"""The settings file lives beside the accounts, not in $HOME.

`settings_store` hardcoded `Path.home()`. Under Docker HOME is `/app` on a
read-only root filesystem, so every save raised and the admin Settings UI could
not persist anything — the same failure the auth files were moved off $HOME to
fix, missed for settings.

The fallback semantics must match `auth.py` exactly; `test_auth_state_dir.py` is
the other half of this pair.
"""
from __future__ import annotations

import importlib


def _reload_with(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("RT_STATE_DIR", raising=False)
    else:
        monkeypatch.setenv("RT_STATE_DIR", value)
    from app.core import paths, settings_store
    importlib.reload(paths)
    return importlib.reload(settings_store)


def test_the_settings_file_follows_rt_state_dir(tmp_path, monkeypatch):
    store = _reload_with(monkeypatch, str(tmp_path))
    try:
        assert store.SETTINGS_FILE == tmp_path / "settings.yaml"
    finally:
        _reload_with(monkeypatch, None)


def test_it_lands_beside_the_accounts_file(tmp_path, monkeypatch):
    """The property that matters operationally: one directory to back up, one
    to make writable, one to point at a durable volume."""
    store = _reload_with(monkeypatch, str(tmp_path))
    try:
        from app.core import auth
        auth_reloaded = importlib.reload(auth)
        assert store.SETTINGS_FILE.parent == auth_reloaded.USERS_FILE.parent
    finally:
        _reload_with(monkeypatch, None)
        from app.core import auth
        importlib.reload(auth)


def test_the_default_is_still_home(monkeypatch):
    from pathlib import Path

    store = _reload_with(monkeypatch, None)
    assert store.SETTINGS_FILE == Path.home() / ".reqmesh" / "settings.yaml"


def test_an_empty_state_dir_falls_back_to_home(monkeypatch):
    """Mirrors test_auth_state_dir.py: an empty value must not resolve to the
    filesystem root. The two modules share one resolver so they cannot drift."""
    from pathlib import Path

    store = _reload_with(monkeypatch, "")
    try:
        assert store.SETTINGS_FILE == Path.home() / ".reqmesh" / "settings.yaml"
    finally:
        _reload_with(monkeypatch, None)


def test_overrides_survive_a_write_and_reload(tmp_path, monkeypatch):
    store = _reload_with(monkeypatch, str(tmp_path))
    try:
        store.save_overrides({"instance_name": "Bench"})
        assert store.SETTINGS_FILE.exists()
        assert store.load_overrides().get("instance_name") == "Bench"
    finally:
        _reload_with(monkeypatch, None)


def test_a_legacy_home_settings_file_is_carried_forward(tmp_path, monkeypatch):
    """An operator upgrading from a build that wrote to $HOME keeps their SMTP
    configuration instead of silently losing it."""
    from app.services import state_migrations

    fake_home = tmp_path / "home"
    (fake_home / ".reqmesh").mkdir(parents=True)
    (fake_home / ".reqmesh" / "settings.yaml").write_text("instance_name: Legacy\n")
    monkeypatch.setenv("HOME", str(fake_home))

    state = tmp_path / "state"
    state.mkdir()
    (state / "users.yaml").write_text("admin: {}\n")

    state_migrations.run_state_migrations(state)

    assert (state / "settings.yaml").read_text() == "instance_name: Legacy\n"
    assert (fake_home / ".reqmesh" / "settings.yaml").exists(), "the original is left in place"


def test_carrying_forward_never_overwrites(tmp_path, monkeypatch):
    from app.services import state_migrations

    fake_home = tmp_path / "home"
    (fake_home / ".reqmesh").mkdir(parents=True)
    (fake_home / ".reqmesh" / "settings.yaml").write_text("instance_name: Legacy\n")
    monkeypatch.setenv("HOME", str(fake_home))

    state = tmp_path / "state"
    state.mkdir()
    (state / "users.yaml").write_text("admin: {}\n")
    (state / "settings.yaml").write_text("instance_name: Current\n")

    state_migrations.run_state_migrations(state)

    assert (state / "settings.yaml").read_text() == "instance_name: Current\n"
