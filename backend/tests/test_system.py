"""Tests for self-update (updater service + /api/system routes) and migrations."""

import app.services.migrations as mig
from app.core.config import settings
from app.services import updater


# ── Version comparison ───────────────────────────────────────────────────────

def test_semver_parse_and_compare():
    assert updater.parse_semver("v0.0.1") == (0, 0, 1)
    assert updater.parse_semver("1.2.3-beta") == (1, 2, 3)
    assert updater.parse_semver("nope") is None
    assert updater.is_newer("0.0.2", "0.0.1")
    assert updater.is_newer("0.1.0", "0.0.9")
    assert not updater.is_newer("0.0.1", "0.0.1")
    assert not updater.is_newer("0.0.1", "0.0.2")
    # Unparseable versions compare equal (never falsely offer an update).
    assert updater.compare_versions("weird", "0.0.1") == 0


# ── Migration framework ──────────────────────────────────────────────────────

def test_migrations_init_and_idempotent(tmp_path):
    root = tmp_path / "projects"
    first = mig.run_migrations(root)
    assert first["initialized"] == mig.CURRENT_SCHEMA_VERSION
    assert mig.read_schema_version(root) == mig.CURRENT_SCHEMA_VERSION
    # Second call is a no-op.
    second = mig.run_migrations(root)
    assert second["ran"] == []


def test_migrations_run_pending(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    mig.run_migrations(root)  # marker at current

    next_ver = mig.CURRENT_SCHEMA_VERSION + 1
    calls = []

    def fake_migration(data_root):
        calls.append(data_root)
        (data_root / "migrated.flag").write_text("ok")

    monkeypatch.setattr(mig, "CURRENT_SCHEMA_VERSION", next_ver)
    monkeypatch.setitem(mig.MIGRATIONS, next_ver, fake_migration)

    result = mig.run_migrations(root)
    assert result["ran"] == [next_ver]
    assert len(calls) == 1
    assert (root / "migrated.flag").exists()
    assert mig.read_schema_version(root) == next_ver


# ── Runtime / status (local test env is not Docker) ──────────────────────────

def test_self_update_unsupported_off_docker(monkeypatch):
    monkeypatch.setattr(updater, "is_running_in_docker", lambda: False)
    assert updater.self_update_supported() is False
    status = updater.get_update_status()
    assert status["state"] == updater.UNSUPPORTED


def test_request_update_rejected_when_unsupported(monkeypatch):
    monkeypatch.setattr(updater, "self_update_supported", lambda: False)
    try:
        updater.request_update("9.9.9", "admin")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


# ── API routes ───────────────────────────────────────────────────────────────

def test_system_info(client):
    res = client.get("/api/system/info")
    assert res.status_code == 200
    body = res.json()
    assert set(["version", "docker", "self_update_supported", "github_repo"]).issubset(body)


def test_system_endpoints_require_admin(guest_client):
    for path in ("/api/system/info", "/api/system/update/status", "/api/system/update/check"):
        assert guest_client.get(path).status_code == 403
    assert guest_client.post("/api/system/update", json={}).status_code == 403


def test_update_check_offline(client, monkeypatch):
    monkeypatch.setattr(settings, "offline_mode", True)
    updater._check_cache = None
    res = client.get("/api/system/update/check?force=true")
    assert res.status_code == 200
    body = res.json()
    assert body["offline"] is True
    assert body["update_available"] is False


def test_update_check_detects_newer_release(client, monkeypatch):
    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(updater, "_github_latest_release",
                        lambda: {"tag_name": "v99.0.0", "body": "big", "html_url": "http://x", "published_at": "2026"})
    updater._check_cache = None
    res = client.get("/api/system/update/check?force=true")
    body = res.json()
    assert body["latest"] == "99.0.0"
    assert body["update_available"] is True
    assert body["notes"] == "big"


def test_start_update_conflict_when_unsupported(client, monkeypatch):
    monkeypatch.setattr(updater, "self_update_supported", lambda: False)
    res = client.post("/api/system/update", json={"target_version": "99.0.0"})
    assert res.status_code == 409


def test_supervised_update_flow_writes_control_files(client, tmp_path, monkeypatch):
    """With a writable control dir + docker faked on, an update writes the
    request/target/status files the sidecar consumes."""
    control = tmp_path / "control"
    monkeypatch.setattr(settings, "update_control_dir", str(control))
    monkeypatch.setattr(updater, "is_running_in_docker", lambda: True)
    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(settings, "self_update_enabled", True)

    res = client.post("/api/system/update", json={"target_version": "99.0.0"})
    assert res.status_code == 200, res.text
    assert (control / "update-target").read_text().strip() == "99.0.0"
    assert (control / "update-request.json").exists()
    assert (control / "update-status.json").exists()

    status = client.get("/api/system/update/status").json()
    assert status["target_version"] == "99.0.0"
    assert status["state"] in ("requested", "in_progress")
