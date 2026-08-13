"""Link targets are validated on write, for every id-bearing field.

Before this, ``component_routes._validate_links`` rejected a dangling
``satisfies`` / ``verification_cases`` entry but nothing guarded the other five
fields that point at another collection — a typo in a risk's linked requirement
was accepted silently and surfaced only if someone ran ``GET /validate``.

These tests go through the HTTP routes, which is the only path a real client
uses, and cover both directions per field: a missing id is rejected, a real id
is accepted. The one field that legitimately names ids that do not exist yet is
``change_request.creates``, and it must keep working.
"""
from __future__ import annotations


def _req(client, project, req_id):
    res = client.post(f"/api/projects/{project}/requirements",
                      json={"id": req_id, "name": req_id})
    assert res.status_code == 201, res.text
    return req_id


def _vc(client, project, vc_id):
    res = client.post(f"/api/projects/{project}/verification",
                      json={"id": vc_id, "name": vc_id, "method": "test"})
    assert res.status_code == 201, res.text
    return vc_id


# ── risk.linked_requirements ──────────────────────────────────────────────────

def test_risk_linked_requirement_missing_is_rejected(client, project):
    client.post(f"/api/projects/{project}/risks", json={"id": "RSK-1", "title": "r"})
    res = client.put(f"/api/projects/{project}/risks/RSK-1",
                     json={"linked_requirements": ["NOPE"]})
    assert res.status_code == 400
    assert "Requirement not found: NOPE" in res.json()["detail"]


def test_risk_linked_requirement_real_is_accepted(client, project):
    _req(client, project, "REQ-1")
    client.post(f"/api/projects/{project}/risks", json={"id": "RSK-1", "title": "r"})
    res = client.put(f"/api/projects/{project}/risks/RSK-1",
                     json={"linked_requirements": ["REQ-1"]})
    assert res.status_code == 200, res.text


# ── decision.linked_requirements ──────────────────────────────────────────────

def test_decision_linked_requirement_missing_is_rejected(client, project):
    res = client.post(f"/api/projects/{project}/decisions",
                      json={"id": "DEC-1", "title": "d",
                            "linked_requirements": ["NOPE"]})
    assert res.status_code == 400
    assert "Requirement not found: NOPE" in res.json()["detail"]


def test_decision_linked_requirement_real_is_accepted(client, project):
    _req(client, project, "REQ-1")
    res = client.post(f"/api/projects/{project}/decisions",
                      json={"id": "DEC-1", "title": "d",
                            "linked_requirements": ["REQ-1"]})
    assert res.status_code == 201, res.text


# ── specification.requirements ────────────────────────────────────────────────

def test_specification_requirements_missing_is_rejected(client, project):
    client.post(f"/api/projects/{project}/specifications",
                json={"id": "SPEC-1", "name": "s"})
    res = client.put(f"/api/projects/{project}/specifications/SPEC-1",
                     json={"requirements": ["NOPE"]})
    assert res.status_code == 400
    assert "Requirement not found: NOPE" in res.json()["detail"]


def test_specification_requirements_real_is_accepted(client, project):
    _req(client, project, "REQ-1")
    client.post(f"/api/projects/{project}/specifications",
                json={"id": "SPEC-1", "name": "s"})
    res = client.put(f"/api/projects/{project}/specifications/SPEC-1",
                     json={"requirements": ["REQ-1"]})
    assert res.status_code == 200, res.text


# ── change_request.affected_requirements ─────────────────────────────────────

def test_change_request_affected_requirement_missing_is_rejected(client, project):
    res = client.post(f"/api/projects/{project}/change-requests",
                      json={"id": "CR-1", "title": "c",
                            "affected_requirements": ["NOPE"]})
    assert res.status_code == 400
    assert "Requirement not found: NOPE" in res.json()["detail"]


def test_change_request_affected_requirement_real_is_accepted(client, project):
    _req(client, project, "REQ-1")
    res = client.post(f"/api/projects/{project}/change-requests",
                      json={"id": "CR-1", "title": "c",
                            "affected_requirements": ["REQ-1"]})
    assert res.status_code == 201, res.text


def test_change_request_creates_may_name_absent_ids(client, project):
    """The regression this task is most likely to cause: a CR that proposes to
    *create* a requirement names an id that does not exist yet. The client lists
    that id in both ``creates`` and ``affected_requirements``, so the write-time
    check must exempt ``creates`` ids — validating them would break the feature."""
    res = client.post(f"/api/projects/{project}/change-requests", json={
        "id": "CR-NEW",
        "title": "new requirement",
        "changes": {"NEW-0001": {"name": "Fresh", "description": "proposed"}},
        "creates": ["NEW-0001"],
        "affected_requirements": ["NEW-0001"],
    })
    assert res.status_code == 201, res.text
    assert res.json()["creates"] == ["NEW-0001"]


# ── requirement.relations[].target ────────────────────────────────────────────

def test_relation_target_missing_requirement_is_rejected(client, project):
    res = client.post(f"/api/projects/{project}/requirements",
                      json={"id": "REQ-1", "name": "r",
                            "relations": [{"type": "refines", "target": "NOPE"}]})
    assert res.status_code == 400
    assert "Relation target not found: NOPE" in res.json()["detail"]


def test_relation_target_real_requirement_is_accepted(client, project):
    _req(client, project, "REQ-1")
    res = client.post(f"/api/projects/{project}/requirements",
                      json={"id": "REQ-2", "name": "r",
                            "relations": [{"type": "refines", "target": "REQ-1"}]})
    assert res.status_code == 201, res.text


def test_relation_target_missing_verification_case_is_rejected(client, project):
    res = client.post(f"/api/projects/{project}/requirements",
                      json={"id": "REQ-1", "name": "r",
                            "relations": [{"type": "verified_by", "target": "NOPE"}]})
    assert res.status_code == 400
    assert "Relation target not found: NOPE" in res.json()["detail"]


def test_relation_target_real_verification_case_is_accepted(client, project):
    _vc(client, project, "VC-1")
    res = client.post(f"/api/projects/{project}/requirements",
                      json={"id": "REQ-1", "name": "r",
                            "relations": [{"type": "verified_by", "target": "VC-1"}]})
    assert res.status_code == 201, res.text


def test_relation_update_with_missing_target_is_rejected(client, project):
    _req(client, project, "REQ-1")
    res = client.put(f"/api/projects/{project}/requirements/REQ-1",
                     json={"relations": [{"type": "refines", "target": "NOPE"}]})
    assert res.status_code == 400
    assert "Relation target not found: NOPE" in res.json()["detail"]


# ── Round-trips for the two `*Create` model gaps ─────────────────────────────

def test_component_create_preserves_attributes(client, project):
    """ComponentCreate omitted `attributes`, so the bulk-delete recreate path
    dropped them. Create through the route and assert the field survives."""
    res = client.post(f"/api/projects/{project}/components", json={
        "id": "C-1", "name": "Wing",
        "attributes": [{"key": "material", "value": "aluminium"}],
    })
    assert res.status_code == 201, res.text
    got = client.get(f"/api/projects/{project}/components/C-1").json()
    assert got["attributes"] == [{"key": "material", "value": "aluminium"}]


def test_decision_create_preserves_full_draft(client, project):
    """DecisionRecordCreate dropped rationale, consequences, status and the
    linked_* fields, so a new decision lost all of them. Create through the
    route with every field populated and assert they all survive."""
    _req(client, project, "REQ-1")
    res = client.post(f"/api/projects/{project}/decisions", json={
        "id": "DEC-1",
        "title": "Choose the actuator",
        "decision": "Use the rotary actuator",
        "rationale": "Cheaper and proven",
        "consequences": "Longer lead time",
        "status": "accepted",
        "linked_requirements": ["REQ-1"],
        "linked_components": ["C-1"],
    })
    assert res.status_code == 201, res.text
    got = next(d for d in client.get(f"/api/projects/{project}/decisions").json()["items"]
               if d["id"] == "DEC-1")
    assert got["rationale"] == "Cheaper and proven"
    assert got["consequences"] == "Longer lead time"
    assert got["status"] == "accepted"
    assert got["linked_requirements"] == ["REQ-1"]
    assert got["linked_components"] == ["C-1"]
