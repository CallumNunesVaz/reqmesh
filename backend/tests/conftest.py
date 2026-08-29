import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core import auth
from app.core.dependencies import require_edit, require_maintain, require_maintain_global, require_admin


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Isolate all filesystem side effects into a temp directory."""
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "git_autocommit", False)
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "allow_self_registration", True)
    monkeypatch.setattr(settings, "require_auth", False)
    # Reset module-level rate limiter state so tests don't interfere with
    # each other through the shared in-memory counters.
    from app.core import rate_limit
    rate_limit._window_attempts.clear()
    rate_limit._last_eviction = 0.0
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.yaml")
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "secret")
    monkeypatch.setattr(auth, "RESET_TOKENS_FILE", tmp_path / "reset_tokens.yaml")
    monkeypatch.setattr(auth, "VERIFY_TOKENS_FILE", tmp_path / "verify_tokens.yaml")
    monkeypatch.setattr(auth, "_secret_cache", None)
    # Per-source lockout counters are in-memory; reset them like the rate
    # limiter's buckets so tests don't bleed failed-login state into each other.
    auth._per_source_failures.clear()
    from app.core import settings_store
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.yaml")
    return tmp_path


@pytest.fixture()
def client(workspace):
    """Client authenticated as an admin (auth dependencies overridden)."""
    admin = {"username": "tester", "role": "admin"}
    app.dependency_overrides[require_edit] = lambda: admin
    app.dependency_overrides[require_maintain] = lambda: admin
    app.dependency_overrides[require_maintain_global] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def guest_client(workspace):
    """Client with no credentials — resolves to the guest/viewer role."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def _real_role_client(workspace):
    """Factory for a client that carries a real token for *role*.

    Deliberately installs **no** dependency overrides. The admin `client`
    fixture can override every guard because an admin genuinely passes them
    all; doing the same for a contributor produces a fixture that satisfies
    `require_admin`, so a test asserting "a contributor cannot do X" would pass
    no matter what the guards actually do. These go through the real
    dependency chain so the tiers mean something.
    """
    from app.core import auth

    def _make(role: str, username: str | None = None):
        name = username or role
        auth.register_user(name, "Password123!long", role)
        c = TestClient(app)
        c.headers.update({"Authorization": f"Bearer {auth.create_token(name, role)}"})
        return c

    return _make


@pytest.fixture()
def contributor_client(_real_role_client):
    """Contributor: may propose (change requests, risks, comments), not edit."""
    with _real_role_client("contributor") as c:
        yield c


@pytest.fixture()
def maintainer_client(_real_role_client):
    """Maintainer: may edit project data, but is not an admin."""
    with _real_role_client("maintainer") as c:
        yield c


@pytest.fixture()
def project(client):
    client.post("/api/projects", json={"id": "demo", "name": "Demo Project"})
    # Naming enforcement defaults to on, which would reject the readable
    # hand-written ids this suite uses ("SYS", "WING", "REQ-OLD"…). Turn it off
    # so the existing tests keep exercising the behaviour they were written for;
    # test_naming.py turns it back on where it tests enforcement itself.
    client.patch("/api/projects/demo", json={"naming": {"enforce": False}})
    return "demo"


def make_req(client, project_id, req_id, **fields):
    body = {"id": req_id, "name": fields.pop("name", req_id), **fields}
    res = client.post(f"/api/projects/{project_id}/requirements", json=body)
    assert res.status_code == 201, res.text
    return res.json()
