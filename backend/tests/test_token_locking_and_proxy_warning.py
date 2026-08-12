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


# ── Tokens are bearer credentials, so the file must not hold usable copies ────

def test_a_reset_token_is_not_stored_in_plaintext(workspace):
    """The emailed token must not appear in the file it is checked against.

    Stored verbatim, anyone able to read reset_tokens.yaml — a stray backup, a
    misdirected volume mount — could set any account's password without knowing
    the old one.
    """
    auth.register_user("tokuser", "Password123!", "contributor")
    token = auth.create_reset_token("tokuser")

    raw = auth.RESET_TOKENS_FILE.read_text()
    assert token not in raw
    assert "tokuser" in raw, "the username is still needed to resolve the account"


def test_a_reset_token_read_from_the_file_cannot_be_replayed(workspace):
    """The account-takeover property, stated directly: what is on disk is not a
    credential. Replaying the stored key must fail while the real token works."""
    auth.register_user("replay", "Password123!", "contributor")
    token = auth.create_reset_token("replay")

    import re
    stored_key = re.findall(r"\b[0-9a-f]{64}\b", auth.RESET_TOKENS_FILE.read_text())
    assert len(stored_key) == 1, "expected exactly one hashed key on disk"

    assert auth.consume_reset_token(stored_key[0], "FromTheFile1!") is False
    assert auth.consume_reset_token(token, "TheRealToken1!") is True


def test_a_verification_token_is_not_stored_in_plaintext(workspace):
    auth.register_user("verifyuser", "Password123!", "contributor")
    token = auth.create_verify_token("verifyuser")

    assert token not in auth.VERIFY_TOKENS_FILE.read_text()
    assert auth.verify_email(token) == "verifyuser"


def test_token_stores_are_owner_only(workspace):
    auth.register_user("modeuser", "Password123!", "contributor")
    auth.create_reset_token("modeuser")
    auth.create_verify_token("modeuser")

    assert auth.RESET_TOKENS_FILE.stat().st_mode & 0o777 == 0o600
    assert auth.VERIFY_TOKENS_FILE.stat().st_mode & 0o777 == 0o600


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
