import subprocess
from pathlib import Path

from app.core.config import settings

from .conftest import make_req


# ── Projects ─────────────────────────────────────────────────────────────────

def test_project_lifecycle(client):
    res = client.post("/api/projects", json={"id": "p1", "name": "Project One"})
    assert res.status_code == 200
    assert client.get("/api/projects").json()[0]["id"] == "p1"
    assert client.get("/api/projects/p1").json()["name"] == "Project One"
    assert client.delete("/api/projects/p1").json() == {"ok": True}
    assert client.get("/api/projects/p1").status_code == 404


def test_project_id_traversal_rejected(client):
    res = client.post("/api/projects", json={"id": "../escape"})
    assert res.status_code == 400
    res = client.get("/api/projects/..%2F..%2Fetc")
    assert res.status_code in (400, 404)


# ── Requirements CRUD ────────────────────────────────────────────────────────

def test_requirement_crud_and_yaml_on_disk(client, project):
    req = make_req(client, project, "SYST0001", name="Auth", priority="high")
    assert req["created"] and req["modified"]

    path = Path(settings.data_root) / project / "requirements" / "SYST0001.yaml"
    assert path.exists()

    res = client.put(f"/api/projects/{project}/requirements/SYST0001", json={"status": "approved"})
    assert res.json()["status"] == "approved"
    assert res.json()["name"] == "Auth"

    assert client.delete(f"/api/projects/{project}/requirements/SYST0001").json() == {"ok": True}
    assert not path.exists()


def test_requirement_id_traversal_rejected(client, project):
    res = client.post(f"/api/projects/{project}/requirements", json={"id": "../../evil"})
    assert res.status_code == 400


def test_update_can_clear_nullable_fields(client, project):
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002", parent="SYST0001")

    res = client.put(f"/api/projects/{project}/requirements/SYST0002", json={"parent": None})
    assert res.status_code == 200
    assert res.json()["parent"] is None


def test_update_leaves_unmentioned_fields_alone(client, project):
    make_req(client, project, "SYST0001", rationale="because")
    res = client.put(f"/api/projects/{project}/requirements/SYST0001", json={"name": "new name"})
    assert res.json()["rationale"] == "because"


# ── Static routes must not be shadowed by /requirements/{req_id} ─────────────

def test_tree_route_reachable(client, project):
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002", parent="SYST0001")
    res = client.get(f"/api/projects/{project}/requirements/tree")
    assert res.status_code == 200
    tree = res.json()
    assert tree[0]["id"] == "SYST0001"
    assert tree[0]["children"][0]["id"] == "SYST0002"


def test_next_uid_route_reachable(client, project):
    make_req(client, project, "SYST0001")
    make_req(client, project, "SYST0002")
    res = client.get(f"/api/projects/{project}/requirements/next-uid?parent=SYST0001")
    assert res.status_code == 200
    assert res.json()["next_id"] == "SYST0003"


# ── Search ───────────────────────────────────────────────────────────────────

def test_search_and_filters(client, project):
    make_req(client, project, "SYST0001", name="Engine thrust", status="approved")
    make_req(client, project, "SYST0002", name="Wing loading", status="proposed")

    hits = client.get(f"/api/projects/{project}/requirements?search=thrust").json()
    assert [r["id"] for r in hits] == ["SYST0001"]

    hits = client.get(f"/api/projects/{project}/requirements?status=proposed").json()
    assert [r["id"] for r in hits] == ["SYST0002"]

    hits = client.get(f"/api/projects/{project}/requirements?search=wing&status=approved").json()
    assert hits == []


# ── Cascade ──────────────────────────────────────────────────────────────────

def test_cascade_creates_copies_without_polluting_verification(client, project):
    make_req(client, project, "SYST0001", name="System req")
    make_req(client, project, "PROP0001", name="Propulsion group", parent="SYST0001")

    res = client.post(f"/api/projects/{project}/requirements/SYST0001/cascade")
    assert res.status_code == 200
    created = res.json()["created"]
    assert len(created) == 1

    copy = client.get(f"/api/projects/{project}/requirements/{created[0]}").json()
    assert copy["parent"] == "PROP0001"
    assert copy["cascade_from"] == "SYST0001"
    assert copy["name"] == "System req"

    # The child group's verification_cases must not contain requirement IDs.
    child = client.get(f"/api/projects/{project}/requirements/PROP0001").json()
    assert created[0] not in child.get("verification_cases", [])


def test_cascade_propagates_edits(client, project):
    make_req(client, project, "SYST0001", name="System req")
    make_req(client, project, "PROP0001", parent="SYST0001")
    created = client.post(f"/api/projects/{project}/requirements/SYST0001/cascade").json()["created"]

    res = client.put(f"/api/projects/{project}/requirements/SYST0001", json={"name": "Renamed"})
    assert res.json().get("cascaded") is True
    copy = client.get(f"/api/projects/{project}/requirements/{created[0]}").json()
    assert copy["name"] == "Renamed"


# ── History ──────────────────────────────────────────────────────────────────

def test_history_records_field_changes(client, project):
    make_req(client, project, "SYST0001", name="Before")
    client.put(f"/api/projects/{project}/requirements/SYST0001", json={"name": "After"})

    entries = client.get(f"/api/projects/{project}/requirements/SYST0001/history").json()
    actions = [e["action"] for e in entries]
    assert "create" in actions and "update" in actions
    update = next(e for e in entries if e["action"] == "update")
    assert update["changes"]["name"] == {"before": "Before", "after": "After"}
    assert update["user"] == "tester"


# ── Bulk operations ──────────────────────────────────────────────────────────

def test_bulk_update_validates_fields(client, project):
    make_req(client, project, "SYST0001")
    res = client.post(f"/api/projects/{project}/requirements/bulk",
                      json={"ids": ["SYST0001"], "updates": {"status": "not-a-status"}})
    assert res.status_code == 422

    res = client.post(f"/api/projects/{project}/requirements/bulk",
                      json={"ids": ["SYST0001"], "updates": {"status": "approved"}})
    assert res.json()["updated"] == 1


# ── Auth & roles ─────────────────────────────────────────────────────────────

def test_guest_cannot_mutate(guest_client):
    res = guest_client.post("/api/projects", json={"id": "p1"})
    assert res.status_code == 403


def test_self_registration_cannot_grant_admin(guest_client):
    res = guest_client.post("/api/auth/register",
                            json={"username": "mallory", "password": "pass1234", "role": "admin"})
    assert res.status_code == 403

    res = guest_client.post("/api/auth/register",
                            json={"username": "alice", "password": "pass1234"})
    assert res.status_code == 200
    assert res.json()["role"] == "editor"


def test_project_delete_requires_admin(guest_client):
    res = guest_client.delete("/api/projects/anything")
    assert res.status_code == 403


# ── Verification, traces, baselines ──────────────────────────────────────────

def test_verification_case_lifecycle(client, project):
    res = client.post(f"/api/projects/{project}/verification",
                      json={"id": "VC-001", "name": "Thrust test", "method": "test"})
    assert res.status_code == 201
    res = client.put(f"/api/projects/{project}/verification/VC-001",
                     json={"status": "passed", "verified_requirements": ["SYST0001"]})
    assert res.json()["status"] == "passed"


def test_baseline_freeze_and_diff(client, project):
    make_req(client, project, "SYST0001", name="Original")
    res = client.post(f"/api/projects/{project}/baselines/BL1/freeze")
    assert res.json()["requirements"] == 1

    client.put(f"/api/projects/{project}/requirements/SYST0001", json={"name": "Changed"})
    diff = client.get(f"/api/projects/{project}/baselines/BL1/diff").json()
    assert diff["changed_count"] == 1
    assert diff["changes"][0]["diffs"]["name"]["after"] == "Changed"


def test_validate_flags_dangling_relation(client, project):
    make_req(client, project, "SYST0001", name="A")
    client.put(f"/api/projects/{project}/requirements/SYST0001",
               json={"relations": [{"type": "refines", "target": "GHOST9999"}]})
    res = client.get(f"/api/projects/{project}/validate").json()
    assert res["valid"] is False
    assert any(i["type"] == "dangling_link" for i in res["issues"])


# ── Git auto-commit ──────────────────────────────────────────────────────────

def test_git_autocommit_and_log(client, project, monkeypatch):
    project_root = Path(settings.data_root) / project
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    monkeypatch.setattr(settings, "git_autocommit", True)

    make_req(client, project, "SYST0001", name="Committed req")

    res = client.get(f"/api/projects/{project}/git/log").json()
    assert res["is_repo"] is True
    assert len(res["commits"]) >= 1
    assert "requirements" in res["commits"][0]["message"]
