from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.fingerprint import compute_fingerprint
from app.services.yaml_store import YamlStore


def _store(client, project_id: str) -> YamlStore:
    return YamlStore(Path(settings.data_root) / project_id)


def _make_cr(store, cr_id: str, changes: dict, base_fingerprints: dict | None = None) -> dict:
    cr = {
        "id": cr_id,
        "title": "Test CR",
        "status": "submitted",
        "submitted_by": "tester",
        "changes": changes,
        "base_fingerprints": base_fingerprints if base_fingerprints is not None else {},
        "affected_requirements": list(changes.keys()),
    }
    store.create_item("change_requests", cr)
    return cr


# ── Redline unit tests ────────────────────────────────────────────────────────

def test_redline_yields_field_diff(client, project):
    """A proposal differing from the target yields that field in diffs with the
    live value as before."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "SYST-R1", "name": "Old Name", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-R1"))

    cr = _make_cr(store, "CR-001",
                  changes={"SYST-R1": {"name": "New Name"}},
                  base_fingerprints={"SYST-R1": fp})

    result = redline(store, cr)
    assert result["id"] == "CR-001"
    assert result["blocked"] is False
    assert len(result["targets"]) == 1
    t = result["targets"][0]
    assert t["id"] == "SYST-R1"
    assert "name" in t["diffs"]
    assert t["diffs"]["name"]["before"] == "Old Name"
    assert t["diffs"]["name"]["after"] == "New Name"
    assert t["stale"] is False


def test_field_equal_to_proposal_absent_from_diffs(client, project):
    """A field already equal to the proposal is absent from diffs."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "SYST-R2", "name": "Same Name", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-R2"))

    # Proposal sets name to the same value.
    cr = _make_cr(store, "CR-002",
                  changes={"SYST-R2": {"name": "Same Name"}},
                  base_fingerprints={"SYST-R2": fp})

    result = redline(store, cr)
    t = result["targets"][0]
    # name should NOT be in diffs because it matches.
    assert "name" not in t["diffs"]


def test_editing_target_makes_it_stale_and_blocked(client, project):
    """Editing the target after raising the request makes it stale and blocked."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "SYST-R3", "name": "Original", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-R3"))

    cr = _make_cr(store, "CR-003",
                  changes={"SYST-R3": {"name": "Proposed"}},
                  base_fingerprints={"SYST-R3": fp})

    # Now edit the target — this changes the fingerprint.
    store.update_requirement("SYST-R3", {"name": "Edited After"})

    result = redline(store, cr)
    t = result["targets"][0]
    assert t["stale"] is True
    assert result["blocked"] is True
    # The diff should show the live (edited) value as before.
    assert t["diffs"]["name"]["before"] == "Edited After"
    assert t["diffs"]["name"]["after"] == "Proposed"


def test_no_fingerprints_not_stale(client, project):
    """A request with no base_fingerprints is not stale."""
    from app.services.change_requests import redline

    store = _store(client, project)
    store.create_requirement({"id": "SYST-R4", "name": "R4", "description": "desc"})

    cr = _make_cr(store, "CR-004",
                  changes={"SYST-R4": {"name": "New R4"}},
                  base_fingerprints={})

    # Edit the target to make it differ, but no fingerprint means not stale.
    store.update_requirement("SYST-R4", {"name": "Something Else"})

    result = redline(store, cr)
    t = result["targets"][0]
    assert t["stale"] is False
    assert result["blocked"] is False


def test_missing_target_is_stale_with_empty_diffs(client, project):
    """A target id that no longer exists is stale with empty diffs."""
    from app.services.change_requests import redline

    store = _store(client, project)
    cr = _make_cr(store, "CR-005",
                  changes={"NONEXIST": {"name": "X"}},
                  base_fingerprints={})

    result = redline(store, cr)
    assert result["blocked"] is True
    t = result["targets"][0]
    assert t["id"] == "NONEXIST"
    assert t["diffs"] == {}
    assert t["stale"] is True


# ── Execute endpoint tests ────────────────────────────────────────────────────

def test_execute_applies_fields_and_sets_implemented(client, project):
    """Execute applies every proposed field and sets status to implemented."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-E1", "name": "E1 Orig", "description": "E1 desc", "priority": "low"})
    fp = compute_fingerprint(store.get_requirement("SYST-E1"))
    _make_cr(store, "CR-E1",
             changes={"SYST-E1": {"name": "E1 New", "priority": "high"}},
             base_fingerprints={"SYST-E1": fp})

    res = client.post(f"/api/projects/{project}/change-requests/CR-E1/execute")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == "CR-E1"
    assert data["status"] == "implemented"
    assert data["updated"] == 1

    # Verify the requirement was updated.
    req = store.get_requirement("SYST-E1")
    assert req["name"] == "E1 New"
    assert req["priority"] == "high"
    # Verify CR status.
    cr = store.get_item("change_requests", "CR-E1")
    assert cr["status"] == "implemented"
    assert cr["approved_by"] == "tester"


def test_execute_on_stale_request_returns_409_and_changes_nothing(client, project):
    """Execute on a stale request returns 409 and changes nothing — assert the
    requirement is untouched, not merely that the call failed."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-E2", "name": "E2 Original", "description": "E2 desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-E2"))
    _make_cr(store, "CR-E2",
             changes={"SYST-E2": {"name": "E2 Proposed"}},
             base_fingerprints={"SYST-E2": fp})

    # Edit the target to make the CR stale.
    store.update_requirement("SYST-E2", {"name": "E2 Edited"})

    res = client.post(f"/api/projects/{project}/change-requests/CR-E2/execute")
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "SYST-E2" in detail

    # Assert the requirement is untouched.
    req = store.get_requirement("SYST-E2")
    assert req["name"] == "E2 Edited"
    # CR status should NOT be implemented.
    cr = store.get_item("change_requests", "CR-E2")
    assert cr["status"] == "submitted"


def test_execute_with_empty_changes_returns_400(client, project):
    """Execute with empty changes returns 400."""
    store = _store(client, project)
    _make_cr(store, "CR-E3", changes={})

    res = client.post(f"/api/projects/{project}/change-requests/CR-E3/execute")
    assert res.status_code == 400, res.text
    assert "no changes" in res.json()["detail"].lower()


def test_execute_records_history(client, project):
    """Execute records history for each target."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-E4", "name": "E4 Orig", "description": "E4 desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-E4"))
    _make_cr(store, "CR-E4",
             changes={"SYST-E4": {"description": "E4 updated"}},
             base_fingerprints={"SYST-E4": fp})

    res = client.post(f"/api/projects/{project}/change-requests/CR-E4/execute")
    assert res.status_code == 200, res.text

    # Verify history was recorded for the target requirement.
    history = store.list_history("SYST-E4")
    update_entries = [h for h in history if h.get("action") == "update"]
    assert len(update_entries) >= 1
    # The latest update entry should mention the description change.
    latest = update_entries[-1]
    assert "description" in latest.get("changes", {})


# ── Reject endpoint tests ─────────────────────────────────────────────────────

def test_reject_sets_rejected(client, project):
    """Reject sets status to rejected."""
    store = _store(client, project)
    _make_cr(store, "CR-R1", changes={"SOME": {"name": "x"}})

    res = client.post(f"/api/projects/{project}/change-requests/CR-R1/reject")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "rejected"

    cr = store.get_item("change_requests", "CR-R1")
    assert cr["status"] == "rejected"
    assert cr["reviewed_by"] == "tester"


def test_reject_works_on_stale_request(client, project):
    """Reject sets rejected and works on a stale request."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-RR", "name": "RR orig", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-RR"))
    _make_cr(store, "CR-R2",
             changes={"SYST-RR": {"name": "RR proposed"}},
             base_fingerprints={"SYST-RR": fp})

    # Make it stale.
    store.update_requirement("SYST-RR", {"name": "RR edited"})

    res = client.post(f"/api/projects/{project}/change-requests/CR-R2/reject")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"

    cr = store.get_item("change_requests", "CR-R2")
    assert cr["status"] == "rejected"


# ── Redline endpoint test ─────────────────────────────────────────────────────

def test_redline_endpoint_returns_correct_shape(client, project):
    """The redline endpoint returns the CRRedline shape."""
    store = _store(client, project)
    store.create_requirement({"id": "SYST-R5", "name": "R5", "description": "desc"})
    fp = compute_fingerprint(store.get_requirement("SYST-R5"))
    _make_cr(store, "CR-RL1",
             changes={"SYST-R5": {"name": "R5 new"}},
             base_fingerprints={"SYST-R5": fp})

    res = client.get(f"/api/projects/{project}/change-requests/CR-RL1/redline")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == "CR-RL1"
    assert "targets" in data
    assert "blocked" in data
    assert isinstance(data["blocked"], bool)


def test_redline_endpoint_404_for_missing_cr(client, project):
    res = client.get(f"/api/projects/{project}/change-requests/NOSUCH/redline")
    assert res.status_code == 404


# ── Fingerprint endpoint test ─────────────────────────────────────────────────

def test_fingerprint_endpoint_returns_fingerprint(client, project):
    """GET /requirements/{req_id}/fingerprint returns id and fingerprint."""
    from app.services.fingerprint import compute_fingerprint

    store = _store(client, project)
    store.create_requirement({"id": "SYST-FP", "name": "FP", "description": "fp desc"})
    expected = compute_fingerprint(store.get_requirement("SYST-FP"))

    res = client.get(f"/api/projects/{project}/requirements/SYST-FP/fingerprint")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == "SYST-FP"
    assert data["fingerprint"] == expected
