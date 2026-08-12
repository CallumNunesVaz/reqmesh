"""The password policy, and the property that makes extracting it worthwhile:
the API and the CLI agree.

The rules lived in the HTTP layer, so `reset-admin` checked length alone — an
operator could set out of band a password the web UI would have refused.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from app.cli import cli
from app.core import auth
from app.core.password_policy import MAX_PASSWORD_BYTES, validate_password

ACCEPTABLE = "Str0ng-Passphrase!"

REJECTED = [
    ("short", "Ab1!x", "at least 12"),
    ("no uppercase", "str0ng-passphrase!", "uppercase"),
    ("no lowercase", "STR0NG-PASSPHRASE!", "lowercase"),
    ("no digit", "Strong-Passphrase!", "digit"),
    ("no special", "Str0ngPassphrase1", "special"),
    ("over the bcrypt limit", "A1!" + "x" * MAX_PASSWORD_BYTES, "at most"),
]


@pytest.mark.parametrize("label,password,expected", REJECTED, ids=[r[0] for r in REJECTED])
def test_rejected_passwords(label, password, expected):
    problem = validate_password(password)
    assert problem is not None, f"{label} should be rejected"
    assert expected in problem


def test_an_acceptable_password_passes():
    assert validate_password(ACCEPTABLE) is None


def test_a_password_containing_the_username_is_rejected():
    assert "username" in (validate_password("Alice-Str0ng-Pass!", "alice") or "")
    assert validate_password("Alice-Str0ng-Pass!", "bob") is None


def test_the_username_check_ignores_case():
    assert validate_password("ALICE-Str0ng-Pass!", "alice") is not None


def test_the_bcrypt_limit_is_measured_in_bytes_not_characters():
    """A multi-byte password can pass the character count and still overflow
    bcrypt's 72-byte input, which bcrypt 5 raises on rather than truncating."""
    password = "Aa1!" + "é" * 40  # 44 chars, 84 bytes
    assert len(password) < MAX_PASSWORD_BYTES
    assert validate_password(password) is not None


# ── The API and the CLI must agree ───────────────────────────────────────────

@pytest.mark.parametrize("password", [r[1] for r in REJECTED], ids=[r[0] for r in REJECTED])
def test_the_api_rejects_what_the_policy_rejects(client, password):
    res = client.post("/api/auth/register",
                      json={"username": "newperson", "password": password})
    assert res.status_code == 400, res.text


@pytest.mark.parametrize("password", [r[1] for r in REJECTED], ids=[r[0] for r in REJECTED])
def test_the_cli_rejects_what_the_policy_rejects(workspace, password):
    auth.register_user("cliuser", ACCEPTABLE, "contributor")

    res = CliRunner().invoke(cli, ["reset-admin", "-u", "cliuser", "-p", password])

    assert res.exit_code == 1, res.output
    assert auth.authenticate("cliuser", ACCEPTABLE)["status"] == "ok", \
        "the original password must still work after a refused reset"
