"""`/git/test-remote` must not be a way to reach git with an unchecked URL.

Setting a project's remote is admin-only and scheme-restricted
(`router._guard_git_settings`). The connection test hands the same URL to
`git ls-remote`, which accepts local paths and `file://` — so without the same
gate it read branch names out of arbitrary repositories on the host, confirmed
filesystem paths through its error text, and probed internal hosts and ports.
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
from app.services import git_service


@pytest.fixture()
def secret_repo(tmp_path) -> Path:
    """A repository elsewhere on the host, with a distinctive branch name."""
    repo = tmp_path / "private-internal-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "unreleased-feature-q4"],
                   cwd=repo, check=True)
    (repo / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=a",
                    "commit", "-qm", "x"], cwd=repo, check=True)
    return repo


@pytest.fixture()
def project(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    root = tmp_path / "projects" / "p"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


# ── The service refuses at the boundary ──────────────────────────────────────

@pytest.mark.parametrize("scheme_desc", ["bare local path", "file:// URL"])
def test_local_repositories_are_refused(project, secret_repo, scheme_desc):
    url = str(secret_repo) if scheme_desc == "bare local path" else f"file://{secret_repo}"
    result = git_service.test_remote(project, url)
    assert result["ok"] is False
    assert "https://" in result["error"]
    # The branch name must not leak in any form.
    assert "unreleased-feature-q4" not in str(result)


def test_internal_http_target_is_refused_before_any_connection(project):
    """http:// is banned outright, which also closes the port-probe oracle."""
    result = git_service.test_remote(project, "http://127.0.0.1:9/")
    assert result["ok"] is False
    assert "https://" in result["error"]
    # Refused by the allowlist, not by a failed connection.
    assert "connect" not in result["error"].lower()


@pytest.mark.parametrize("url", [
    "https://github.com/org/repo.git",
    "ssh://git@github.com/org/repo.git",
    "git@github.com:org/repo.git",
])
def test_allowed_schemes_pass_the_guard(project, url):
    """They must reach git — this test asserts the guard, not connectivity."""
    assert git_service.is_allowed_remote(url) is True


@pytest.mark.parametrize("url", [
    "/srv/git/other-project",
    "file:///etc",
    "http://internal.example/repo.git",
    "ext::sh -c 'id'",
    "git://10.0.0.5/repo.git",
    "../../../other-repo",
])
def test_disallowed_schemes_are_rejected(url):
    assert git_service.is_allowed_remote(url) is False


def test_allowlist_is_shared_with_the_write_path():
    """One definition, so a new caller cannot drift from the write path."""
    from app.api import router as router_mod
    assert router_mod._ALLOWED_REMOTE_SCHEMES is git_service.ALLOWED_REMOTE_SCHEMES


# ── The endpoint requires admin ──────────────────────────────────────────────

def _client(role: str, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "require_auth", False)
    monkeypatch.setattr(settings, "git_autocommit", False)
    user = {"username": "u", "role": role}
    for dep in (require_edit, require_maintain, require_maintain_global):
        app.dependency_overrides[dep] = lambda: user

    def _admin_only():
        from fastapi import HTTPException
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        return user

    app.dependency_overrides[require_admin] = _admin_only
    return TestClient(app)


def test_maintainer_cannot_test_a_remote(tmp_path, monkeypatch, secret_repo):
    """It was require_maintain; setting the remote has always been admin-only."""
    client = _client("maintainer", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    res = client.post("/api/projects/p/git/test-remote",
                      json={"remote_url": str(secret_repo)})
    assert res.status_code == 403
    app.dependency_overrides.clear()


def test_admin_still_gets_the_scheme_check(tmp_path, monkeypatch, secret_repo):
    """Admin is not a bypass — the URL is validated for them too."""
    client = _client("admin", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    res = client.post("/api/projects/p/git/test-remote",
                      json={"remote_url": str(secret_repo)})
    assert res.status_code == 400
    assert "unreleased-feature-q4" not in res.text
    app.dependency_overrides.clear()


def test_missing_url_is_a_400(tmp_path, monkeypatch):
    client = _client("admin", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    res = client.post("/api/projects/p/git/test-remote", json={})
    assert res.status_code == 400
    app.dependency_overrides.clear()
