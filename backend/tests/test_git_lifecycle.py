"""Git lifecycle: status, init, push, remote management, and credential safety.

All tests drive real git repositories — the ``client`` fixture's projects are
real directories, so these are integration tests, not mocks.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


from app.core import auth
from app.core.config import settings
from app.main import app
from app.services import git_service


# ── helpers ───────────────────────────────────────────────────────────────────

def _patch_project(client, project_id, git_fields: dict):
    return client.patch(
        f"/api/projects/{project_id}",
        json={"git": git_fields},
    )


def _read_meta_yaml(project_root: Path) -> dict:
    """Read the project's _meta.yaml without going through YamlStore."""
    from ruamel.yaml import YAML
    y = YAML(typ="safe")
    with open(project_root / "_meta.yaml") as f:
        return y.load(f) or {}


# ── status on a non-repo ──────────────────────────────────────────────────────

def test_status_non_repo_returns_is_repo_false(client, project):
    """When there is no .git directory, status must not 500."""
    res = client.get(f"/api/projects/{project}/git/status")
    assert res.status_code == 200
    body = res.json()
    assert body["is_repo"] is False
    assert body["commit_count"] == 0
    assert body["head"] is None
    assert body["has_remote"] is False


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_creates_a_repo(client, project):
    """POST /git/init must create a .git directory."""
    res = client.post(f"/api/projects/{project}/git/init")
    assert res.status_code == 201
    assert res.json()["initialised"] is True

    # Verify on disk
    store_root = Path(settings.data_root) / project
    assert (store_root / ".git").is_dir()


def test_second_init_returns_409(client, project):
    """A second initialisation on an existing repo must 409."""
    res = client.post(f"/api/projects/{project}/git/init")
    assert res.status_code == 201

    res2 = client.post(f"/api/projects/{project}/git/init")
    assert res2.status_code == 409


# ── status reports dirty and commit_count ─────────────────────────────────────

def test_status_reports_dirty_and_commit_count(client, project):
    """After init and an initial commit, status should show 0 dirty and
    1 commit.  After a write via the API, dirty should be true."""
    # Init first
    client.post(f"/api/projects/{project}/git/init")

    store_root = Path(settings.data_root) / project
    # Commit the initial _meta.yaml so the repo is clean
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "initial"],
        cwd=str(store_root), capture_output=True, text=True,
    )

    # Now status should show clean and 1 commit
    res = client.get(f"/api/projects/{project}/git/status")
    assert res.status_code == 200
    body = res.json()
    assert body["is_repo"] is True
    assert body["dirty"] is False
    assert body["commit_count"] == 1
    assert body["head"] is not None
    assert body["head"]["message"] == "initial"


def test_status_dirty_flag(client, project):
    """Dirty must be true when there are uncommitted changes."""
    client.post(f"/api/projects/{project}/git/init")

    store_root = Path(settings.data_root) / project
    # Create an initial commit so we can detect dirty
    (store_root / "somefile").write_text("initial")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "initial"],
        cwd=str(store_root), capture_output=True, text=True,
    )

    # Clean state
    res = client.get(f"/api/projects/{project}/git/status")
    assert res.json()["dirty"] is False

    # Make a change
    (store_root / "somefile").write_text("changed")

    res = client.get(f"/api/projects/{project}/git/status")
    assert res.json()["dirty"] is True


# ── credential redaction ──────────────────────────────────────────────────────

def test_remote_url_credentials_are_redacted_in_status(client, project):
    """Tokens embedded in a remote URL must not appear in the status response."""
    client.post(f"/api/projects/{project}/git/init")

    # Set a remote URL with a token
    res = _patch_project(
        client, project,
        {"remote_url": "https://ghp_secret123token@github.com/acme/repo.git"},
    )
    assert res.status_code == 200

    res = client.get(f"/api/projects/{project}/git/status")
    assert res.status_code == 200
    body = res.json()

    # The raw token must not appear anywhere in the body
    body_str = str(body)
    assert "ghp_secret123token" not in body_str
    # The remote_url field should be redacted
    assert "***@" in body["remote_url"] or body["remote_url"].startswith("https://***@")
    # has_remote should still be true
    assert body["has_remote"] is True


def test_failed_push_error_is_redacted(client, project, monkeypatch):
    """When a push fails, the error in the response must not contain credentials."""
    monkeypatch.setattr(settings, "offline_mode", False)
    client.post(f"/api/projects/{project}/git/init")

    # Set a remote URL with a token, pointing at a non-existent host
    _patch_project(
        client, project,
        {"remote_url": "https://token-abc123@push-target.invalid/repo.git"},
    )

    # Attempt a push — it will fail because the remote doesn't exist
    res = client.post(f"/api/projects/{project}/git/push")
    # The push should fail (non-200), but must not 500 either
    assert res.status_code == 502  # push now raises HTTPException on failure

    body = res.json()
    # Error text must be present but must not contain the raw token
    error_text = str(body)
    assert "token-abc123" not in error_text


# ── push records outcome ──────────────────────────────────────────────────────

def test_failed_push_records_last_push_outcome(client, project, monkeypatch):
    """After a failed push, status must report last_push.ok == false."""
    monkeypatch.setattr(settings, "offline_mode", False)
    client.post(f"/api/projects/{project}/git/init")

    # Commit something so there is something to push
    store_root = Path(settings.data_root) / project
    (store_root / "f").write_text("data")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "pre-push"],
        cwd=str(store_root), capture_output=True, text=True,
    )

    # Set an unreachable remote
    _patch_project(
        client, project,
        {"remote_url": "https://nonexistent.example.invalid/repo.git"},
    )

    res = client.post(f"/api/projects/{project}/git/push")
    assert res.status_code == 502
    assert "ok" not in (res.json() or {})  # error responses have `detail`, not `ok`

    # Status should now report the failed push
    res = client.get(f"/api/projects/{project}/git/status")
    body = res.json()
    assert body["last_push"] is not None
    assert body["last_push"]["ok"] is False
    assert body["last_push"]["error"] is not None
    # Timestamp should be present
    assert "at" in body["last_push"]


# ── delete remote ─────────────────────────────────────────────────────────────

def test_delete_remote_by_maintainer_is_403(workspace, monkeypatch):
    """A maintainer cannot delete the remote (admin-only).

    Uses a fresh TestClient with no dependency overrides so the role check
    is real — the ``client`` fixture overrides every guard to admin, which
    would make this test always pass for the wrong reason.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "require_auth", False)

    # Clear any existing dependency overrides so real auth is used.
    app.dependency_overrides.clear()
    try:
        auth.register_user("mo", "Password123!", "maintainer")
        auth.register_user("adm", "Password123!", "admin")

        # Admin creates project and sets remote
        login_res = TestClient(app).post(
            "/api/auth/login",
            json={"username": "adm", "password": "Password123!"},
        )
        csrf = login_res.json()["csrf_token"]
        TestClient(app).post(
            "/api/projects", json={"id": "testdel", "name": "Test Delete"},
            headers={"X-CSRF-Token": csrf},
        )
        TestClient(app).patch(
            "/api/projects/testdel",
            json={"git": {"remote_url": "https://example.com/repo.git"}},
            headers={"X-CSRF-Token": csrf},
        )
        TestClient(app).post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )

        # Maintainer tries to delete
        login_res = TestClient(app).post(
            "/api/auth/login",
            json={"username": "mo", "password": "Password123!"},
        )
        maint_csrf = login_res.json()["csrf_token"]
        maint_client = TestClient(app)
        maint_client.headers.update({"X-CSRF-Token": maint_csrf})

        res = maint_client.delete("/api/projects/testdel/git/remote")
        assert res.status_code == 403, res.text
    finally:
        app.dependency_overrides.clear()


def test_delete_remote_by_admin_succeeds_and_clears_both(client, project):
    """Admin can delete the remote, and both the git remote and the
    remote_url setting are cleared."""
    client.post(f"/api/projects/{project}/git/init")

    store_root = Path(settings.data_root) / project

    # Set remote_url in settings
    _patch_project(
        client, project,
        {"remote_url": "https://example.com/repo.git"},
    )

    # Set up the actual git remote (ensure_remote is called lazily by push,
    # but setting the URL in _meta.yaml doesn't call it directly)
    git_service.ensure_remote(store_root, "https://example.com/repo.git")

    # Verify the git remote exists
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    assert result.returncode == 0, f"remote not set: {result.stderr}"

    # Delete
    res = client.delete(f"/api/projects/{project}/git/remote")
    assert res.status_code == 200, res.text

    # Both should be gone
    meta = _read_meta_yaml(store_root)
    assert "remote_url" not in meta.get("git", {})

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    assert result.returncode != 0  # No remote anymore


# ── scheme validation still applies ───────────────────────────────────────────

def test_setting_disallowed_scheme_is_still_rejected(client, project):
    """The scheme allowlist is enforced on the write path."""
    for bad in ("file:///etc/passwd", "http://169.254.169.254/repo.git"):
        res = _patch_project(client, project, {"remote_url": bad})
        assert res.status_code == 400, f"{bad} -> {res.status_code}"


# ── status performs no network access ─────────────────────────────────────────

def test_status_is_not_blocked_by_unreachable_remote(client, project, monkeypatch):
    """A status call must return promptly even with an unreachable remote
    configured. This is the whole reason ``ahead`` is computed from the
    local tracking ref — a status poll must never hang."""
    monkeypatch.setattr(settings, "offline_mode", False)
    client.post(f"/api/projects/{project}/git/init")

    # Commit something so there is a HEAD
    store_root = Path(settings.data_root) / project
    (store_root / "f").write_text("x")
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(store_root), capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "x"],
        cwd=str(store_root), capture_output=True, text=True,
    )

    # Set an unreachable remote
    _patch_project(
        client, project,
        {"remote_url": "https://192.0.2.1/repo.git"},
    )

    start = time.monotonic()
    res = client.get(f"/api/projects/{project}/git/status")
    elapsed = time.monotonic() - start

    assert res.status_code == 200
    # Must return in well under 5 seconds — a network call to an unreachable
    # host would block for much longer.
    assert elapsed < 5, f"status took {elapsed:.1f}s — looks like a network call"


# ── offline mode ──────────────────────────────────────────────────────────────

def test_push_in_offline_mode_records_offline_status(client, project, monkeypatch):
    """When offline_mode is enabled, push must skip and status must say so."""
    monkeypatch.setattr(settings, "offline_mode", True)
    client.post(f"/api/projects/{project}/git/init")

    res = client.post(f"/api/projects/{project}/git/push")
    assert res.status_code == 502
    detail = res.json().get("detail", "")
    assert "offline" in detail.lower()

    # Status should also report the push outcome
    res = client.get(f"/api/projects/{project}/git/status")
    body = res.json()
    assert body["last_push"] is not None
    assert body["last_push"]["ok"] is False
