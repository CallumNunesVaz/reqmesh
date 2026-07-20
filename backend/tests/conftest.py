import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core import auth
from app.core.dependencies import require_edit, require_admin


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Isolate all filesystem side effects into a temp directory."""
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "git_autocommit", False)
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.yaml")
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "secret")
    monkeypatch.setattr(auth, "RESET_TOKENS_FILE", tmp_path / "reset_tokens.yaml")
    monkeypatch.setattr(auth, "VERIFY_TOKENS_FILE", tmp_path / "verify_tokens.yaml")
    monkeypatch.setattr(auth, "_secret_cache", None)
    from app.core import settings_store
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.yaml")
    return tmp_path


@pytest.fixture()
def client(workspace):
    """Client authenticated as an admin (auth dependencies overridden)."""
    admin = {"username": "tester", "role": "admin"}
    app.dependency_overrides[require_edit] = lambda: admin
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
def project(client):
    client.post("/api/projects", json={"id": "demo", "name": "Demo Project"})
    return "demo"


def make_req(client, project_id, req_id, **fields):
    body = {"id": req_id, "name": fields.pop("name", req_id), **fields}
    res = client.post(f"/api/projects/{project_id}/requirements", json=body)
    assert res.status_code == 201, res.text
    return res.json()
