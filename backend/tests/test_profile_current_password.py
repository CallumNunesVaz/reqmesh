"""Current-password confirmation for password and email changes.

Changing the password or email on `PATCH /auth/profile` now requires proof the
caller knows the existing password, so a stolen or left-open session can no
longer take the account over permanently. These tests use the real-role auth
fixtures so the token → user chain (and token_version invalidation) runs for
real, and assert against `auth.load_users()` where the stored record matters.
"""

from app.core import auth

PASSWORD = "Password123!long"
NEW_PASSWORD = "NewPassword123!"


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _set_email(username, email):
    users = auth.load_users()
    users[username]["email"] = email
    users[username]["email_verified"] = True
    auth.save_users(users)


def test_password_change_with_correct_current_password(_real_role_client, guest_client):
    c = _real_role_client("contributor", "alice")
    res = c.patch("/api/auth/profile",
                  json={"password": NEW_PASSWORD, "current_password": PASSWORD})
    assert res.status_code == 200, res.text

    assert _login(guest_client, "alice", NEW_PASSWORD).status_code == 200
    assert _login(guest_client, "alice", PASSWORD).status_code == 401


def test_password_change_without_current_password(_real_role_client, guest_client):
    c = _real_role_client("contributor", "bob")
    res = c.patch("/api/auth/profile", json={"password": NEW_PASSWORD})
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "Current password is required to change your password or email address"
    )
    assert _login(guest_client, "bob", PASSWORD).status_code == 200


def test_password_change_with_wrong_current_password(_real_role_client, guest_client):
    c = _real_role_client("contributor", "carol")
    res = c.patch("/api/auth/profile",
                  json={"password": NEW_PASSWORD, "current_password": "not-the-password"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Current password is incorrect"
    assert _login(guest_client, "carol", PASSWORD).status_code == 200


def test_email_change_without_current_password(_real_role_client):
    c = _real_role_client("contributor", "dave")
    _set_email("dave", "old@example.com")

    res = c.patch("/api/auth/profile", json={"email": "new@example.com"})
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "Current password is required to change your password or email address"
    )
    assert auth.load_users()["dave"]["email"] == "old@example.com"


def test_email_change_with_correct_current_password(_real_role_client):
    c = _real_role_client("contributor", "erin")
    _set_email("erin", "old@example.com")

    res = c.patch("/api/auth/profile",
                  json={"email": "new@example.com", "current_password": PASSWORD})
    assert res.status_code == 200, res.text
    stored = auth.load_users()["erin"]
    assert stored["email"] == "new@example.com"
    assert stored["email_verified"] is False


def test_email_set_to_same_value_needs_no_current_password(_real_role_client):
    c = _real_role_client("contributor", "frank")
    _set_email("frank", "same@example.com")

    res = c.patch("/api/auth/profile", json={"email": "same@example.com"})
    assert res.status_code == 200, res.text
    stored = auth.load_users()["frank"]
    assert stored["email"] == "same@example.com"
    assert stored["email_verified"] is True


def test_full_name_only_update_needs_no_current_password(_real_role_client):
    c = _real_role_client("contributor", "grace")
    res = c.patch("/api/auth/profile", json={"full_name": "Grace Hopper"})
    assert res.status_code == 200, res.text
    assert auth.load_users()["grace"]["full_name"] == "Grace Hopper"


def test_wrong_current_password_with_full_name_change_mutates_nothing(_real_role_client):
    c = _real_role_client("contributor", "heidi")
    res = c.patch("/api/auth/profile",
                  json={"full_name": "Hijacked", "current_password": "not-the-password"})
    assert res.status_code == 403
    assert res.json()["detail"] == "Current password is incorrect"
    assert auth.load_users()["heidi"]["full_name"] != "Hijacked"
