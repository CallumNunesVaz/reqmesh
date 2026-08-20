from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.services.fingerprint import compute_fingerprint
from app.services.yaml_store import YamlStore


def _store(client, project_id: str) -> YamlStore:
    return YamlStore(Path(settings.data_root) / project_id)


def _make_cr(store, cr_id: str, changes: dict, base_fingerprints: dict | None = None,
             creates: list[str] | None = None) -> dict:
    cr = {
        "id": cr_id,
        "title": "Test CR",
        "status": "submitted",
        "submitted_by": "tester",
        "changes": changes,
        "base_fingerprints": base_fingerprints if base_fingerprints is not None else {},
        "affected_requirements": list(changes.keys()),
        "creates": creates if creates is not None else [],
    }
    store.create_item("change_requests", cr)
    return cr


# ── Creates: redline ──────────────────────────────────────────────────────────

def test_creates_target_produces_creates_true_redline(client, project):
    """A CR with creates: ["NEW0001"] produces a redline where that target
    has creates: True, stale: False, all diffs with before: None, and is not blocked."""
    from app.services.change_requests import redline

    store = _store(client, project)
    cr = _make_cr(store, "CR-C1",
                  changes={"NEW0001": {"name": "New Req", "description": "A new one"}},
                  creates=["NEW0001"])

    result = redline(store, cr)
    assert result["blocked"] is False
    assert len(result["targets"]) == 1
    t = result["targets"][0]
    assert t["id"] == "NEW0001"
    assert t["name"] == "New Req"
    assert t["stale"] is False
    assert t["creates"] is True
    assert t["diffs"]["name"]["before"] is None
    assert t["diffs"]["name"]["after"] == "New Req"
    assert t["diffs"]["description"]["before"] is None
    assert t["diffs"]["description"]["after"] == "A new one"


def test_creates_target_uses_target_id_as_name_when_no_name_in_proposal(client, project):
    """When the proposal has no 'name' field, the target name falls back to the id."""
    from app.services.change_requests import redline

    store = _store(client, project)
    cr = _make_cr(store, "CR-C2",
                  changes={"NEW0002": {"description": "desc only"}},
                  creates=["NEW0002"])

    result = redline(store, cr)
    t = result["targets"][0]
    assert t["name"] == "NEW0002"


# ── Creates: execute ──────────────────────────────────────────────────────────

def test_execute_creates_requirement(client, project):
    """Executing a creates CR creates the requirement and records 'create' history."""
    store = _store(client, project)
    _make_cr(store, "CR-C3",
             changes={"NEW0003": {"name": "Created Req", "description": "hello", "priority": "high"}},
             creates=["NEW0003"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-C3/execute")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["updated"] == 1

    req = store.get_requirement("NEW0003")
    assert req is not None
    assert req["name"] == "Created Req"
    assert req["description"] == "hello"
    assert req["priority"] == "high"

    history = store.list_history("NEW0003")
    create_entries = [h for h in history if h.get("action") == "create"]
    assert len(create_entries) >= 1


def test_execute_creates_records_create_not_update(client, project):
    """A creates target records a 'create' history entry, not 'update'."""
    store = _store(client, project)
    _make_cr(store, "CR-C4",
             changes={"NEW0004": {"name": "C4"}},
             creates=["NEW0004"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-C4/execute")
    assert res.status_code == 200, res.text

    history = store.list_history("NEW0004")
    update_entries = [h for h in history if h.get("action") == "update"]
    assert len(update_entries) == 0


# ── Deleted requirement must not regress ──────────────────────────────────────

def test_absent_id_not_in_creates_is_stale_and_blocked(client, project):
    """A CR targeting an absent id that is not in creates is still stale and blocked."""
    from app.services.change_requests import redline

    store = _store(client, project)
    cr = _make_cr(store, "CR-C5",
                  changes={"GONE": {"name": "x"}},
                  creates=[])

    result = redline(store, cr)
    assert result["blocked"] is True
    t = result["targets"][0]
    assert t["id"] == "GONE"
    assert t["diffs"] == {}
    assert t["stale"] is True
    assert t["creates"] is False


# ── Collision: creates id already exists ──────────────────────────────────────

def test_creates_id_already_exists_is_stale_and_blocked(client, project):
    """A CR whose creates id already exists is stale and blocked."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "EXISTS", "name": "Already Here", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("EXISTS"))
    cr = _make_cr(store, "CR-C6",
                  changes={"EXISTS": {"name": "New Name"}},
                  base_fingerprints={"EXISTS": fp},
                  creates=["EXISTS"])

    result = redline(store, cr)
    assert result["blocked"] is True
    t = result["targets"][0]
    assert t["stale"] is True
    assert t["creates"] is True


def test_execute_collision_returns_409(client, project):
    """Executing a CR whose creates id already exists returns 409 without touching
    the record."""
    store = _store(client, project)
    store.create_requirement({"id": "EXISTS2", "name": "Already Here", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("EXISTS2"))
    _make_cr(store, "CR-C7",
             changes={"EXISTS2": {"name": "New Name"}},
             base_fingerprints={"EXISTS2": fp},
             creates=["EXISTS2"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-C7/execute")
    assert res.status_code == 409, res.text

    req = store.get_requirement("EXISTS2")
    assert req["name"] == "Already Here"


# ── Mixed CR (one edit, one creation) ─────────────────────────────────────────

def test_mixed_cr_applies_both(client, project):
    """A mixed CR (one edit, one creation) applies both and reports combined count."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-M1", "name": "M1 Orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-M1"))
    _make_cr(store, "CR-M1",
             changes={
                 "SYST-M1": {"name": "M1 Updated"},
                 "NEW-M1": {"name": "New M1", "description": "created"},
             },
             base_fingerprints={"SYST-M1": fp},
             creates=["NEW-M1"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-M1/execute")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["updated"] == 2

    # Edit applied.
    req = store.get_requirement("SYST-M1")
    assert req["name"] == "M1 Updated"

    # Creation applied.
    new_req = store.get_requirement("NEW-M1")
    assert new_req is not None
    assert new_req["name"] == "New M1"
    assert new_req["description"] == "created"


def test_execute_creates_requirement_with_full_defaults(client, project):
    """A CR proposes only the fields it cares about, so the created requirement
    must still come out with the same defaults POST /requirements applies.
    Writing the bare proposal produced a record with no type, priority or
    status — one the UI crashed on."""
    store = _store(client, project)
    _make_cr(store, "CR-DEF",
             changes={"NEW-DEF": {"name": "Sparse proposal"}},
             creates=["NEW-DEF"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-DEF/execute")
    assert res.status_code == 200, res.text

    req = store.get_requirement("NEW-DEF")
    assert req["type"] == "functional"
    assert req["priority"] == "medium"
    assert req["status"] == "proposed"
    assert req["attributes"] == []
    assert req["relations"] == []
    assert req["verification_cases"] == []
    assert req["verification_status"] == "pending"


def test_execute_sanitises_proposed_description(client, project):
    """The create goes through RequirementCreate, so a script payload proposed
    in a change request is cleaned exactly as it is on the normal create path."""
    store = _store(client, project)
    _make_cr(store, "CR-XSS",
             changes={"NEW-XSS": {"name": "x", "description": "<p>ok</p><script>alert(1)</script>"}},
             creates=["NEW-XSS"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-XSS/execute")
    assert res.status_code == 200, res.text
    assert "<script>" not in store.get_requirement("NEW-XSS")["description"]


def test_execute_rejects_invalid_proposed_field(client, project):
    """An unusable value in the proposal is a 400, not a half-written record."""
    store = _store(client, project)
    _make_cr(store, "CR-INV",
             changes={"NEW-INV": {"name": "x", "priority": "urgent-ish"}},
             creates=["NEW-INV"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-INV/execute")
    assert res.status_code == 400, res.text
    assert store.get_requirement("NEW-INV") is None


# ── Execute reports what it created ───────────────────────────────────────────

def test_execute_returns_created_ids(client, project):
    """Execute reports the ids it brought into existence, so the caller can focus
    the new requirement instead of guessing which target was the new one."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-R1", "name": "R1 Orig"})
    fp = compute_fingerprint(store.get_requirement("SYST-R1"))
    _make_cr(store, "CR-R1",
             changes={
                 "SYST-R1": {"name": "R1 Updated"},
                 "NEW-R1": {"name": "New R1"},
             },
             base_fingerprints={"SYST-R1": fp},
             creates=["NEW-R1"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-R1/execute")
    assert res.status_code == 200, res.text
    data = res.json()
    # Only the creation, not the edit.
    assert data["created"] == ["NEW-R1"]
    assert data["updated"] == 2


def test_execute_returns_empty_created_for_edit_only_cr(client, project):
    """An edit-only CR reports no creations — the field is always present so the
    caller never has to distinguish absent from empty."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-R2", "name": "R2 Orig"})
    fp = compute_fingerprint(store.get_requirement("SYST-R2"))
    _make_cr(store, "CR-R2",
             changes={"SYST-R2": {"name": "R2 Updated"}},
             base_fingerprints={"SYST-R2": fp})

    res = client.post(f"/api/projects/{project}/change-requests/CR-R2/execute")
    assert res.status_code == 200, res.text
    assert res.json()["created"] == []


# ── Unsafe id in creates ──────────────────────────────────────────────────────

def test_unsafe_id_in_creates_is_rejected(client, project):
    """An unsafe id in creates (e.g. ../etc/passwd) is rejected with 400."""
    store = _store(client, project)
    _make_cr(store, "CR-BAD",
             changes={"../etc/passwd": {"name": "bad"}},
             creates=["../etc/passwd"])

    res = client.post(f"/api/projects/{project}/change-requests/CR-BAD/execute")
    assert res.status_code == 400, res.text


def test_unsafe_id_blank_is_rejected(client, project):
    """A blank id in creates is rejected."""
    store = _store(client, project)
    _make_cr(store, "CR-BLANK",
             changes={"": {"name": "blank"}},
             creates=[""])

    res = client.post(f"/api/projects/{project}/change-requests/CR-BLANK/execute")
    assert res.status_code == 400, res.text


# ── Compatibility: existing CRs with no creates field still work ──────────────

def test_existing_cr_without_creates_field_is_unaffected(client, project):
    """A CR without 'creates' (written before the change) behaves as before."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "SYST-C8", "name": "C8 Orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-C8"))

    # Simulate an old CR without the 'creates' key.
    cr = {
        "id": "CR-OLD",
        "title": "Old CR",
        "status": "submitted",
        "submitted_by": "tester",
        "changes": {"SYST-C8": {"name": "C8 New"}},
        "base_fingerprints": {"SYST-C8": fp},
        "affected_requirements": ["SYST-C8"],
    }
    store.create_item("change_requests", cr)

    result = redline(store, cr)
    assert result["blocked"] is False
    t = result["targets"][0]
    assert t["creates"] is False
    assert t["name"] == "C8 Orig"

    # Execute still works.
    res = client.post(f"/api/projects/{project}/change-requests/CR-OLD/execute")
    assert res.status_code == 200, res.text
    assert store.get_requirement("SYST-C8")["name"] == "C8 New"


# ── Lifecycle fields are not writable through the generic PUT ─────────────────

def _tok(username: str, role: str) -> dict:
    from app.core import auth
    auth.register_user(username, "Password123!", role)
    return {"Authorization": f"Bearer {auth.create_token(username, role)}"}


def _make_project_demo(guest_client) -> None:
    """Create project ``demo`` with naming enforcement off, using a real admin."""
    adm = _tok("adm", "admin")
    assert guest_client.post("/api/projects", json={"id": "demo", "name": "Demo"},
                             headers=adm).status_code == 201
    assert guest_client.patch("/api/projects/demo", json={"naming": {"enforce": False}},
                              headers=adm).status_code == 200


@pytest.mark.parametrize("field,value", [
    ("status", "approved"),
    ("approved_by", "admin"),
    ("reviewed_by", "admin"),
    ("submitted_by", "admin"),
])
def test_contributor_cannot_put_lifecycle_fields(guest_client, field, value):
    """A propose-tier caller cannot set a lifecycle field through PUT — the
    generic write path must not out-rank the execute/reject approval gates."""
    _make_project_demo(guest_client)
    project = "demo"
    cont = _tok("cont", "contributor")

    res = guest_client.post(
        f"/api/projects/{project}/change-requests",
        json={"id": f"CR-LF-{field}", "title": "x"},
        headers=cont,
    )
    assert res.status_code == 201, res.text

    res = guest_client.put(
        f"/api/projects/{project}/change-requests/CR-LF-{field}",
        json={field: value},
        headers=cont,
    )
    assert res.status_code == 422, res.text

    cr = guest_client.get(
        f"/api/projects/{project}/change-requests/CR-LF-{field}",
        headers=cont).json()
    assert cr["status"] == "submitted"
    assert cr["approved_by"] == ""


def test_maintainer_can_execute_change_request(guest_client):
    """The lifecycle-field tightening must not lock the legitimate approval path —
    a maintainer's execute still works end-to-end."""
    _make_project_demo(guest_client)
    project = "demo"
    store = _store(None, project)
    store.create_requirement({"id": "SYST-MT", "name": "MT Orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-MT"))
    _make_cr(store, "CR-MT",
             changes={"SYST-MT": {"name": "MT Updated"}},
             base_fingerprints={"SYST-MT": fp})

    maint = _tok("maint", "maintainer")
    res = guest_client.post(f"/api/projects/{project}/change-requests/CR-MT/execute",
                            headers=maint)
    assert res.status_code == 200, res.text
    assert store.get_requirement("SYST-MT")["name"] == "MT Updated"


# ── changes are validated against RequirementUpdate on execute ────────────────

def test_execute_rejects_unknown_key_in_changes(client, project):
    """An unknown key in a proposed change is a 400 with the envelope, not a
    silently-merged write."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-UK", "name": "UK Orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-UK"))
    _make_cr(store, "CR-UK",
             changes={"SYST-UK": {"name": "UK New", "bogus_field": "x"}},
             base_fingerprints={"SYST-UK": fp})

    res = client.post(f"/api/projects/{project}/change-requests/CR-UK/execute")
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "invalid_change"
    assert detail["requirement_id"] == "SYST-UK"
    assert detail["errors"]
    assert store.get_requirement("SYST-UK")["name"] == "UK Orig"


def test_execute_rejects_wrong_typed_change(client, project):
    """A well-formed but wrong-typed value in a proposed change is a 400 with
    the envelope."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-WT", "name": "WT Orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-WT"))
    _make_cr(store, "CR-WT",
             changes={"SYST-WT": {"priority": "not-a-priority"}},
             base_fingerprints={"SYST-WT": fp})

    res = client.post(f"/api/projects/{project}/change-requests/CR-WT/execute")
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "invalid_change"
    assert detail["requirement_id"] == "SYST-WT"
