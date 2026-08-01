"""`app.cli reset-admin` — the recovery path for a lost admin password.

Before this existed the documented recovery was "reset it from the
container/host shell", with no command to run: RT_ADMIN_PASSWORD is only
applied when users.yaml is absent, so on any later deploy the configured
password silently does not work, and with SMTP disabled forgot-password is
unavailable too. The only route left was hand-editing YAML.
"""

import time

import pytest
from click.testing import CliRunner

from app.cli import cli
from app.core import auth


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A users file with an admin and a contributor, isolated from the host."""
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.yaml")
    auth.save_users({
        "admin": {"username": "admin", "role": "admin",
                  "password_hash": auth.hash_password("original-password").decode()},
        "bob": {"username": "bob", "role": "contributor",
                "password_hash": auth.hash_password("bobs-password-12").decode()},
    })
    return tmp_path


def test_resets_the_password(seeded):
    res = CliRunner().invoke(cli, ["reset-admin", "--password", "a-new-password"])
    assert res.exit_code == 0, res.output

    user = auth.load_users()["admin"]
    assert auth.verify_password("a-new-password", user["password_hash"])
    assert not auth.verify_password("original-password", user["password_hash"])


def test_clears_the_lockout(seeded):
    """Five failed logins lock an account for fifteen minutes. Resetting without
    clearing that leaves the new password rejected and looking just as broken."""
    users = auth.load_users()
    users["admin"]["failed_attempts"] = 5
    users["admin"]["locked_until"] = int(time.time()) + 900
    users["admin"]["disabled"] = True
    auth.save_users(users)

    CliRunner().invoke(cli, ["reset-admin", "--password", "a-new-password"])

    user = auth.load_users()["admin"]
    assert user["failed_attempts"] == 0
    assert "locked_until" not in user
    assert user["disabled"] is False


def test_does_not_force_another_password_change(seeded):
    """This is a deliberate recovery by the operator, not provisioning."""
    users = auth.load_users()
    users["admin"]["password_change_required"] = True
    auth.save_users(users)

    CliRunner().invoke(cli, ["reset-admin", "--password", "a-new-password"])
    assert auth.load_users()["admin"]["password_change_required"] is False


def test_can_target_any_account(seeded):
    res = CliRunner().invoke(cli, ["reset-admin", "-u", "bob", "-p", "bobs-new-password"])
    assert res.exit_code == 0
    assert auth.verify_password("bobs-new-password", auth.load_users()["bob"]["password_hash"])
    # and leaves the others alone
    assert auth.verify_password("original-password", auth.load_users()["admin"]["password_hash"])


def test_rejects_a_short_password(seeded):
    res = CliRunner().invoke(cli, ["reset-admin", "--password", "short"])
    assert res.exit_code != 0
    assert "12 characters" in res.output
    assert auth.verify_password("original-password", auth.load_users()["admin"]["password_hash"])


def test_unknown_account_lists_what_exists(seeded):
    """A typo should not read as "the accounts file is empty"."""
    res = CliRunner().invoke(cli, ["reset-admin", "-u", "nope", "-p", "a-new-password"])
    assert res.exit_code != 0
    assert "admin" in res.output and "bob" in res.output


def test_make_admin_restores_the_role(seeded):
    res = CliRunner().invoke(cli, ["reset-admin", "-u", "bob", "-p", "bobs-new-password",
                                   "--make-admin"])
    assert res.exit_code == 0
    assert auth.load_users()["bob"]["role"] == "admin"


def test_role_is_left_alone_without_the_flag(seeded):
    CliRunner().invoke(cli, ["reset-admin", "-u", "bob", "-p", "bobs-new-password"])
    assert auth.load_users()["bob"]["role"] == "contributor"


def test_the_reset_password_actually_authenticates(seeded):
    """End to end through authenticate_user, including its lockout handling."""
    CliRunner().invoke(cli, ["reset-admin", "--password", "a-new-password"])
    result = auth.authenticate("admin", "a-new-password")
    assert result["status"] == "ok", result
