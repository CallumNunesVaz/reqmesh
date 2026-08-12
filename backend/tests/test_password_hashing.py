"""Password hashing: the work factor, and how it moves forward.

The work factor is meant to rise as hardware gets cheaper. These tests pin the
mechanism that lets it rise without a flag day — verification dispatches on the
stored hash's format, and a stale hash is upgraded at the next successful login,
the only moment the plaintext is legitimately in hand.
"""
from __future__ import annotations

import bcrypt

from app.core import auth


def _stored_hash(username: str) -> str:
    return auth.load_users()[username]["password_hash"]


def _cost(hashed: str) -> int:
    return int(hashed.split("$")[2])


def test_a_new_hash_uses_the_declared_work_factor(workspace):
    auth.register_user("fresh", "Password123!", "contributor")
    assert _cost(_stored_hash("fresh")) == auth.BCRYPT_ROUNDS


def test_a_weaker_hash_is_upgraded_on_a_successful_login(workspace):
    """The upgrade path. A hash written when the cost was lower is replaced,
    and the same password keeps working across the change."""
    auth.register_user("legacy", "Password123!", "contributor")
    users = auth.load_users()
    users["legacy"]["password_hash"] = bcrypt.hashpw(b"Password123!", bcrypt.gensalt(rounds=4)).decode()
    auth.save_users(users)

    assert auth.authenticate("legacy", "Password123!")["status"] == "ok"

    assert _cost(_stored_hash("legacy")) == auth.BCRYPT_ROUNDS
    assert auth.authenticate("legacy", "Password123!")["status"] == "ok"


def test_a_current_hash_is_not_rewritten(workspace):
    """No gratuitous rehash: every login would otherwise pay for a bcrypt hash
    it does not need, inside the users lock."""
    auth.register_user("current", "Password123!", "contributor")
    before = _stored_hash("current")

    auth.authenticate("current", "Password123!")

    assert _stored_hash("current") == before


def test_a_failed_login_never_rehashes(workspace):
    auth.register_user("wrongpw", "Password123!", "contributor")
    before = _stored_hash("wrongpw")

    assert auth.authenticate("wrongpw", "NotThePassword1!")["status"] == "invalid"

    assert _stored_hash("wrongpw") == before


def test_an_unrecognised_hash_fails_closed(workspace):
    """A corrupted record is a failed login, not a 500. bcrypt raises on input
    it cannot parse, and that reached the login path."""
    assert auth.verify_password("anything", "not-a-bcrypt-hash") is False
    assert auth.verify_password("anything", "") is False


def test_a_corrupted_record_cannot_crash_the_login_path(workspace):
    auth.register_user("corrupt", "Password123!", "contributor")
    users = auth.load_users()
    users["corrupt"]["password_hash"] = "$2b$truncated"
    auth.save_users(users)

    assert auth.authenticate("corrupt", "Password123!")["status"] == "invalid"


def test_needs_rehash_agrees_with_what_hash_password_produces(workspace):
    """The invariant that keeps the two functions from drifting apart."""
    assert auth.needs_rehash(auth.hash_password("Password123!").decode()) is False
    assert auth.needs_rehash(bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=4)).decode()) is True
    assert auth.needs_rehash("garbage") is True
