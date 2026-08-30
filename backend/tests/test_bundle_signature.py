"""Signature verification for uploaded update bundles (SEC-9 behaviour change).

An unset ``RT_UPDATE_PUBLIC_KEY`` used to accept unsigned bundles with a warning.
It now *refuses* them, and the refusal must be actionable: the error names both
``RT_UPDATE_PUBLIC_KEY`` and ``RT_UPDATE_ALLOW_UNSIGNED=1`` and says where the
public key is published. These tests assert the message, not just the exception
type, because that is the part a self-updating operator will actually see.
"""

import base64
import logging
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.services import bundle_update as bu


def _keypair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return private, base64.b64encode(raw).decode()


def _sign(private, archive):
    sig_path = Path(str(archive) + ".sig")
    sig_path.write_bytes(private.sign(archive.read_bytes()))
    return sig_path


@pytest.fixture
def archive(tmp_path):
    p = tmp_path / "reqmesh-v2.0.0.tar.gz"
    p.write_bytes(b"reqmesh-bundle-bytes")
    return p


def test_valid_signature_with_configured_key_verifies(archive, monkeypatch):
    private, pub = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub)
    monkeypatch.setattr(settings, "update_allow_unsigned", False)
    sig = _sign(private, archive)

    bu.verify_bundle_signature(archive, sig)  # must not raise


def test_wrong_signature_refused(archive, monkeypatch):
    private, _ = _keypair()
    _, other_pub = _keypair()
    monkeypatch.setattr(settings, "update_public_key", other_pub)
    sig = _sign(private, archive)

    with pytest.raises(RuntimeError):
        bu.verify_bundle_signature(archive, sig)


def test_no_signature_with_configured_key_refused(archive, monkeypatch):
    _, pub = _keypair()
    monkeypatch.setattr(settings, "update_public_key", pub)

    with pytest.raises(RuntimeError):
        bu.verify_bundle_signature(archive, None)


def test_no_key_and_no_allow_refused_with_actionable_message(archive, monkeypatch):
    monkeypatch.setattr(settings, "update_public_key", "")
    monkeypatch.setattr(settings, "update_allow_unsigned", False)

    with pytest.raises(RuntimeError) as excinfo:
        bu.verify_bundle_signature(archive, None)

    msg = str(excinfo.value)
    assert "RT_UPDATE_PUBLIC_KEY" in msg
    assert "RT_UPDATE_ALLOW_UNSIGNED=1" in msg


def test_no_key_with_allow_unsigned_accepted_logs_sec9_warning(archive, monkeypatch, caplog):
    monkeypatch.setattr(settings, "update_public_key", "")
    monkeypatch.setattr(settings, "update_allow_unsigned", True)

    with caplog.at_level(logging.WARNING, logger="app.services.bundle_update"):
        bu.verify_bundle_signature(archive, None)  # must not raise

    assert any("SEC-9" in r.getMessage() for r in caplog.records)
