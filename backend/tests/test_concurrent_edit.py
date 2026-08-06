"""Tests for the opt-in If-Match precondition on entity PUT routes.

The precondition prevents silent overwrites: a client that loaded the record,
held it open while someone else saved, and then saved their own changes would
otherwise erase the other person's edit with no warning and no history trace.
"""

from __future__ import annotations

from tests.conftest import make_req


def test_two_writes_with_stale_if_match_first_200_second_409(client, project):
    """A stale token is refused — the first write succeeds, the second 409s."""
    # Create a requirement and read its initial modified timestamp.
    req = make_req(client, project, "REQ-001", name="original")
    initial_modified = req["modified"]

    # First write with the initial token — should succeed.
    res1 = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "first writer"},
        headers={"If-Match": initial_modified},
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["name"] == "first writer"

    # Second write with the *same* stale token — must return 409.
    res2 = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "second writer"},
        headers={"If-Match": initial_modified},
    )
    assert res2.status_code == 409, res2.text


def test_409_does_not_overwrite_content(client, project):
    """A 409 must not have written anything — the stored record stays at the
    first writer's value."""
    req = make_req(client, project, "REQ-001", name="original")
    initial_modified = req["modified"]

    # First write succeeds.
    client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "first writer", "description": "first desc"},
        headers={"If-Match": initial_modified},
    )

    # Stale write fails.
    stale = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "second writer", "description": "second desc"},
        headers={"If-Match": initial_modified},
    )
    assert stale.status_code == 409

    # The stored record still holds the first writer's values.
    current = client.get(f"/api/projects/{project}/requirements/REQ-001").json()
    assert current["name"] == "first writer"
    assert current["description"] == "first desc"


def test_no_if_match_header_is_backward_compatible(client, project):
    """Omitting If-Match must behave exactly as before — no check, 200."""
    make_req(client, project, "REQ-001", name="original")

    # A write without If-Match succeeds.
    res = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "changed"},
    )
    assert res.status_code == 200, res.text

    # A second write without If-Match also succeeds (last-write-wins).
    res2 = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "changed again"},
    )
    assert res2.status_code == 200, res2.text


def test_current_token_allows_write(client, project):
    """A client that holds the latest modified token may write."""
    make_req(client, project, "REQ-001", name="original")

    # After a write, GET the fresh modified.
    client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "first edit"},
    )
    current = client.get(f"/api/projects/{project}/requirements/REQ-001").json()
    fresh_modified = current["modified"]

    # Write with the fresh token — succeeds.
    res = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "second edit"},
        headers={"If-Match": fresh_modified},
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "second edit"


def test_409_detail_names_entity_id(client, project):
    """The 409 body must include the entity id so the message is actionable."""
    req = make_req(client, project, "REQ-001", name="original")
    initial_modified = req["modified"]

    # Change the record so the token goes stale.
    client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "first writer"},
    )

    res = client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "second writer"},
        headers={"If-Match": initial_modified},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "REQ-001" in detail


def test_precondition_is_per_entity(client, project):
    """A stale token for REQ-1 must not block a write to REQ-2."""
    make_req(client, project, "REQ-001", name="req one")
    req2 = make_req(client, project, "REQ-002", name="req two")

    # Change REQ-1 to make REQ-1's token stale.
    client.put(
        f"/api/projects/{project}/requirements/REQ-001",
        json={"name": "req one changed"},
    )

    # Write REQ-2 using its own original (still current) token — should succeed
    # because REQ-2 hasn't been touched.
    res = client.put(
        f"/api/projects/{project}/requirements/REQ-002",
        json={"name": "req two changed"},
        headers={"If-Match": req2["modified"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "req two changed"


def test_precondition_on_specification(client, project):
    """The check also guards specifications."""
    res = client.post(
        f"/api/projects/{project}/specifications",
        json={"id": "SPEC-1", "name": "spec one"},
    )
    assert res.status_code == 201
    spec = client.get(f"/api/projects/{project}/specifications/SPEC-1").json()
    original_modified = spec["modified"]

    # First write succeeds.
    r1 = client.put(
        f"/api/projects/{project}/specifications/SPEC-1",
        json={"name": "first"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200

    # Stale write is refused.
    r2 = client.put(
        f"/api/projects/{project}/specifications/SPEC-1",
        json={"name": "second"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409
    assert "SPEC-1" in r2.json()["detail"]


def test_precondition_on_risk(client, project):
    """The check guards risks."""
    res = client.post(
        f"/api/projects/{project}/risks",
        json={"id": "RSK-1", "title": "risk one", "severity": "high",
              "likelihood": "medium"},
    )
    assert res.status_code == 201
    original_modified = res.json()["modified"]

    # First write succeeds.
    r1 = client.put(
        f"/api/projects/{project}/risks/RSK-1",
        json={"title": "first"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200

    # Stale write is refused.
    r2 = client.put(
        f"/api/projects/{project}/risks/RSK-1",
        json={"title": "second"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409
    assert "RSK-1" in r2.json()["detail"]


def test_precondition_on_change_request(client, project):
    """The check guards change requests."""
    # Need at least one requirement to link for a valid change request.
    make_req(client, project, "REQ-001")
    res = client.post(
        f"/api/projects/{project}/change-requests",
        json={"id": "CR-1", "title": "cr one", "description": "desc",
              "rationale": "because", "urgency": "low",
              "affected_requirements": ["REQ-001"]},
    )
    assert res.status_code == 201
    original_modified = res.json()["modified"]

    # First write succeeds.
    r1 = client.put(
        f"/api/projects/{project}/change-requests/CR-1",
        json={"title": "first"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200

    # Stale write is refused.
    r2 = client.put(
        f"/api/projects/{project}/change-requests/CR-1",
        json={"title": "second"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409
    assert "CR-1" in r2.json()["detail"]


def test_precondition_on_decision(client, project):
    """The check guards decisions."""
    res = client.post(
        f"/api/projects/{project}/decisions",
        json={"id": "DEC-1", "title": "dec one",
              "context": "ctx", "decision": "do it"},
    )
    assert res.status_code == 201
    original_modified = res.json()["modified"]

    # First write succeeds.
    r1 = client.put(
        f"/api/projects/{project}/decisions/DEC-1",
        json={"title": "first"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200

    # Stale write is refused.
    r2 = client.put(
        f"/api/projects/{project}/decisions/DEC-1",
        json={"title": "second"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409
    assert "DEC-1" in r2.json()["detail"]


def test_precondition_on_component(client, project):
    """The check guards components.

    Components were named in this task's scope but their route lives in
    `component_routes.py`, which the delegated pass left alone because the
    file was not in the spec's Files list. They are edited from a full-record
    form on the component detail page, exactly like requirements, so an
    unguarded route there meant the one entity most likely to be edited by
    two people at once was the one entity not protected.
    """
    res = client.post(
        f"/api/projects/{project}/components",
        json={"id": "C-1", "name": "Wing", "type": "assembly"},
    )
    assert res.status_code in (200, 201)
    original_modified = res.json()["modified"]

    r1 = client.put(
        f"/api/projects/{project}/components/C-1",
        json={"name": "first"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200

    r2 = client.put(
        f"/api/projects/{project}/components/C-1",
        json={"name": "second"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409
    assert "C-1" in r2.json()["detail"]

    # The refusal must not have written: the first writer's value stands.
    got = client.get(f"/api/projects/{project}/components/C-1").json()
    assert got["name"] == "first"


def test_component_without_if_match_is_unaffected(client, project):
    """The backward-compatibility guarantee, asserted for components too."""
    client.post(
        f"/api/projects/{project}/components",
        json={"id": "C-2", "name": "Spar", "type": "part"},
    )
    r = client.put(f"/api/projects/{project}/components/C-2", json={"name": "renamed"})
    assert r.status_code == 200
    assert client.get(f"/api/projects/{project}/components/C-2").json()["name"] == "renamed"
