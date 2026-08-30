"""Ed25519 signature verification for uploaded update bundles (SEC-9).

An uploaded bundle was validated by *shape* only — a tarball, one top-level
directory, a manifest with a newer version, ``backend/app`` and ``frontend/dist``.
The ``.sha256`` that ``build_bundle.sh`` emits proved nothing: an attacker
substituting the bundle substitutes the checksum with it. ``stage_from_archive``
now verifies a detached Ed25519 signature over the raw archive bytes *before*
the tarball is ever opened, so an unverified tar is never extracted and re-exec'd.

The key pair is generated in these tests; no key material is committed.
"""

import base64
import json
import logging
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.services import bundle_update as bu
from app.services import updater


def _make_install(tmp_path):
    inst = tmp_path / "install"
    (inst / "backend" / "app").mkdir(parents=True)
    (inst / "backend" / "app" / "marker.txt").write_text("OLD")
    (inst / "frontend" / "dist").mkdir(parents=True)
    (inst / "frontend" / "dist" / "index.html").write_text("OLD ui")
    (inst / "manifest.json").write_text(json.dumps({"version": "1.0.0"}))
    (inst / "VERSION").write_text("1.0.0\n")
    return inst


def _make_bundle(tmp_path, version="2.0.0"):
    top = tmp_path / "src" / f"reqmesh-v{version}"
    (top / "backend" / "app").mkdir(parents=True)
    (top / "backend" / "app" / "marker.txt").write_text("NEW")
    (top / "frontend" / "dist").mkdir(parents=True)
    (top / "frontend" / "dist" / "index.html").write_text("NEW ui")
    (top / "manifest.json").write_text(json.dumps({"version": version, "git_sha": "sha"}))
    (top / "VERSION").write_text(f"{version}\n")
    tarball = tmp_path / f"reqmesh-v{version}.tar.gz"
    with tarfile.open(tarball, "w:gz") as t:
        t.add(top, arcname=f"reqmesh-v{version}")
    return tarball


def _patch_bundle(monkeypatch, inst):
    monkeypatch.setattr(bu, "install_root", lambda: inst)
    monkeypatch.setattr(bu, "bundle_update_supported", lambda: True)
    monkeypatch.setattr(bu, "get_version", lambda: "1.0.0")
    monkeypatch.setattr(updater, "create_backup", lambda fv: {"tag": "pre", "projects": ["p"]})


def _keypair():
    """A fresh Ed25519 key pair: (private_key, base64 raw public key)."""
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return private, base64.b64encode(raw).decode()


def _sign(private, archive):
    """Write a detached signature over the raw archive bytes, at <archive>.sig."""
    sig_path = Path(str(archive) + ".sig")
    sig_path.write_bytes(private.sign(archive.read_bytes()))
    return sig_path


def test_signed_bundle_stages_with_matching_key(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    private, pub_b64 = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub_b64)
    tarball = _make_bundle(tmp_path)
    _sign(private, tarball)

    res = bu.stage_from_archive(tarball, "admin")

    assert res["state"] == "staged"
    assert res["target_version"] == "2.0.0"
    assert not tarball.exists()  # archive consumed


def test_wrong_key_rejected(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    private, _ = _keypair()
    _, other_pub = _keypair()
    monkeypatch.setattr(settings, "update_public_key", other_pub)
    tarball = _make_bundle(tmp_path)
    _sign(private, tarball)

    with pytest.raises(RuntimeError) as excinfo:
        bu.stage_from_archive(tarball, "admin")
    assert str(excinfo.value) == "Bundle signature is not valid for this instance's update key."


def test_unsigned_bundle_rejected_when_key_configured(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    _, pub_b64 = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub_b64)
    tarball = _make_bundle(tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        bu.stage_from_archive(tarball, "admin")
    assert str(excinfo.value) == "Bundle is not signed, and this instance requires signed updates."


def test_unsigned_bundle_refused_without_key(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    monkeypatch.setattr(settings, "update_public_key", "")
    tarball = _make_bundle(tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        bu.stage_from_archive(tarball, "admin")
    msg = str(excinfo.value)
    assert "RT_UPDATE_PUBLIC_KEY" in msg
    assert "RT_UPDATE_ALLOW_UNSIGNED" in msg


def test_unsigned_bundle_accepted_with_allow_unsigned_logs_warning(tmp_path, monkeypatch, caplog):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    monkeypatch.setattr(settings, "update_public_key", "")
    monkeypatch.setattr(settings, "update_allow_unsigned", True)
    tarball = _make_bundle(tmp_path)

    with caplog.at_level(logging.WARNING, logger="app.services.bundle_update"):
        res = bu.stage_from_archive(tarball, "admin")

    assert res["state"] == "staged"
    assert any("SEC-9" in r.getMessage() for r in caplog.records)


def test_tampered_archive_rejected(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    private, pub_b64 = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub_b64)
    tarball = _make_bundle(tmp_path)
    _sign(private, tarball)

    # Flip one byte in the archive *after* signing.
    data = bytearray(tarball.read_bytes())
    data[-1] ^= 0xFF
    tarball.write_bytes(bytes(data))

    with pytest.raises(RuntimeError) as excinfo:
        bu.stage_from_archive(tarball, "admin")
    assert str(excinfo.value) == "Bundle signature is not valid for this instance's update key."


def test_rejected_bundle_leaves_no_staged_state(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    _, pub_b64 = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub_b64)
    tarball = _make_bundle(tmp_path)

    with pytest.raises(RuntimeError):
        bu.stage_from_archive(tarball, "admin")

    assert not tarball.exists()  # uploaded archive is gone
    updates = inst / ".updates"
    assert not (updates / "staged").exists()
    assert not (updates / "pending.json").exists()


def test_unparseable_key_rejected(tmp_path, monkeypatch):
    inst = _make_install(tmp_path)
    _patch_bundle(monkeypatch, inst)
    private, _ = _keypair()
    monkeypatch.setattr(settings, "update_public_key", "!!!not-base64!!!")
    tarball = _make_bundle(tmp_path)
    _sign(private, tarball)

    with pytest.raises(RuntimeError) as excinfo:
        bu.stage_from_archive(tarball, "admin")
    assert str(excinfo.value) == "RT_UPDATE_PUBLIC_KEY is not a valid Ed25519 public key."
