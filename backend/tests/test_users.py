"""Tests for admin user management (/auth/users)."""

from __future__ import annotations


def test_list_users_returns_default_admin(client):
    res = client.get("/api/auth/users")
    assert res.status_code == 200
    users = res.json()
    names = {u["username"] for u in users}
    assert "admin" in names
    admin = next(u for u in users if u["username"] == "admin")
    assert admin["role"] == "admin"
    assert "password_hash" not in admin  # never leak hashes


def test_create_standard_user(client):
    res = client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "editor"
    names = {u["username"] for u in client.get("/api/auth/users").json()}
    assert "bob" in names


def test_create_admin_user(client):
    res = client.post("/api/auth/users", json={"username": "alice", "password": "TestPass1!secure", "role": "admin"})
    assert res.status_code == 201
    assert res.json()["role"] == "admin"


def test_create_rejects_short_password(client):
    res = client.post("/api/auth/users", json={"username": "bob", "password": "Sh1!", "role": "editor"})
    assert res.status_code == 400


def test_create_rejects_bad_username(client):
    res = client.post("/api/auth/users", json={"username": "a b!", "password": "TestPass1!secure", "role": "editor"})
    assert res.status_code == 400


def test_create_rejects_invalid_role(client):
    res = client.post("/api/auth/users", json={"username": "bobby", "password": "TestPass1!secure", "role": "superuser"})
    assert res.status_code == 400


def test_create_duplicate_conflicts(client):
    client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    res = client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    assert res.status_code == 409


def test_change_role(client):
    client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    res = client.patch("/api/auth/users/bob", json={"role": "admin"})
    assert res.status_code == 200
    assert res.json()["role"] == "admin"


def test_reset_password_then_login(client):
    client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    res = client.patch("/api/auth/users/bob", json={"password": "NewPass2!secure"})
    assert res.status_code == 200
    # Login goes through real authentication against the users file.
    login = client.post("/api/auth/login", json={"username": "bob", "password": "NewPass2!secure"})
    assert login.status_code == 200
    assert login.json()["role"] == "editor"


def test_cannot_demote_last_admin(client):
    # Default workspace has exactly one admin ("admin").
    res = client.patch("/api/auth/users/admin", json={"role": "editor"})
    assert res.status_code == 400
    assert "last administrator" in res.json()["detail"].lower()


def test_cannot_delete_last_admin(client):
    res = client.delete("/api/auth/users/admin")
    assert res.status_code == 400


def test_cannot_delete_self(client):
    # The overridden admin identity is "tester"; create that account then try
    # to delete it — a second admin ("admin") exists so only the self-guard fires.
    client.post("/api/auth/users", json={"username": "tester", "password": "TestPass1!secure", "role": "admin"})
    res = client.delete("/api/auth/users/tester")
    assert res.status_code == 400
    assert "your own account" in res.json()["detail"].lower()


def test_delete_user(client):
    client.post("/api/auth/users", json={"username": "bob", "password": "TestPass1!secure", "role": "editor"})
    res = client.delete("/api/auth/users/bob")
    assert res.status_code == 200
    names = {u["username"] for u in client.get("/api/auth/users").json()}
    assert "bob" not in names


def test_delete_missing_user(client):
    res = client.delete("/api/auth/users/nobody")
    assert res.status_code == 404


def test_non_admin_cannot_list_users(guest_client):
    res = guest_client.get("/api/auth/users")
    assert res.status_code == 403
