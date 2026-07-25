"""Regression tests for the auto-commit middleware's project-id handling.

The middleware in ``app.main`` runs *after* the response, keyed off
``request.url.path``. That path has already been percent-decoded once by the
ASGI server, so decoding it a second time let an unauthenticated caller walk
out of the data root with ``%252e%252e%252f`` and run git commands in an
arbitrary repository on the host. Nothing else guarded that path: a
trailing-slash **307** satisfies the middleware's ``status_code < 400`` check
without any route handler, auth dependency or ``safe_id`` ever running.

These tests drive the ASGI app directly with a hand-built scope, because that
is the only faithful way to reproduce what uvicorn hands the application — a
test client would re-encode the segment and hide the bug.
"""
import asyncio
import shutil
import subprocess

import pytest

from app.core.config import settings
from app.core.ids import safe_id
from app.main import app
from fastapi import HTTPException

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _asgi_post(path: str) -> int:
    """POST through the real middleware stack with an already-decoded path,
    exactly as uvicorn would deliver it. Returns the HTTP status."""
    status: dict = {}

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": [(b"host", b"testserver"),
                    (b"content-type", b"application/json"),
                    (b"content-length", b"2")],
        "client": ("1.2.3.4", 1), "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return status.get("code", 0)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_repo(path, dirty=True):
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=path)
    _git("config", "user.email", "v@example.test", cwd=path)
    _git("config", "user.name", "victim", cwd=path)
    (path / "tracked.txt").write_text("committed")
    _git("add", "-A", cwd=path)
    _git("commit", "-q", "-m", "initial", cwd=path)
    if dirty:
        # Work in progress the attacker would otherwise sweep into a commit.
        (path / "tracked.txt").write_text("uncommitted work")
        (path / "private_notes.txt").write_text("not meant to be committed")
    return _head(path)


def _head(path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path,
                          capture_output=True, text=True).stdout.strip()


class TestEncodedTraversal:
    @needs_git
    @pytest.mark.parametrize("segment", [
        "%2e%2e%2fvictim_repo",      # what uvicorn yields for %252e%252e%252f
        "%2e%2e/victim_repo",
        "..%2fvictim_repo",
        "../victim_repo",
    ])
    def test_does_not_touch_a_repo_outside_the_data_root(self, workspace, monkeypatch, segment):
        monkeypatch.setattr(settings, "git_autocommit", True)
        data_root = workspace / "projects"
        data_root.mkdir(parents=True, exist_ok=True)
        victim = workspace / "victim_repo"
        before = _make_repo(victim)

        _asgi_post(f"/api/projects/{segment}/requirements/")

        assert _head(victim) == before, f"foreign repo was modified via {segment!r}"
        assert (victim / "private_notes.txt").exists(), "uncommitted file was swept away"
        # Still dirty => nothing was committed on the victim's behalf.
        porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=victim,
                                   capture_output=True, text=True).stdout
        assert porcelain.strip(), "victim working tree was unexpectedly cleaned"

    def test_safe_id_rejects_traversal_segments(self):
        for bad in ("../victim", "..", "a/../../b", "%2e%2e", "a/b"):
            with pytest.raises(HTTPException):
                safe_id(bad, "project id")


class TestLegitimateAutocommitStillWorks:
    @needs_git
    def test_mutation_creates_a_commit(self, client, monkeypatch):
        """The guard must not break the feature it protects."""
        monkeypatch.setattr(settings, "git_autocommit", True)
        client.post("/api/projects", json={"id": "demo", "name": "Demo"})
        project = __import__("pathlib").Path(settings.data_root) / "demo"
        _git("init", "-q", cwd=project)
        _git("config", "user.email", "d@example.test", cwd=project)
        _git("config", "user.name", "dev", cwd=project)
        _git("add", "-A", cwd=project)
        _git("commit", "-q", "-m", "init", cwd=project)
        before = _head(project)

        res = client.post("/api/projects/demo/requirements",
                          json={"id": "REQ0001", "name": "Cabin pressure"})
        assert res.status_code == 201

        assert _head(project) != before, "legitimate mutation no longer auto-commits"
        msg = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=project,
                             capture_output=True, text=True).stdout.strip()
        assert msg == "rt: post requirements"
