"""Tests for CRUD and orchestration of project system states."""
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.yaml_store import YamlStore


def _store(project_id: str) -> YamlStore:
    return YamlStore(Path(settings.data_root) / project_id)


def _names(client, project) -> list[str]:
    data = client.get(f"/api/projects/{project}/system-states").json()
    return [s["name"] for s in data["states"]]


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_state(client, project):
    res = client.post(f"/api/projects/{project}/system-states",
                      json={"name": "takeoff", "description": "Take-off phase"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "takeoff"
    assert data["description"] == "Take-off phase"
    assert data["order"] == 1


def test_create_duplicate_is_409(client, project):
    client.post(f"/api/projects/{project}/system-states",
                json={"name": "takeoff"})
    res = client.post(f"/api/projects/{project}/system-states",
                      json={"name": "takeoff"})
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_create_empty_name_is_400(client, project):
    for bad in ("", "   "):
        res = client.post(f"/api/projects/{project}/system-states",
                          json={"name": bad})
        assert res.status_code == 400
        assert "required" in res.json()["detail"]


# ── List & order ──────────────────────────────────────────────────────────────

def test_list_in_creation_order(client, project):
    client.post(f"/api/projects/{project}/system-states", json={"name": "Z"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "A"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "M"})

    data = client.get(f"/api/projects/{project}/system-states").json()
    names = [s["name"] for s in data["states"]]
    assert names == ["Z", "A", "M"]


def test_order_is_1_based(client, project):
    client.post(f"/api/projects/{project}/system-states", json={"name": "A"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "B"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "C"})

    data = client.get(f"/api/projects/{project}/system-states").json()
    orders = [(s["name"], s["order"]) for s in data["states"]]
    assert orders == [("A", 1), ("B", 2), ("C", 3)]


def test_order_is_never_written_to_meta_yaml(client, project):
    """``order`` is derived, not stored — assert on the file on disk."""
    client.post(f"/api/projects/{project}/system-states", json={"name": "S1"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "S2"})

    meta = _store(project).read_meta()
    stored = meta["system_states"]
    for d in stored:
        assert "order" not in d, f"order was written to _meta.yaml: {d}"


def test_legacy_bare_string_loads(client, project):
    """A bare string in _meta.yaml still shows up as a definition."""
    store = _store(project)
    meta = store.read_meta()
    meta["system_states"] = ["takeoff", "cruise", "landing"]
    store.write_meta(meta)

    data = client.get(f"/api/projects/{project}/system-states").json()
    names = [s["name"] for s in data["states"]]
    assert names == ["takeoff", "cruise", "landing"]

    # Also via the project endpoint.
    project_data = client.get(f"/api/projects/{project}").json()
    project_names = [s["name"] for s in project_data["system_states"]]
    assert project_names == ["takeoff", "cruise", "landing"]


# ── Patch ─────────────────────────────────────────────────────────────────────

def test_patch_description(client, project):
    client.post(f"/api/projects/{project}/system-states",
                json={"name": "takeoff", "description": "old"})
    res = client.patch(f"/api/projects/{project}/system-states/takeoff",
                       json={"description": "Take-off phase"})
    assert res.status_code == 200
    assert res.json()["description"] == "Take-off phase"
    assert res.json()["name"] == "takeoff"


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_state(client, project):
    from .conftest import make_req

    client.post(f"/api/projects/{project}/system-states",
                json={"name": "takeoff"})
    make_req(client, project, "R001", system_states=["takeoff"])

    res = client.delete(f"/api/projects/{project}/system-states/takeoff")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "takeoff"
    assert body["requirements_cleared"] == 1

    # The name is now an orphan.
    data = client.get(f"/api/projects/{project}/system-states").json()
    assert "takeoff" in data["orphans"]
    # The requirement still holds it.
    req = client.get(f"/api/projects/{project}/requirements/R001").json()
    assert "takeoff" in req["system_states"]


# ── Orphans ───────────────────────────────────────────────────────────────────

def test_orphan_appears_when_used_but_not_defined(client, project):
    from .conftest import make_req

    make_req(client, project, "R001", system_states=["hover"])
    data = client.get(f"/api/projects/{project}/system-states").json()
    assert "hover" in data["orphans"]
    assert data["states"] == []


def test_defined_state_not_in_orphans(client, project):
    from .conftest import make_req

    client.post(f"/api/projects/{project}/system-states", json={"name": "cruise"})
    make_req(client, project, "R001", system_states=["cruise"])

    data = client.get(f"/api/projects/{project}/system-states").json()
    assert "cruise" not in data["orphans"]


# ── Rename cascade ────────────────────────────────────────────────────────────

def test_rename_cascades_to_requirements(client, project):
    from .conftest import make_req

    client.post(f"/api/projects/{project}/system-states",
                json={"name": "takeoff"})
    make_req(client, project, "R001", system_states=["takeoff", "cruise"])
    make_req(client, project, "R002", system_states=["takeoff"])

    res = client.patch(f"/api/projects/{project}/system-states/takeoff",
                       json={"name": "launch"})
    assert res.status_code == 200
    assert res.json()["old_name"] == "takeoff"
    assert res.json()["name"] == "launch"
    assert res.json()["requirements_updated"] == 2

    r1 = client.get(f"/api/projects/{project}/requirements/R001").json()
    assert r1["system_states"] == ["launch", "cruise"]

    r2 = client.get(f"/api/projects/{project}/requirements/R002").json()
    assert r2["system_states"] == ["launch"]

    # The old name is not an orphan.
    data = client.get(f"/api/projects/{project}/system-states").json()
    assert "takeoff" not in data["orphans"]
    assert "launch" not in data["orphans"]


def test_rename_duplicate_is_409(client, project):
    client.post(f"/api/projects/{project}/system-states", json={"name": "A"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "B"})
    res = client.patch(f"/api/projects/{project}/system-states/A",
                       json={"name": "B"})
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_patch_empty_name_is_400(client, project):
    client.post(f"/api/projects/{project}/system-states", json={"name": "A"})
    res = client.patch(f"/api/projects/{project}/system-states/A",
                       json={"name": "   "})
    assert res.status_code == 400
    assert "required" in res.json()["detail"]


# ── Reorder ───────────────────────────────────────────────────────────────────

def test_reorder_happy_path(client, project):
    for name in ("takeoff", "cruise", "landing"):
        client.post(f"/api/projects/{project}/system-states", json={"name": name})

    res = client.put(f"/api/projects/{project}/system-states/order", json={
        "names": ["landing", "takeoff", "cruise"],
    })
    assert res.status_code == 200
    returned = [s["name"] for s in res.json()["states"]]
    assert returned == ["landing", "takeoff", "cruise"]
    assert [s["order"] for s in res.json()["states"]] == [1, 2, 3]

    # Reading back confirms the new order.
    assert _names(client, project) == ["landing", "takeoff", "cruise"]
    orders = [s["order"] for s in client.get(f"/api/projects/{project}/system-states").json()["states"]]
    assert orders == [1, 2, 3]


def test_reorder_missing_name(client, project):
    for name in ("A", "B"):
        client.post(f"/api/projects/{project}/system-states", json={"name": name})
    res = client.put(f"/api/projects/{project}/system-states/order", json={
        "names": ["A"],  # missing B
    })
    assert res.status_code == 400
    assert "must list every defined system state exactly once" in res.json()["detail"]
    assert _names(client, project) == ["A", "B"]


def test_reorder_duplicate_name(client, project):
    for name in ("A", "B"):
        client.post(f"/api/projects/{project}/system-states", json={"name": name})
    res = client.put(f"/api/projects/{project}/system-states/order", json={
        "names": ["A", "B", "A"],
    })
    assert res.status_code == 400
    assert "must list every defined system state exactly once" in res.json()["detail"]
    assert _names(client, project) == ["A", "B"]


def test_reorder_unknown_name(client, project):
    for name in ("A", "B"):
        client.post(f"/api/projects/{project}/system-states", json={"name": name})
    res = client.put(f"/api/projects/{project}/system-states/order", json={
        "names": ["A", "B", "C"],
    })
    assert res.status_code == 400
    assert "must list every defined system state exactly once" in res.json()["detail"]
    assert _names(client, project) == ["A", "B"]


def test_reorder_writes_no_order_key(client, project):
    for name in ("A", "B", "C"):
        client.post(f"/api/projects/{project}/system-states", json={"name": name})
    res = client.put(f"/api/projects/{project}/system-states/order", json={
        "names": ["C", "A", "B"],
    })
    assert res.status_code == 200

    meta = _store(project).read_meta()
    for d in meta["system_states"]:
        assert "order" not in d, f"order was written to _meta.yaml: {d}"


# ── Permissions ───────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(_real_role_client):
    with _real_role_client("admin", "ss_admin") as c:
        yield c


@pytest.fixture()
def viewer_project(admin_client):
    r = admin_client.post("/api/projects", json={"id": "ss-roles", "name": "SS Roles"})
    assert r.status_code == 201, r.text
    admin_client.patch("/api/projects/ss-roles", json={"naming": {"enforce": False}})
    admin_client.post("/api/projects/ss-roles/system-states", json={"name": "A"})
    admin_client.post("/api/projects/ss-roles/system-states", json={"name": "B"})
    return "ss-roles"


def test_reorder_viewer_is_refused(viewer_project, guest_client):
    res = guest_client.put(
        f"/api/projects/{viewer_project}/system-states/order",
        json={"names": ["B", "A"]},
    )
    assert res.status_code == 403, f"viewer reordered system states: {res.status_code}"

