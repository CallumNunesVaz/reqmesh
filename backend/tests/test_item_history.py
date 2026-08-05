"""Tests for the generic item-history endpoint at /projects/{id}/history/{item_id}."""

def test_risk_history_has_create_and_update_entries(client, project):
    """A risk created then updated has >=1 entry, and the update carries before/after."""
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK-1", "title": "Original", "severity": "critical", "likelihood": "rare"})
    client.put(f"/api/projects/{project}/risks/RSK-1", json={"title": "Updated"})

    res = client.get(f"/api/projects/{project}/history/RSK-1")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) >= 1
    # The newest entry (first) should be the update
    update_entry = entries[0]
    assert update_entry["action"] == "update"
    assert "title" in update_entry["changes"]
    assert update_entry["changes"]["title"]["before"] == "Original"
    assert update_entry["changes"]["title"]["after"] == "Updated"


def test_component_history(client, project):
    """A component created then updated appears in history."""
    client.post(f"/api/projects/{project}/components", json={"id": "CMP-1", "name": "Engine"})
    client.put(f"/api/projects/{project}/components/CMP-1", json={"name": "Turbo Engine"})

    res = client.get(f"/api/projects/{project}/history/CMP-1")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) >= 1
    update_entry = entries[0]
    assert update_entry["action"] == "update"
    assert "name" in update_entry["changes"]
    assert update_entry["changes"]["name"]["before"] == "Engine"
    assert update_entry["changes"]["name"]["after"] == "Turbo Engine"


def test_change_request_history(client, project):
    """A change request created then updated appears in history."""
    client.post(f"/api/projects/{project}/change-requests", json={
        "id": "CR-HIST", "title": "Old Title", "urgency": "low"})
    client.put(f"/api/projects/{project}/change-requests/CR-HIST", json={"title": "New Title"})

    res = client.get(f"/api/projects/{project}/history/CR-HIST")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) >= 1
    update_entry = entries[0]
    assert update_entry["action"] == "update"
    assert "title" in update_entry["changes"]
    assert update_entry["changes"]["title"]["before"] == "Old Title"
    assert update_entry["changes"]["title"]["after"] == "New Title"


def test_entity_with_no_history_returns_empty_list(client, project):
    """An id that has no history (never created/edited) returns [] with status 200."""
    res = client.get(f"/api/projects/{project}/history/NO-SUCH-ID")
    assert res.status_code == 200
    assert res.json() == []


def test_requirement_history_alias_is_404(client, project):
    """The legacy requirement-specific history route is removed; the generic
    route serves requirements and everything else."""
    from tests.conftest import make_req

    make_req(client, project, "R-HIST", name="Original Name")
    client.put(f"/api/projects/{project}/requirements/R-HIST", json={"name": "New Name"})

    # Generic route still works.
    via_generic = client.get(f"/api/projects/{project}/history/R-HIST")
    assert via_generic.status_code == 200
    assert len(via_generic.json()) >= 1

    # Old alias is gone.
    res = client.get(f"/api/projects/{project}/requirements/R-HIST/history")
    assert res.status_code == 404, res.text


def test_invalid_item_id_returns_400(client, project):
    """An id containing `..` (not as a standalone path segment, which Starlette
    normalises away before routing) is rejected by safe_id with 400."""
    res = client.get(f"/api/projects/{project}/history/test..invalid")
    assert res.status_code == 400
