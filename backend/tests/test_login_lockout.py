"""Per-IP login lockout: one origin must not lock an account it does not own.

The old logic counted failed logins purely per account, so anyone who knew a
username could keep it locked indefinitely from a single machine — the brute-
force mitigation was itself a denial of service. The fix adds a per-source
counter so a single origin trips its own limit first and is refused *without*
locking the account for everyone else, while the account-level counter remains
as the backstop for genuinely distributed attempts.
"""

import time

from app.core import auth
from app.core.config import settings


def _register(username="bob", password="GoodPass123!"):
    auth.register_user(username, password, "contributor")


def test_single_source_cannot_lock_account(workspace, monkeypatch):
    """The finding: one origin cannot lock an account it does not own.

    The attempt count deliberately runs well past ``lockout_max_attempts``. A
    weaker version of this test (five attempts against a backstop of twenty)
    passes against the old per-account-only logic too, because five never
    reached the threshold — so it would green-light a build that merely raised
    the number and never added per-source accounting. Thirty attempts from one
    IP locks the account under the old logic and must not under this one.
    """
    monkeypatch.setattr(settings, "lockout_max_attempts", 20)
    monkeypatch.setattr(settings, "lockout_per_ip_max_attempts", 5)
    _register()

    for _ in range(30):
        assert auth.authenticate("bob", "wrong", client_ip="203.0.113.9")["status"] == "invalid"

    # Account is not locked for anyone else.
    result = auth.authenticate("bob", "GoodPass123!", client_ip="203.0.113.10")
    assert result["status"] == "ok"
    assert int(auth.load_users()["bob"].get("locked_until", 0) or 0) == 0


def test_distributed_attempts_trip_account_backstop(workspace, monkeypatch):
    """Brute-force protection is not weakened: twenty failures spread across
    twenty distinct sources still lock the account for everybody."""
    monkeypatch.setattr(settings, "lockout_max_attempts", 20)
    monkeypatch.setattr(settings, "lockout_per_ip_max_attempts", 5)
    _register()

    for i in range(20):
        ip = f"198.51.100.{i + 1}"
        assert auth.authenticate("bob", "wrong", client_ip=ip)["status"] == "invalid"

    assert auth.authenticate("bob", "GoodPass123!", client_ip="198.51.100.99")["status"] == "locked"


def test_correct_login_resets_both_counters(workspace, monkeypatch):
    monkeypatch.setattr(settings, "lockout_max_attempts", 20)
    monkeypatch.setattr(settings, "lockout_per_ip_max_attempts", 5)
    _register()

    for _ in range(4):
        assert auth.authenticate("bob", "wrong", client_ip="203.0.113.9")["status"] == "invalid"
    assert auth._per_source_failures.get(("203.0.113.9", "bob")) == 4

    assert auth.authenticate("bob", "GoodPass123!", client_ip="203.0.113.9")["status"] == "ok"

    # Both counters reset: the per-source window and the account counter.
    assert auth._per_source_failures.get(("203.0.113.9", "bob")) is None
    assert int(auth.load_users()["bob"].get("failed_attempts", 0)) == 0

    # A fresh burst starts from zero, not four deep.
    for _ in range(4):
        assert auth.authenticate("bob", "wrong", client_ip="203.0.113.9")["status"] == "invalid"
    assert auth.authenticate("bob", "GoodPass123!", client_ip="203.0.113.10")["status"] == "ok"


def test_uniform_401_for_locked_wrong_and_unknown(guest_client, monkeypatch):
    """A locked account, a wrong password and an unknown user are all
    indistinguishable to the caller: same status, same body."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    _register()

    users = auth.load_users()
    users["bob"]["locked_until"] = int(time.time()) + 900
    auth.save_users(users)

    login = "/api/auth/login"
    wrong = guest_client.post(login, json={"username": "bob", "password": "nope"})
    unknown = guest_client.post(login, json={"username": "nobody", "password": "nope"})
    locked = guest_client.post(login, json={"username": "bob", "password": "GoodPass123!"})

    assert wrong.status_code == unknown.status_code == locked.status_code == 401
    assert wrong.json() == unknown.json() == locked.json()


def test_lock_expiry_after_window(workspace, monkeypatch):
    monkeypatch.setattr(settings, "lockout_max_attempts", 20)
    monkeypatch.setattr(settings, "lockout_per_ip_max_attempts", 5)
    monkeypatch.setattr(settings, "lockout_window_minutes", 15)
    _register()

    for i in range(20):
        auth.authenticate("bob", "wrong", client_ip=f"198.51.100.{i + 1}")
    assert auth.authenticate("bob", "GoodPass123!", client_ip="198.51.100.1")["status"] == "locked"

    # Fast-forward past the lockout window.
    users = auth.load_users()
    users["bob"]["locked_until"] = int(time.time()) - 1
    auth.save_users(users)

    assert auth.authenticate("bob", "GoodPass123!", client_ip="198.51.100.1")["status"] == "ok"
