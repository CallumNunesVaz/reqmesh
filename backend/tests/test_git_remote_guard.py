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


@pytest.mark.parametrize("url", [
    "https://user:token@github.com/org/repo.git",
    "https://ghp_abcdef@github.com/org/repo.git",
    "ssh://user:pass@github.com/org/repo.git",
])
def test_credentials_embedded_in_the_url_are_rejected(url):
    """A token in the URL would be committed to _meta.yaml and pushed."""
    assert git_service.is_allowed_remote(url) is False
    assert "credentials" in (git_service.remote_url_error(url) or "")


def test_plain_ssh_username_is_not_a_credential():
    """``ssh://git@host`` is the conventional SSH username, not a secret."""
    assert git_service.is_allowed_remote("ssh://git@github.com/org/repo.git") is True
    assert git_service.is_allowed_remote("git@github.com:org/repo.git") is True


def test_allowlist_is_shared_with_the_write_path():
    """One definition, so a new caller cannot drift from the write path."""
    from app.api import router as router_mod
    assert router_mod._remote_url_error is git_service.remote_url_error


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


# ── The write and read paths treat credentials as secrets ────────────────────

def test_credentials_are_rejected_by_the_write_path(tmp_path, monkeypatch):
    client = _client("admin", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    res = client.patch(
        "/api/projects/p",
        json={"git": {"remote_url": "https://user:token@github.com/o/r.git"}},
    )
    assert res.status_code == 400
    assert "credentials" in res.text
    app.dependency_overrides.clear()


def test_read_path_redacts_a_legacy_credentialed_remote(tmp_path, monkeypatch):
    from app.core import dependencies as deps
    from app.services.yaml_store import YamlStore

    # `get_project` resolves the user itself (the injected guard is not enough
    # to decide whether to include the git key), so pin the resolver.
    monkeypatch.setattr(
        deps, "get_current_user",
        lambda request, authorization=None: {"username": "adm", "role": "admin"},
    )
    client = _client("admin", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    store = YamlStore(Path(settings.data_root) / "p")
    meta = store.read_meta()
    meta["git"] = {"remote_url": "https://user:secret@github.com/o/r.git"}
    store.write_meta(meta)

    res = client.get("/api/projects/p")
    assert res.status_code == 200
    assert res.json()["git"]["remote_url"] == "https://***@github.com/o/r.git"
    app.dependency_overrides.clear()


def test_echoing_the_redacted_url_does_not_overwrite_the_stored_one(tmp_path, monkeypatch):
    from app.services.yaml_store import YamlStore

    client = _client("admin", tmp_path, monkeypatch)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    store = YamlStore(Path(settings.data_root) / "p")
    meta = store.read_meta()
    meta["git"] = {"remote_url": "https://user:secret@github.com/o/r.git"}
    store.write_meta(meta)

    res = client.patch("/api/projects/p",
                       json={"git": {"remote_url": "https://***@github.com/o/r.git",
                                     "user_name": "Someone"}})
    assert res.status_code == 200, res.text
    stored = store.read_meta()["git"]["remote_url"]
    assert stored == "https://user:secret@github.com/o/r.git"
    assert store.read_meta()["git"]["user_name"] == "Someone"
    app.dependency_overrides.clear()
