"""User-management features: lockout, disable, invite, force-logout, bulk, CSV."""

from app.core import auth
from app.core.config import settings
from app.core.rate_limit import _window_attempts


def _clear_rate_limit():
    _window_attempts.clear()


# ── Lockout & disable (exercised at the auth layer directly) ─────────────────

def test_lockout_after_failed_attempts(workspace, monkeypatch):
    monkeypatch.setattr(settings, "lockout_max_attempts", 3)
    monkeypatch.setattr(settings, "lockout_window_minutes", 15)
    auth.register_user("bob", "GoodPass123!", "editor")

    for _ in range(3):
        assert auth.authenticate("bob", "wrong")["status"] == "invalid"
    # Now locked, even with the right password.
    locked = auth.authenticate("bob", "GoodPass123!")
    assert locked["status"] == "locked"

    assert auth.unlock_user("bob")
    assert auth.authenticate("bob", "GoodPass123!")["status"] == "ok"


def test_disabled_account_cannot_login(workspace):
    auth.register_user("bob", "GoodPass123!", "editor")
    auth.set_user_disabled("bob", True)
    assert auth.authenticate("bob", "GoodPass123!")["status"] == "disabled"
    auth.set_user_disabled("bob", False)
    assert auth.authenticate("bob", "GoodPass123!")["status"] == "ok"


def test_login_survives_password_reset(workspace):
    """Regression: a token minted at login must carry the stored token_version,
    or it is invalid the moment a prior reset bumped that version."""
    auth.register_user("bob", "GoodPass123!", "editor")
    auth.set_user_password("bob", "NewPass456!")  # bumps token_version to 1
    res = auth.authenticate("bob", "NewPass456!")
    assert res["status"] == "ok"
    assert auth.get_user_from_token(res["token"]) is not None


# ── Admin endpoints ──────────────────────────────────────────────────────────

def test_disable_endpoint_guards(client):
    auth.register_user("bob", "GoodPass123!", "editor")
    assert client.post("/api/auth/users/bob/disable", json={"disabled": True}).status_code == 200
    # cannot disable self (fixture admin is "tester")
    auth.register_user("tester", "GoodPass123!", "admin")
    res = client.post("/api/auth/users/tester/disable", json={"disabled": True})
    assert res.status_code == 400


def test_force_logout_revokes_tokens(client, workspace):
    reg = auth.register_user("bob", "GoodPass123!", "editor")
    token = reg["token"]
    assert auth.get_user_from_token(token) is not None
    assert client.post("/api/auth/users/bob/logout").status_code == 200
    assert auth.get_user_from_token(token) is None  # revoked


def test_invite_returns_link_without_smtp(client, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")  # not configured
    res = client.post("/api/auth/users/invite",
                      json={"username": "carol", "email": "carol@example.com", "role": "editor"})
    assert res.status_code == 201
    body = res.json()
    assert body["emailed"] is False
    assert "reset-password?token=" in body["invite_link"]
    # The invited user exists and is flagged.
    assert auth.load_users()["carol"]["invited"] is True


def test_bulk_disable_and_delete(client):
    for name in ("u1", "u2", "u3"):
        auth.register_user(name, "GoodPass123!", "editor")
    res = client.post("/api/auth/users/bulk", json={"usernames": ["u1", "u2"], "action": "disable"})
    assert set(res.json()["applied"]) == {"u1", "u2"}
    assert auth.load_users()["u1"]["disabled"] is True
    res = client.post("/api/auth/users/bulk", json={"usernames": ["u3"], "action": "delete"})
    assert res.json()["applied"] == ["u3"]
    assert "u3" not in auth.load_users()


def test_csv_export_then_import(client):
    auth.register_user("alice", "GoodPass123!", "editor")
    csv_text = client.get("/api/auth/users/export").text
    assert "username" in csv_text and "alice" in csv_text

    new_csv = "username,full_name,email,role\ndave,Dave D,dave@example.com,viewer\n"
    res = client.post("/api/auth/users/import", json={"csv": new_csv})
    body = res.json()
    assert "dave" in body["created"]
    assert auth.load_users()["dave"]["role"] == "viewer"
    assert auth.load_users()["dave"]["invited"] is True


def test_self_registration_toggle(guest_client, monkeypatch):
    _clear_rate_limit()
    monkeypatch.setattr(settings, "allow_self_registration", False)
    res = guest_client.post("/api/auth/register",
                            json={"username": "newbie", "password": "GoodPass123!"})
    assert res.status_code == 403
    _clear_rate_limit()
    monkeypatch.setattr(settings, "allow_self_registration", True)
    res = guest_client.post("/api/auth/register",
                            json={"username": "newbie", "password": "GoodPass123!"})
    assert res.status_code == 200
