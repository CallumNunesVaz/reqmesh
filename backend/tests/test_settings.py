"""Runtime application-settings store and API."""

import os

from app.core import settings_store as ss
from app.core.config import settings


def test_settings_get_lists_overridable(client):
    res = client.get("/api/system/settings")
    assert res.status_code == 200
    keys = {i["key"] for i in res.json()["settings"]}
    assert {"instance_name", "smtp_host", "allow_self_registration"}.issubset(keys)


def test_settings_patch_roundtrip(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "instance_name", "reqmesh")
    res = client.patch("/api/system/settings", json={"instance_name": "Acme Requirements"})
    assert res.status_code == 200
    # Applied to the live settings object...
    assert settings.instance_name == "Acme Requirements"
    # ...and persisted.
    assert ss.load_overrides()["instance_name"] == "Acme Requirements"


def test_settings_secret_redacted_and_blank_ignored(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "smtp_password", "")
    client.patch("/api/system/settings", json={"smtp_password": "hunter2"})
    # Stored as a SecretStr (masked in logs/reprs), unwrapped only on demand.
    assert settings.smtp_password.get_secret_value() == "hunter2"
    view = {i["key"]: i for i in client.get("/api/system/settings").json()["settings"]}
    assert view["smtp_password"]["value"] == "********"
    assert view["smtp_password"]["has_value"] is True
    # A blank/masked secret leaves the stored value unchanged.
    client.patch("/api/system/settings", json={"smtp_password": ""})
    assert settings.smtp_password.get_secret_value() == "hunter2"


def test_settings_env_locked_ignored(client, workspace, monkeypatch):
    monkeypatch.setenv("RT_INSTANCE_NAME", "PinnedByOps")
    monkeypatch.setattr(settings, "instance_name", "PinnedByOps")
    view = {i["key"]: i for i in client.get("/api/system/settings").json()["settings"]}
    assert view["instance_name"]["env_locked"] is True
    # A patch to an env-locked key is ignored.
    client.patch("/api/system/settings", json={"instance_name": "Nope"})
    assert settings.instance_name == "PinnedByOps"
    assert "instance_name" not in ss.load_overrides()


def test_public_config_no_auth(guest_client, monkeypatch):
    monkeypatch.setattr(settings, "instance_name", "Public Name")
    res = guest_client.get("/api/system/public-config")
    assert res.status_code == 200
    body = res.json()
    assert body["instance_name"] == "Public Name"
    assert "allow_self_registration" in body


def test_settings_require_admin(guest_client):
    assert guest_client.get("/api/system/settings").status_code == 403
    assert guest_client.patch("/api/system/settings", json={"instance_name": "x"}).status_code == 403


def test_apply_overrides_on_startup(workspace, monkeypatch):
    monkeypatch.setattr(settings, "instance_name", "reqmesh")
    ss.save_overrides({"instance_name": "From Disk"})
    ss.apply_overrides(settings)
    assert settings.instance_name == "From Disk"
