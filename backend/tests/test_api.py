import subprocess
from pathlib import Path

from app.core.config import settings

from .conftest import make_req


# ── Projects ─────────────────────────────────────────────────────────────────

def test_project_lifecycle(client):
    res = client.post("/api/projects", json={"id": "p1", "name": "Project One"})
    assert res.status_code == 201
    assert client.get("/api/projects").json()[0]["id"] == "p1"
    assert client.get("/api/projects/p1").json()["name"] == "Project One"
    assert client.delete("/api/projects/p1").json() == {"ok": True}
    assert client.get("/api/projects/p1").status_code == 404


def test_project_id_traversal_rejected(client):
    res = client.post("/api/projects", json={"id": "../escape", "name": "escape"})
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

    hits = client.get(f"/api/projects/{project}/requirements?search=thrust").json()["items"]
    assert [r["id"] for r in hits] == ["SYST0001"]

    hits = client.get(f"/api/projects/{project}/requirements?status=proposed").json()["items"]
    assert [r["id"] for r in hits] == ["SYST0002"]

    hits = client.get(f"/api/projects/{project}/requirements?search=wing&status=approved").json()["items"]
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
                            json={"username": "mallory", "password": "TestPass1!secure", "role": "admin"})
    assert res.status_code == 403

    res = guest_client.post("/api/auth/register",
                            json={"username": "alice", "password": "TestPass1!secure"})
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

# ── Requirement creation with nested fields ──────────────────────────────────

def test_create_requirement_accepts_relations_and_attributes(client, project):
    make_req(client, project, "SYST0001")
    req = make_req(client, project, "SYST0002",
                   relations=[{"type": "refines", "target": "SYST0001"}],
                   attributes=[{"key": "standard", "value": "DO-178C"}])
    assert req["relations"] == [{"type": "refines", "target": "SYST0001", "reviewed_fingerprint": None}]
    assert req["attributes"] == [{"key": "standard", "value": "DO-178C"}]


# ── Custom workflow enforcement ──────────────────────────────────────────────

def _set_workflow(project_id):
    from app.services.yaml_store import YamlStore
    store = YamlStore(Path(settings.data_root) / project_id)
    meta = store.read_meta()
    meta["workflow"] = {
        "states": ["proposed", "approved", "verified"],
        "transitions": {"proposed": ["approved"], "approved": ["verified"]},
        "default": "proposed",
    }
    store.write_meta(meta)


def test_workflow_blocks_invalid_transition(client, project):
    make_req(client, project, "SYST0001")
    _set_workflow(project)

    res = client.put(f"/api/projects/{project}/requirements/SYST0001", json={"status": "verified"})
    assert res.status_code == 400
    assert "not allowed" in res.json()["detail"]

    res = client.put(f"/api/projects/{project}/requirements/SYST0001", json={"status": "approved"})
    assert res.status_code == 200


def test_bulk_update_respects_workflow(client, project):
    make_req(client, project, "SYST0001")                      # proposed
    make_req(client, project, "SYST0002", status="verified")   # terminal state
    _set_workflow(project)

    res = client.post(f"/api/projects/{project}/requirements/bulk",
                      json={"ids": ["SYST0001", "SYST0002"], "updates": {"status": "approved"}})
    body = res.json()
    assert body["ids"] == ["SYST0001"]
    assert [s["id"] for s in body["skipped"]] == ["SYST0002"]


# ── Published reports escape user content ────────────────────────────────────

def test_publish_html_escapes_user_content(client, project):
    make_req(client, project, "SYST0001", name='<script>alert("xss")</script>')
    res = client.post(f"/api/projects/{project}/publish", json={"format": "html"})
    content = res.json()["content"]
    assert '<script>alert' not in content
    assert '&lt;script&gt;' in content


# ── ReqIF export structure ───────────────────────────────────────────────────

def test_reqif_export_is_well_formed(client, project):
    import xml.etree.ElementTree as ET

    make_req(client, project, "SYST0001", name="Root")
    make_req(client, project, "SYST0002", name="Child",
             relations=[{"type": "refines", "target": "SYST0001"}])
    client.put(f"/api/projects/{project}/traces",
               json={"links": [{"source": "SYST0002", "target": "SYST0001", "type": "refines"}]})

    res = client.get(f"/api/projects/{project}/publish/download?format=reqif")
    assert res.status_code == 200
    root = ET.fromstring(res.content)

    ns = {"r": "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"}
    # Every attribute value carries exactly one DEFINITION element.
    for av in root.iter("{http://www.omg.org/spec/ReqIF/20110401/reqif.xsd}ATTRIBUTE-VALUE-STRING"):
        assert len(av.findall("r:DEFINITION", ns)) == 1
    # Every hierarchy entry has exactly one OBJECT ref.
    for h in root.iter("{http://www.omg.org/spec/ReqIF/20110401/reqif.xsd}SPEC-HIERARCHY"):
        assert len(h.findall("r:OBJECT", ns)) == 1
    # Relation identifiers are unique.
    rel_ids = [rel.get("IDENTIFIER")
               for rel in root.iter("{http://www.omg.org/spec/ReqIF/20110401/reqif.xsd}SPEC-RELATION")]
    assert len(rel_ids) == 2
    assert len(set(rel_ids)) == len(rel_ids)


# ── Registration password policy ─────────────────────────────────────────────

def test_register_rejects_short_password(guest_client):
    res = guest_client.post("/api/auth/register",
                            json={"username": "bob", "password": "Sh1!"})
    assert res.status_code == 400
    assert "12 characters" in res.json()["detail"]


# ── Demo project seeding ─────────────────────────────────────────────────────

def test_demo_project_seeded_on_first_launch(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(settings, "seed_demo", True)
    with TestClient(app) as c:
        projects = c.get("/api/projects").json()
        assert [p["id"] for p in projects] == ["cessna-172"]
        reqs = c.get("/api/projects/cessna-172/requirements").json()["items"]
        assert len(reqs) >= 50
        tree = c.get("/api/projects/cessna-172/requirements/tree").json()
        assert tree[0]["id"] == "ACFT0000"
        assert len(c.get("/api/projects/cessna-172/verification").json()) >= 7
        validate_result = c.get("/api/projects/cessna-172/validate").json()
        assert "issues" in validate_result
        assert "valid" in validate_result


def test_demo_seeding_skips_populated_data_root(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.yaml_store import YamlStore

    existing = Path(settings.data_root) / "my-project"
    store = YamlStore(existing)
    store.ensure_dirs()
    store.write_meta({"name": "Mine"})

    monkeypatch.setattr(settings, "seed_demo", True)
    with TestClient(app) as c:
        ids = [p["id"] for p in c.get("/api/projects").json()]
        assert ids == ["my-project"]


def test_baseline_rename_carries_snapshot_and_labels(client, project):
    make_req(client, project, "SYST0001")
    client.post(f"/api/projects/{project}/baselines",
                json={"name": "BL1", "requirements": ["SYST0001"]})
    client.post(f"/api/projects/{project}/baselines/BL1/freeze")

    res = client.patch(f"/api/projects/{project}/baselines/BL1", json={"name": "BL2"})
    assert res.status_code == 200
    assert res.json()["requirements_updated"] == 1

    # The requirement label moved and the frozen snapshot moved with it.
    req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
    assert req["baseline"] == "BL2"
    assert client.get(f"/api/projects/{project}/baselines/BL2/diff").status_code == 200
    assert client.get(f"/api/projects/{project}/baselines/BL1/diff").status_code == 404


def test_baseline_rename_missing_is_404(client, project):
    res = client.patch(f"/api/projects/{project}/baselines/NOPE", json={"name": "NEW"})
    assert res.status_code == 404


def test_project_git_settings_roundtrip_and_visibility(client, project):
    from app.core import auth as auth_mod

    res = client.patch(f"/api/projects/{project}",
                       json={"git": {"remote_url": "https://token@example.com/r.git",
                                     "push_interval_minutes": 5}})
    assert res.status_code == 200

    # Anonymous readers never see the git block (remote URLs may hold tokens).
    anon = client.get(f"/api/projects/{project}", headers={"Authorization": ""})
    assert "git" not in anon.json()

    # A signed-in editor gets it back for the settings page.
    auth_mod.register_user("ed", "Password123!", "editor")
    tok = auth_mod.create_token("ed", "editor")
    seen = client.get(f"/api/projects/{project}",
                      headers={"Authorization": f"Bearer {tok}"}).json()
    assert seen["git"]["push_interval_minutes"] == 5


def test_profile_email_change_resets_verification(client, workspace):
    from app.core import auth as auth_mod

    auth_mod.register_user("pat", "Password123!", "editor")
    users = auth_mod.load_users()
    users["pat"]["email"] = "old@example.com"
    users["pat"]["email_verified"] = True
    auth_mod.save_users(users)

    tok = auth_mod.create_token("pat", "editor")
    res = client.patch("/api/auth/profile", json={"email": "new@example.com"},
                       headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200
    assert auth_mod.load_users()["pat"]["email_verified"] is False

    res = client.patch("/api/auth/profile", json={"email": "not-an-email"},
                       headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 400


# ── Version / build metadata ─────────────────────────────────────────────────

def test_version_endpoints_report_version(client):
    from app.core.version import get_version

    ver = get_version()
    root = client.get("/version")
    assert root.status_code == 200
    assert root.json()["version"] == ver
    assert root.json()["name"] == "reqmesh"

    api = client.get("/api/version")
    assert api.status_code == 200
    assert api.json()["version"] == ver

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == ver
