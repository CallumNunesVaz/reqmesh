"""Where the account database lives.

``USERS_FILE`` defaulted to ``Path.home()/".reqmesh"``. In the Docker deployment
that resolved to ``/app/.reqmesh`` — a path the compose file covered with a
root-owned tmpfs while the container ran as uid 999 under a read-only rootfs. The
result on a real Ubuntu host was that login returned 500 with
``PermissionError: '/app/.reqmesh/users.yaml'``, and had the directory been
writable the accounts would still have been discarded on every restart, because
tmpfs is memory-backed.

``RT_STATE_DIR`` moves this to the same durable volume as the project data.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_auth(monkeypatch, state_dir: str | None):
    """Re-import app.core.auth with RT_STATE_DIR set (or not)."""
    if state_dir is None:
        monkeypatch.delenv("RT_STATE_DIR", raising=False)
    else:
        monkeypatch.setenv("RT_STATE_DIR", state_dir)
    from app.core import auth as auth_mod
    return importlib.reload(auth_mod)


@pytest.fixture(autouse=True)
def _restore_auth_module():
    """Leave the module as the rest of the suite expects it."""
    yield
    from app.core import auth as auth_mod
    importlib.reload(auth_mod)


def test_state_dir_env_redirects_every_auth_file(tmp_path, monkeypatch):
    auth = _reload_auth(monkeypatch, str(tmp_path / "state"))
    assert auth.USERS_FILE == tmp_path / "state" / "users.yaml"
    assert auth.SECRET_FILE == tmp_path / "state" / "secret"
    assert auth.RESET_TOKENS_FILE == tmp_path / "state" / "reset_tokens.yaml"
    assert auth.VERIFY_TOKENS_FILE == tmp_path / "state" / "verify_tokens.yaml"


def test_default_is_still_home(monkeypatch):
    """An existing bare-metal install must not have its accounts move."""
    auth = _reload_auth(monkeypatch, None)
    assert auth.USERS_FILE == Path.home() / ".reqmesh" / "users.yaml"


def test_empty_state_dir_falls_back_to_home(monkeypatch):
    """RT_STATE_DIR= in a .env must not resolve to the filesystem root."""
    auth = _reload_auth(monkeypatch, "")
    assert auth.USERS_FILE == Path.home() / ".reqmesh" / "users.yaml"


def test_users_can_actually_be_written_to_the_state_dir(tmp_path, monkeypatch):
    """The end-to-end failure was a write, not a path computation."""
    state = tmp_path / "state"
    auth = _reload_auth(monkeypatch, str(state))

    auth.register_user("alice", "Password123!", "admin")
    assert auth.USERS_FILE.exists(), "users.yaml was not created under RT_STATE_DIR"
    assert auth.authenticate("alice", "Password123!") is not None

    # The write must land in the state dir and nowhere near the real home
    # directory — the container case is precisely one where home is unwritable.
    assert auth.USERS_FILE.parent == state
    assert Path.home() not in auth.USERS_FILE.parents


def test_state_dir_survives_a_reload(tmp_path, monkeypatch):
    """A restart must find the accounts written before it.

    This is the property tmpfs silently broke: the file was written, the process
    restarted, and the account was gone.
    """
    state = tmp_path / "state"
    auth = _reload_auth(monkeypatch, str(state))
    auth.register_user("bob", "Password123!", "maintainer")
    # The account has to be *in the durable location* for surviving a restart to
    # mean anything: writing it to a tmpfs also "survives" a module reload, which
    # is exactly why the container bug went unnoticed.
    assert auth.USERS_FILE.parent == state, \
        f"account written to {auth.USERS_FILE}, not the configured state dir"

    auth = _reload_auth(monkeypatch, str(state))   # simulate the restart
    assert auth.authenticate("bob", "Password123!") is not None, \
        "account did not survive the restart"
