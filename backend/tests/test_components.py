"""Tests for the component hierarchy and its mapping onto requirements/verification."""

from __future__ import annotations

import pytest

from tests.conftest import make_req


def make_vc(client, project_id, vc_id, **fields):
    res = client.post(f"/api/projects/{project_id}/verification", json={"id": vc_id, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def make_component(client, project_id, cid, **fields):
    body = {"id": cid, "name": fields.pop("name", cid), **fields}
    return client.post(f"/api/projects/{project_id}/components", json=body)


@pytest.fixture()
def wired(client, project):
    """A project with one requirement and one verification case to map onto."""
    make_req(client, project, "REQ-001", name="Cabin pressure")
    make_vc(client, project, "VC-001", name="Pressure test")
    return project


# ── CRUD ─────────────────────────────────────────────────────────────────────

def test_create_component_defaults(client, project):
    res = make_component(client, project, "C-001")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["type"] == "assembly"
    assert body["parent"] is None
    assert body["quantity"] == 1
    assert body["satisfies"] == []


def test_list_is_sorted_by_id(client, project):
    make_component(client, project, "C-002")
    make_component(client, project, "C-001")
    ids = [c["id"] for c in client.get(f"/api/projects/{project}/components").json()]
    assert ids == ["C-001", "C-002"]


def test_get_and_update(client, project):
    make_component(client, project, "C-001", name="Pump")
    res = client.put(f"/api/projects/{project}/components/C-001", json={"supplier": "Acme", "quantity": 3})
    assert res.status_code == 200
    body = client.get(f"/api/projects/{project}/components/C-001").json()
    assert body["supplier"] == "Acme"
    assert body["quantity"] == 3
    assert body["name"] == "Pump"  # untouched fields survive a partial update


def test_get_missing_component(client, project):
    assert client.get(f"/api/projects/{project}/components/nope").status_code == 404


def test_duplicate_id_conflicts(client, project):
    make_component(client, project, "C-001")
    assert make_component(client, project, "C-001").status_code == 409


def test_rejects_unsafe_id(client, project):
    assert make_component(client, project, "../escape").status_code == 400


def test_non_editor_cannot_create(client, project, guest_client):
    # The `client` fixture overrides require_edit app-wide to authenticate as an
    # admin; drop it so the real guard runs against the guest's viewer role.
    from app.core.dependencies import require_edit
    from app.main import app
    app.dependency_overrides.pop(require_edit)

    res = guest_client.post(f"/api/projects/{project}/components", json={"id": "C-001", "name": "X"})
    assert res.status_code == 403


# ── Hierarchy ────────────────────────────────────────────────────────────────

def test_tree_nests_children_under_parents(client, project):
    make_component(client, project, "SYS", type="system")
    make_component(client, project, "SUB", type="subsystem", parent="SYS")
    make_component(client, project, "PART", type="part", parent="SUB")

    tree = client.get(f"/api/projects/{project}/components/tree").json()
    assert len(tree) == 1
    assert tree[0]["id"] == "SYS"
    assert tree[0]["children"][0]["id"] == "SUB"
    assert tree[0]["children"][0]["children"][0]["id"] == "PART"


def test_tree_is_not_shadowed_by_the_id_route(client, project):
    # "tree" must route to the tree endpoint, not be read as a component id.
    make_component(client, project, "SYS")
    res = client.get(f"/api/projects/{project}/components/tree")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_rejects_missing_parent(client, project):
    res = make_component(client, project, "C-001", parent="ghost")
    assert res.status_code == 400
    assert "Parent component not found" in res.json()["detail"]


def test_rejects_self_parent(client, project):
    make_component(client, project, "C-001")
    res = client.put(f"/api/projects/{project}/components/C-001", json={"parent": "C-001"})
    assert res.status_code == 400
    assert "own parent" in res.json()["detail"]


def test_rejects_reparenting_under_own_descendant(client, project):
    make_component(client, project, "A")
    make_component(client, project, "B", parent="A")
    make_component(client, project, "C", parent="B")
    # A under C would detach the whole A→B→C branch from the tree.
    res = client.put(f"/api/projects/{project}/components/A", json={"parent": "C"})
    assert res.status_code == 400
    assert "Circular" in res.json()["detail"]


def test_delete_promotes_children_to_the_grandparent(client, project):
    make_component(client, project, "SYS")
    make_component(client, project, "SUB", parent="SYS")
    make_component(client, project, "PART", parent="SUB")

    res = client.delete(f"/api/projects/{project}/components/SUB")
    assert res.status_code == 200
    assert res.json()["promoted_children"] == ["PART"]

    # PART must still be reachable from the tree, now directly under SYS.
    assert client.get(f"/api/projects/{project}/components/PART").json()["parent"] == "SYS"
    tree = client.get(f"/api/projects/{project}/components/tree").json()
    assert tree[0]["children"][0]["id"] == "PART"


def test_deleting_a_root_promotes_children_to_top_level(client, project):
    make_component(client, project, "SYS")
    make_component(client, project, "SUB", parent="SYS")
    client.delete(f"/api/projects/{project}/components/SYS")

    assert client.get(f"/api/projects/{project}/components/SUB").json()["parent"] is None
    tree = client.get(f"/api/projects/{project}/components/tree").json()
    assert [c["id"] for c in tree] == ["SUB"]


def test_delete_missing_component(client, project):
    assert client.delete(f"/api/projects/{project}/components/nope").status_code == 404


# ── Mapping onto requirements / verification ─────────────────────────────────

def test_component_satisfies_requirement(client, wired):
    res = make_component(client, wired, "C-001", satisfies=["REQ-001"])
    assert res.status_code == 201
    assert res.json()["satisfies"] == ["REQ-001"]


def test_component_links_to_verification_case(client, wired):
    res = make_component(client, wired, "C-001", verification_cases=["VC-001"])
    assert res.status_code == 201
    assert res.json()["verification_cases"] == ["VC-001"]


def test_rejects_link_to_missing_requirement(client, wired):
    res = make_component(client, wired, "C-001", satisfies=["REQ-999"])
    assert res.status_code == 400
    assert "Requirement not found" in res.json()["detail"]


def test_rejects_link_to_missing_verification_case(client, wired):
    res = make_component(client, wired, "C-001", verification_cases=["VC-999"])
    assert res.status_code == 400
    assert "Verification case not found" in res.json()["detail"]


def test_update_validates_links(client, wired):
    make_component(client, wired, "C-001")
    res = client.put(f"/api/projects/{wired}/components/C-001", json={"satisfies": ["REQ-999"]})
    assert res.status_code == 400


def test_reverse_lookup_from_requirement(client, wired):
    make_component(client, wired, "C-001", satisfies=["REQ-001"])
    make_component(client, wired, "C-002")  # unrelated

    res = client.get(f"/api/projects/{wired}/requirements/REQ-001/components")
    assert res.status_code == 200
    assert [c["id"] for c in res.json()] == ["C-001"]


def test_reverse_lookup_from_verification_case(client, wired):
    make_component(client, wired, "C-001", verification_cases=["VC-001"])
    res = client.get(f"/api/projects/{wired}/verification/VC-001/components")
    assert [c["id"] for c in res.json()] == ["C-001"]


def test_reverse_lookup_on_missing_requirement(client, wired):
    assert client.get(f"/api/projects/{wired}/requirements/ghost/components").status_code == 404


def test_filter_by_satisfied_requirement(client, wired):
    make_component(client, wired, "C-001", satisfies=["REQ-001"])
    make_component(client, wired, "C-002")
    res = client.get(f"/api/projects/{wired}/components", params={"satisfies": "REQ-001"})
    assert [c["id"] for c in res.json()] == ["C-001"]


def test_filter_by_type_and_search(client, project):
    make_component(client, project, "C-001", name="Fuel Pump", type="part", part_number="FP-9")
    make_component(client, project, "C-002", name="Avionics Bay", type="assembly")

    by_type = client.get(f"/api/projects/{project}/components", params={"type": "part"}).json()
    assert [c["id"] for c in by_type] == ["C-001"]

    by_name = client.get(f"/api/projects/{project}/components", params={"search": "fuel"}).json()
    assert [c["id"] for c in by_name] == ["C-001"]

    by_pn = client.get(f"/api/projects/{project}/components", params={"search": "FP-9"}).json()
    assert [c["id"] for c in by_pn] == ["C-001"]


# ── Storage & integrity ──────────────────────────────────────────────────────

def test_component_is_stored_as_yaml(client, project, workspace):
    make_component(client, project, "C-001", name="Pump")
    path = workspace / "projects" / project / "components" / "C-001.yaml"
    assert path.is_file()
    assert "Pump" in path.read_text()


def test_integrity_flags_a_requirement_deleted_out_from_under_a_component(client, wired):
    make_component(client, wired, "C-001", satisfies=["REQ-001"])
    client.delete(f"/api/projects/{wired}/requirements/REQ-001")

    issues = client.get(f"/api/projects/{wired}/validate").json()["issues"]
    dangling = [i for i in issues if i["type"] == "component_dangling_requirement"]
    assert len(dangling) == 1
    assert dangling[0]["id"] == "C-001"
    assert dangling[0]["target"] == "REQ-001"


def test_integrity_flags_a_deleted_verification_case(client, wired):
    make_component(client, wired, "C-001", verification_cases=["VC-001"])
    client.delete(f"/api/projects/{wired}/verification/VC-001")

    issues = client.get(f"/api/projects/{wired}/validate").json()["issues"]
    assert any(i["type"] == "component_dangling_verification" for i in issues)


def test_clean_project_has_no_component_issues(client, wired):
    make_component(client, wired, "SYS")
    make_component(client, wired, "C-001", parent="SYS", satisfies=["REQ-001"], verification_cases=["VC-001"])

    issues = client.get(f"/api/projects/{wired}/validate").json()["issues"]
    assert [i for i in issues if i["type"].startswith("component_")] == []
