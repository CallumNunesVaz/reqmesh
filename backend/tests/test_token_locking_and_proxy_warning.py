"""FAB-3 (token-store locking, deadlock-free) and FAB-5 (proxy-trust warning)."""

import logging
import queue
import threading

from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import settings
from app.main import app


# ── FAB-3: reset/verify token stores are locked, without deadlocking ────────────


def test_reset_token_round_trip(workspace):
    """A created reset token consumes once and actually sets the new password."""
    auth.register_user("alice", "OldPassw0rd!", "contributor")
    token = auth.create_reset_token("alice")
    assert token
    assert auth.consume_reset_token(token, "NewPassw0rd!") is True
    # Burned: a second consume fails.
    assert auth.consume_reset_token(token, "Whatever123!") is False
    # The password really changed.
    assert auth.authenticate("alice", "NewPassw0rd!")["status"] == "ok"
    assert auth.authenticate("alice", "OldPassw0rd!")["status"] == "invalid"


def test_expired_reset_token_is_rejected_and_removed(workspace, monkeypatch):
    auth.register_user("bob", "OldPassw0rd!", "contributor")
    # Force a stored token to be already expired.
    monkeypatch.setattr(auth, "RESET_TOKEN_TTL", -1)
    token = auth.create_reset_token("bob")
    assert auth.consume_reset_token(token, "NewPassw0rd!") is False


def test_no_deadlock_under_concurrent_invite_and_consume(workspace):
    """The lock-order landmine: create_invited_user holds users_lock then takes
    the reset-token lock (users → token), while consume_reset_token must take the
    token lock then set_user_password (which takes users_lock). If consume held
    the token lock across that call the two orders would invert and deadlock.
    Run both paths concurrently and require every thread to finish.
    """
    auth.register_user("seed", "Password123!", "admin")
    tokens: "queue.Queue[str]" = queue.Queue()
    errors: list = []
    stop = threading.Event()

    def inviter(i: int) -> None:
        try:
            for j in range(25):
                tok = auth.create_invited_user(f"inv{i}_{j}", "contributor")
                if tok:
                    tokens.put(tok)
        except Exception as exc:  # noqa: BLE001 - surfaced to the assertion
            errors.append(exc)

    def consumer() -> None:
        try:
            while not stop.is_set() or not tokens.empty():
                try:
                    tok = tokens.get(timeout=0.05)
                except queue.Empty:
                    continue
                auth.consume_reset_token(tok, "NewPassw0rd!")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    inv = [threading.Thread(target=inviter, args=(i,)) for i in range(3)]
    con = [threading.Thread(target=consumer) for _ in range(3)]
    for t in con:
        t.start()
    for t in inv:
        t.start()
    for t in inv:
        t.join(timeout=20)
    stop.set()
    for t in con:
        t.join(timeout=20)

    alive = [t for t in inv + con if t.is_alive()]
    assert not alive, "threads did not finish within 20s — probable deadlock"
    assert not errors, f"unexpected errors: {errors}"


def test_verify_email_still_verifies(workspace):
    """The added inner lock in verify_email must not change its behaviour."""
    auth.register_user("carol", "Password123!", "contributor")
    token = auth.create_verify_token("carol")
    assert token
    assert auth.verify_email(token) == "carol"
    users = auth.load_users()
    assert users["carol"]["email_verified"] is True
    # Single-use.
    assert auth.verify_email(token) is None


# ── FAB-5: startup warning when X-Forwarded-For is trusted broadly ──────────────


def _run_lifespan(monkeypatch, cidr: str):
    from app.core import rate_limit
    monkeypatch.setattr(settings, "require_auth", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "proxy_trusted_cidr", cidr)
    rate_limit._trusted_proxies._cache = None  # bust the parsed-CIDR cache
    with TestClient(app):
        pass


def test_proxy_warning_fires_for_non_loopback(workspace, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="security"):
        _run_lifespan(monkeypatch, "10.0.0.0/8")
    assert any(
        "X-Forwarded-For is trusted from non-loopback" in r.getMessage()
        for r in caplog.records
    )


def test_proxy_warning_silent_for_loopback_only(workspace, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="security"):
        _run_lifespan(monkeypatch, "127.0.0.0/8")
    assert not any(
        "X-Forwarded-For is trusted from non-loopback" in r.getMessage()
        for r in caplog.records
    )
