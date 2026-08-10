from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.ids import safe_id
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
