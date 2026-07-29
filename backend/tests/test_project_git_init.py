"""A new project must actually be a git repository.

Nothing in the application ever ran ``git init``. A project created through the
API was a plain directory, so ``auto_commit`` hit its ``is_repo`` guard and
returned False — which ``_commit_project`` cannot distinguish from "git found
nothing to commit". On a real deployment with ``git_autocommit=true`` every
change was written to disk and none was versioned, with nothing in the logs.

Found by deploying to a clean Ubuntu 24.04 host: after creating a project and a
requirement through the API, ``/data/projects/smoke`` had no ``.git`` at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import (require_admin, require_edit,
                                   require_maintain, require_maintain_global)
from app.main import app
from app.services.git_service import init_repo, is_repo


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "require_auth", False)
    monkeypatch.setattr(settings, "git_autocommit", True)
    admin = {"username": "tester", "role": "admin"}
    for dep in (require_edit, require_maintain, require_maintain_global, require_admin):
        app.dependency_overrides[dep] = lambda: admin
    yield TestClient(app)
    app.dependency_overrides.clear()


def _root(project_id: str = "p") -> Path:
    return Path(settings.data_root) / project_id


# ── The defect ───────────────────────────────────────────────────────────────

def test_created_project_is_a_git_repo(client):
    assert client.post("/api/projects", json={"id": "p", "name": "P"}).status_code == 201
    assert is_repo(_root()), "project directory is not a git repository"


def test_changes_are_actually_committed_end_to_end(client):
    """The whole point: create a project, write to it, get a commit.

    This is what the deployment silently failed to do.
    """
    client.post("/api/projects", json={"id": "p", "name": "P"})
    r = client.post("/api/projects/p/requirements",
                    json={"id": "SYST0001", "title": "versioned"})
    assert r.status_code == 201, r.text

    from app.main import flush_pending_commits
    import asyncio, app.main as main_mod
    monkey_debounce = getattr(main_mod, "_GIT_DEBOUNCE_S", None)
    main_mod._GIT_DEBOUNCE_S = 0.0
    try:
        asyncio.run(flush_pending_commits(force=True))
    finally:
        if monkey_debounce is not None:
            main_mod._GIT_DEBOUNCE_S = monkey_debounce

    out = subprocess.run(["git", "log", "--oneline"], cwd=_root(),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip(), "no commits were made despite git_autocommit=True"


def test_no_repo_when_autocommit_is_off(client, monkeypatch):
    """Don't create repositories for an operator who turned versioning off."""
    monkeypatch.setattr(settings, "git_autocommit", False)
    client.post("/api/projects", json={"id": "q", "name": "Q"})
    assert not is_repo(_root("q"))


# ── init_repo itself ─────────────────────────────────────────────────────────

def test_init_repo_is_idempotent(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    assert init_repo(d) is True
    head_before = (d / ".git" / "HEAD").read_text()
    assert init_repo(d) is True, "second call must be a no-op, not a failure"
    assert (d / ".git" / "HEAD").read_text() == head_before


def test_init_repo_refuses_a_missing_directory(tmp_path):
    assert init_repo(tmp_path / "nope") is False


def test_init_repo_leaves_a_nested_project_alone(tmp_path):
    """A project inside an existing repo is already tracked by its parent.

    Initialising a child repo there would silently detach those files from the
    history the operator set up.
    """
    parent = tmp_path / "outer"
    parent.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=parent, check=True)
    child = parent / "projects" / "inner"
    child.mkdir(parents=True)

    assert init_repo(child) is True          # reports "you have a repo"
    assert not (child / ".git").exists(), "created a nested repo inside a repo"
