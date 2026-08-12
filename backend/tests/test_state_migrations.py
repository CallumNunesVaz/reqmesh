"""The state directory's own migrations — accounts, secret, token stores.

Separate from the project-data migrator on purpose: the two directories have
independent lifetimes, and an operator restoring one must not mark the other's
migrations as done.
"""
from __future__ import annotations

import json
import os

import pytest

from app.services.state_migrations import (
    CURRENT_STATE_VERSION,
    _MARKER,
    read_state_version,
    run_state_migrations,
)


def test_a_fresh_state_dir_is_marked_without_running_anything(tmp_path):
    """No accounts yet means a new install: record the version, repair nothing."""
    summary = run_state_migrations(tmp_path)

    assert summary["migrated"] is False
    assert read_state_version(tmp_path) == CURRENT_STATE_VERSION


def test_a_legacy_dir_with_accounts_but_no_marker_is_migrated(tmp_path):
    """The opposite of the project migrator's assumption, deliberately: an
    unmarked state dir with accounts predates the framework and needs its
    repairs, all of which are idempotent."""
    (tmp_path / "users.yaml").write_text("admin: {}\n")

    summary = run_state_migrations(tmp_path)

    assert summary["migrated"] is True
    assert summary["from"] == 1


def test_plaintext_token_files_are_deleted(tmp_path):
    """Entries keyed by the raw token cannot be told apart from hashed keys, so
    they are dropped rather than upgraded. A live reset link stops working —
    which is the point: it was readable by anyone with the file."""
    (tmp_path / "users.yaml").write_text("admin: {}\n")
    (tmp_path / "reset_tokens.yaml").write_text("sometoken:\n  username: admin\n  expires: 99\n")
    (tmp_path / "verify_tokens.yaml").write_text("othertoken:\n  username: admin\n  expires: 99\n")

    run_state_migrations(tmp_path)

    assert not (tmp_path / "reset_tokens.yaml").exists()
    assert not (tmp_path / "verify_tokens.yaml").exists()


def test_a_world_readable_users_file_is_repaired(tmp_path):
    """An install whose users.yaml was created by the old bootstrap path took
    the umask. The migration tightens it without waiting for the next write."""
    users = tmp_path / "users.yaml"
    users.write_text("admin: {}\n")
    os.chmod(users, 0o644)

    run_state_migrations(tmp_path)

    assert users.stat().st_mode & 0o777 == 0o600


def test_the_marker_itself_is_private(tmp_path):
    run_state_migrations(tmp_path)
    assert (tmp_path / _MARKER).stat().st_mode & 0o777 == 0o600


def test_running_twice_is_a_no_op(tmp_path):
    (tmp_path / "users.yaml").write_text("admin: {}\n")
    run_state_migrations(tmp_path)

    second = run_state_migrations(tmp_path)

    assert second["migrated"] is False
    assert read_state_version(tmp_path) == CURRENT_STATE_VERSION


def test_an_unwritable_state_dir_does_not_raise(tmp_path):
    """Failing to repair is not a reason to refuse to serve."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "users.yaml").write_text("admin: {}\n")
    os.chmod(state, 0o500)
    try:
        summary = run_state_migrations(state)
        assert summary is not None
    finally:
        os.chmod(state, 0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_it_never_touches_the_data_root_marker(tmp_path):
    """The separation that makes two markers worth having: restoring project
    data from a backup must not mark the state dir's repairs as done."""
    state = tmp_path / "state"
    data = tmp_path / "projects"
    state.mkdir()
    data.mkdir()
    (data / ".reqmesh-schema.json").write_text(json.dumps({"schema_version": 1}))

    run_state_migrations(state)

    assert json.loads((data / ".reqmesh-schema.json").read_text())["schema_version"] == 1
    assert not (data / _MARKER).exists()
