"""Risks, change requests, decisions, specs and analyses can point at components.

Every link in the registry used to target `requirements`, except the two parent
trees — so "this actuator is a single point of failure" was unsayable: a risk
could name the text describing a part but not the part.

The routes needed no change: the update handlers take the Pydantic `*Update`
models, so adding the fields there carried them through. What these tests prove
is the half that is easy to get wrong — that the registry rows are live, that
traversal picked them up with no traversal code written, and that a component
link is not confused with a requirement link of the same id.
"""


def _project(client, pid):
    client.post("/api/projects", json={"id": pid, "name": pid.upper()})
    return pid


def _component(client, pid, cid, name="Wing"):
    return client.post(f"/api/projects/{pid}/components", json={"id": cid, "name": name})


def test_risk_round_trips_both_component_fields(client):
    p = _project(client, "cl1")
    _component(client, p, "C-1")
    _component(client, p, "C-2", "Spar")
    client.post(f"/api/projects/{p}/risks", json={"id": "RSK-1", "title": "r", "severity": "high"})

    client.put(f"/api/projects/{p}/risks/RSK-1", json={
        "linked_components": ["C-1"], "mitigating_components": ["C-2"]})

    got = next(r for r in client.get(f"/api/projects/{p}/risks").json()["items"] if r["id"] == "RSK-1")
    assert got["linked_components"] == ["C-1"]
    assert got["mitigating_components"] == ["C-2"]


def test_change_request_round_trips_affected_components(client):
    p = _project(client, "cl2")
    _component(client, p, "C-1")
    client.post(f"/api/projects/{p}/change-requests", json={"id": "CR-1", "title": "c"})

    client.put(f"/api/projects/{p}/change-requests/CR-1",
               json={"affected_components": ["C-1"]})

    got = next(c for c in client.get(f"/api/projects/{p}/change-requests").json()["items"]
               if c["id"] == "CR-1")
    assert got["affected_components"] == ["C-1"]


def test_decision_round_trips_linked_components(client):
    p = _project(client, "cl3")
    _component(client, p, "C-1")
    client.post(f"/api/projects/{p}/decisions", json={"id": "DEC-1", "title": "d"})

    client.put(f"/api/projects/{p}/decisions/DEC-1", json={"linked_components": ["C-1"]})

    got = next(d for d in client.get(f"/api/projects/{p}/decisions").json()["items"]
               if d["id"] == "DEC-1")
    assert got["linked_components"] == ["C-1"]


def test_specification_and_analysis_round_trip(client):
    p = _project(client, "cl4")
    _component(client, p, "C-1")
    client.post(f"/api/projects/{p}/specifications", json={"id": "SPEC-1", "name": "s"})
    client.post(f"/api/projects/{p}/analysis", json={"id": "AC-1", "name": "a"})

    client.put(f"/api/projects/{p}/specifications/SPEC-1", json={"components": ["C-1"]})
    client.put(f"/api/projects/{p}/analysis/AC-1", json={"scope_components": ["C-1"]})

    spec = next(s for s in client.get(f"/api/projects/{p}/specifications").json()["items"]
                if s["id"] == "SPEC-1")
    case = next(a for a in client.get(f"/api/projects/{p}/analysis").json()["items"]
                if a["id"] == "AC-1")
    assert spec["components"] == ["C-1"]
    assert case["scope_components"] == ["C-1"]


def test_deleting_a_referenced_component_is_blocked(client):
    """The payoff: no traversal code was written, so this proves the rows are live."""
    p = _project(client, "cl5")
    _component(client, p, "C-1")
    client.post(f"/api/projects/{p}/risks", json={"id": "RSK-1", "title": "r"})
    client.put(f"/api/projects/{p}/risks/RSK-1", json={"linked_components": ["C-1"]})

    res = client.delete(f"/api/projects/{p}/components/C-1")
    assert res.status_code == 409
    assert "risk" in res.text.lower()


def test_component_link_does_not_cross_link_a_same_named_requirement(client):
    """Ids are unique per collection, not globally.

    A risk pointing at component `X` must not register as a referrer of a
    requirement that happens to also be called `X`, or deleting that unrelated
    requirement would be blocked for no reason.
    """
    p = _project(client, "cl6")
    _component(client, p, "SHARED1")
    client.post(f"/api/projects/{p}/requirements", json={"id": "SHARED1", "title": "req"})
    client.post(f"/api/projects/{p}/risks", json={"id": "RSK-1", "title": "r"})
    client.put(f"/api/projects/{p}/risks/RSK-1", json={"linked_components": ["SHARED1"]})

    # The requirement is not referenced by that risk, so it deletes cleanly.
    assert client.delete(f"/api/projects/{p}/requirements/SHARED1").status_code == 200
    # The component still is.
    assert client.delete(f"/api/projects/{p}/components/SHARED1").status_code == 409


def test_dangling_component_id_is_reported_not_rejected(client):
    """Entity files arrive by git pull as well as by API, so a bad id is a
    finding for the integrity check rather than a write-time rejection —
    exactly how `linked_requirements` already behaves."""
    p = _project(client, "cl7")
    client.post(f"/api/projects/{p}/risks", json={"id": "RSK-1", "title": "r"})

    assert client.put(f"/api/projects/{p}/risks/RSK-1",
                      json={"linked_components": ["NOPE"]}).status_code == 200

    issues = client.get(f"/api/projects/{p}/validate").json()
    found = [i for i in (issues.get("issues") or issues)
             if isinstance(i, dict)
             and i.get("type") == "dangling_reference"
             and i.get("target") == "NOPE"]
    assert found, "a dangling component reference should be reported"
    assert found[0]["target_collection"] == "components"


def test_risk_without_the_new_fields_still_loads(client):
    """A project written before these fields existed must be unaffected.

    The create route writes a subset of the model, so a fresh risk carries
    `linked_requirements` but not `mitigating_requirements` — and now not the
    component fields either. That inconsistency predates this work; what matters
    here is that their absence is harmless, so the assertion is "absent or
    empty", not "present and empty". Asserting the stricter shape would be
    asserting a contract the API does not offer.
    """
    p = _project(client, "cl8")
    client.post(f"/api/projects/{p}/risks", json={"id": "RSK-1", "title": "r"})

    got = next(r for r in client.get(f"/api/projects/{p}/risks").json()["items"] if r["id"] == "RSK-1")
    assert not got.get("linked_components")
    assert not got.get("mitigating_components")

    # And setting one afterwards works, so the absence is not a stuck state.
    client.put(f"/api/projects/{p}/risks/RSK-1", json={"linked_components": []})
    assert client.get(f"/api/projects/{p}/risks").json()["items"][0].get("linked_components") == []
