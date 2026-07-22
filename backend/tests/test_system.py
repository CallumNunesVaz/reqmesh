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


def test_file_update_supported_offline(monkeypatch, tmp_path):
    """File-based update must work even in offline mode (its whole purpose)."""
    monkeypatch.setattr(settings, "update_control_dir", str(tmp_path / "control"))
    monkeypatch.setattr(updater, "is_running_in_docker", lambda: True)
    monkeypatch.setattr(settings, "self_update_enabled", True)
    monkeypatch.setattr(settings, "offline_mode", True)
    assert updater.file_update_supported() is True
    # Registry-based update stays disabled offline.
    assert updater.self_update_supported() is False


def test_upload_update_stages_image_and_requests(client, tmp_path, monkeypatch):
    control = tmp_path / "control"
    monkeypatch.setattr(settings, "update_control_dir", str(control))
    monkeypatch.setattr(updater, "is_running_in_docker", lambda: True)
    monkeypatch.setattr(settings, "self_update_enabled", True)
    monkeypatch.setattr(settings, "offline_mode", True)  # proves offline works

    res = client.post(
        "/api/system/update/upload",
        files={"file": ("reqmesh-v0.0.9-image.tar.gz", b"not-a-real-image-but-nonempty", "application/gzip")},
        data={"target_version": "0.0.9"},
    )
    assert res.status_code == 200, res.text
    assert (control / "update-image.tar").read_bytes() == b"not-a-real-image-but-nonempty"
    assert (control / "update-mode").read_text().strip() == "image"
    assert (control / "update-target").read_text().strip() == "0.0.9"
    status = client.get("/api/system/update/status").json()
    assert status["state"] in ("requested", "in_progress")
    assert status["target_version"] == "0.0.9"


def test_upload_update_rejects_empty(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "update_control_dir", str(tmp_path / "control"))
    monkeypatch.setattr(updater, "is_running_in_docker", lambda: True)
    monkeypatch.setattr(settings, "self_update_enabled", True)
    res = client.post("/api/system/update/upload",
                      files={"file": ("empty.tar", b"", "application/x-tar")})
    assert res.status_code == 400


def test_upload_update_conflict_when_unsupported(client, monkeypatch):
    monkeypatch.setattr(updater, "file_update_supported", lambda: False)
    res = client.post("/api/system/update/upload",
                      files={"file": ("x.tar.gz", b"data", "application/gzip")})
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


# ── Bare-metal bundle update (updater bundle_update service) ──────────────────

import json as _json
import os as _os
import tarfile as _tarfile

from app.services import bundle_update as bu


def _make_install(tmp_path):
    inst = tmp_path / "install"
    (inst / "backend" / "app").mkdir(parents=True)
    (inst / "backend" / "app" / "marker.txt").write_text("OLD")
    (inst / "frontend" / "dist").mkdir(parents=True)
    (inst / "frontend" / "dist" / "index.html").write_text("OLD ui")
    (inst / "manifest.json").write_text(_json.dumps({"version": "1.0.0"}))
    (inst / "VERSION").write_text("1.0.0\n")
    return inst


def _make_bundle(tmp_path, version="2.0.0", *, drop_frontend=False, traversal=False):
    top = tmp_path / "src" / f"reqmesh-v{version}"
    (top / "backend" / "app").mkdir(parents=True)
    (top / "backend" / "app" / "marker.txt").write_text("NEW")
    if not drop_frontend:
        (top / "frontend" / "dist").mkdir(parents=True)
        (top / "frontend" / "dist" / "index.html").write_text("NEW ui")
    (top / "manifest.json").write_text(_json.dumps({"version": version, "git_sha": "sha"}))
    (top / "VERSION").write_text(f"{version}\n")
    tarball = tmp_path / f"reqmesh-v{version}.tar.gz"
    with _tarfile.open(tarball, "w:gz") as t:
        t.add(top, arcname=f"reqmesh-v{version}")
        if traversal:
            import io
            ti = _tarfile.TarInfo("../evil.txt")
            payload = b"pwn"
            ti.size = len(payload)
            t.addfile(ti, io.BytesIO(payload))
    return tarball


def _patch_bundle(monkeypatch, inst):
    monkeypatch.setattr(bu, "install_root", lambda: inst)
    monkeypatch.setattr(bu, "bundle_update_supported", lambda: True)
    monkeypatch.setattr(bu, "get_version", lambda: "1.0.0")
    monkeypatch.setattr(updater, "create_backup", lambda fv: {"tag": "pre", "projects": ["p"]})


def test_bundle_stage_and_apply(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    tarball = _make_bundle(tmp_path)

    res = bu.stage_from_archive(tarball, "admin")
    assert res["state"] == "staged" and res["target_version"] == "2.0.0"
    assert bu.pending_marker() is not None
    assert bu.bundle_status()["state"] == "staged"
    assert not tarball.exists()  # archive consumed

    reexecs = []
    monkeypatch.setattr(bu, "reexec", lambda: reexecs.append(1))
    monkeypatch.setattr(_os, "chdir", lambda p: None)
    bu.apply_pending_update()

    assert reexecs == [1]
    assert (inst / "backend" / "app" / "marker.txt").read_text() == "NEW"
    assert (inst / "frontend" / "dist" / "index.html").read_text() == "NEW ui"
    assert (inst / "VERSION").read_text().strip() == "2.0.0"
    assert bu.pending_marker() is None
    assert bu.bundle_status()["state"] == "completed"
    # Rollback copy of the previous version is retained.
    rollbacks = list((inst / ".updates").glob("rollback-*"))
    assert rollbacks and (rollbacks[0] / "backend" / "app" / "marker.txt").read_text() == "OLD"


def test_bundle_rejects_not_newer(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    tarball = _make_bundle(tmp_path, version="0.5.0")
    try:
        bu.stage_from_archive(tarball, "admin")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "not newer" in str(e)


def test_bundle_rejects_malformed(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    tarball = _make_bundle(tmp_path, drop_frontend=True)
    try:
        bu.stage_from_archive(tarball, "admin")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "frontend/dist" in str(e)


def test_bundle_blocks_path_traversal(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    tarball = _make_bundle(tmp_path, traversal=True)
    try:
        bu.stage_from_archive(tarball, "admin")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    # Nothing escaped the install tree.
    assert not (tmp_path / "evil.txt").exists()


def test_apply_incomplete_staged_records_failure(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    (inst / ".updates" / "staged").mkdir(parents=True)  # empty → incomplete
    bu._write_json_atomic(inst / ".updates" / "pending.json", {"target_version": "2.0.0"})
    monkeypatch.setattr(bu, "reexec", lambda: (_ for _ in ()).throw(AssertionError("must not reexec")))
    bu.apply_pending_update()
    assert bu.bundle_status()["state"] == "failed"
    assert (inst / "backend" / "app" / "marker.txt").read_text() == "OLD"  # intact
    assert bu.pending_marker() is None


def test_runtime_info_exposes_bundle_fields(client):
    body = client.get("/api/system/info").json()
    assert "bundle_update_supported" in body
    assert "can_restart" in body


def test_bundle_upload_conflict_when_unsupported(client, monkeypatch):
    monkeypatch.setattr(bu, "bundle_update_supported", lambda: False)
    res = client.post("/api/system/update/bundle",
                      files={"file": ("reqmesh-v9.9.9.tar.gz", b"data", "application/gzip")})
    assert res.status_code == 409


def test_restart_conflict_when_unavailable(client, monkeypatch):
    monkeypatch.setattr(bu, "can_restart", lambda: False)
    assert client.post("/api/system/restart").status_code == 409


def test_restart_requires_admin(guest_client):
    assert guest_client.post("/api/system/restart").status_code == 403
    assert guest_client.post("/api/system/update/bundle",
                             files={"file": ("x.tar.gz", b"d", "application/gzip")}).status_code == 403


def test_bundle_apply_rolls_back_when_deps_fail(tmp_path, monkeypatch):
    """A bundle whose requirements changed but can't be installed (e.g. offline)
    must roll the swap back rather than boot new code against stale deps."""
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    # Old install and new bundle carry *different* requirements.txt.
    (inst / "backend" / "requirements.txt").write_text("oldpkg==1.0\n")
    top = tmp_path / "src" / "reqmesh-v2.0.0"
    (top / "backend" / "app").mkdir(parents=True)
    (top / "backend" / "app" / "marker.txt").write_text("NEW")
    (top / "backend" / "requirements.txt").write_text("newpkg==9.9\n")
    (top / "frontend" / "dist").mkdir(parents=True)
    (top / "frontend" / "dist" / "index.html").write_text("NEW ui")
    (top / "manifest.json").write_text(_json.dumps({"version": "2.0.0"}))
    (top / "VERSION").write_text("2.0.0\n")
    tarball = tmp_path / "reqmesh-v2.0.0.tar.gz"
    with _tarfile.open(tarball, "w:gz") as t:
        t.add(top, arcname="reqmesh-v2.0.0")

    bu.stage_from_archive(tarball, "admin")
    monkeypatch.setattr(bu, "_sync_dependencies", lambda reqs: False)  # simulate offline failure
    monkeypatch.setattr(bu, "reexec", lambda: (_ for _ in ()).throw(AssertionError("must not reexec")))
    bu.apply_pending_update()

    assert bu.bundle_status()["state"] == "failed"
    # Everything rolled back to the old version.
    assert (inst / "backend" / "app" / "marker.txt").read_text() == "OLD"
    assert (inst / "frontend" / "dist" / "index.html").read_text() == "OLD ui"
    assert _json.loads((inst / "manifest.json").read_text())["version"] == "1.0.0"
    assert (inst / "VERSION").read_text().strip() == "1.0.0"
    assert bu.pending_marker() is None
