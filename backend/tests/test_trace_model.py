"""Tests for all_links() and the GET /trace-model endpoint."""

import pytest
from pathlib import Path

from app.services.tracing import all_links
from app.services.yaml_store import YamlStore


def _store(project_id: str, tmp_path) -> YamlStore:
    from app.core.config import settings
    return YamlStore(Path(settings.data_root) / project_id)


def test_registry_derived_edges(client, project):
    """A component's ``satisfies`` appears with ``type: "satisfies"``
    and a risk's ``linked_requirements`` with ``type: "threatens"``."""
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ001", "name": "Recharge", "description": "x" * 30})
    client.post(f"/api/projects/{project}/components", json={
        "id": "COMP1", "name": "Battery", "satisfies": ["REQ001"]})
    # RiskCreate does not carry linked_requirements; create then update.
    client.post(f"/api/projects/{project}/risks", json={
        "id": "RSK1", "title": "Overheat", "severity": "high",
        "likelihood": "possible"})
    client.put(f"/api/projects/{project}/risks/RSK1", json={
        "linked_requirements": ["REQ001"]})

    res = client.get(f"/api/projects/{project}/trace-model")
    assert res.status_code == 200
    links = res.json()["links"]

    # The component→requirement edge.
    comp = next((l for l in links
                 if l["source"] == "COMP1" and l["target"] == "REQ001" and l["type"] == "satisfies"), None)
    assert comp is not None
    assert comp["holder"] == "components"
    assert comp["target_collection"] == "requirements"
    assert comp["stored"] is False

    # The risk→requirement edge (label "threatens").
    risk = next((l for l in links
                 if l["source"] == "RSK1" and l["target"] == "REQ001" and l["type"] == "threatens"), None)
    assert risk is not None
    assert risk["holder"] == "risks"
    assert risk["target_collection"] == "requirements"
    assert risk["stored"] is False


def test_hand_authored_traces_appear_as_stored(client, project):
    """Links from traces.yaml show up with ``stored: True``."""
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ001", "name": "A", "description": "x" * 30})
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ002", "name": "B", "description": "x" * 30})
    client.put(f"/api/projects/{project}/traces", json={
        "links": [{"source": "REQ001", "target": "REQ002", "type": "refines"}]})

    res = client.get(f"/api/projects/{project}/trace-model")
    assert res.status_code == 200
    links = res.json()["links"]

    trace = next((l for l in links
                  if l["source"] == "REQ001" and l["target"] == "REQ002" and l["type"] == "refines"), None)
    assert trace is not None
    assert trace["stored"] is True
    assert trace["holder"] == "traces"
    assert trace["target_collection"] == "traces"


def test_tree_links_are_excluded(client, project):
    """Parent edges (tree=True) must not appear — no edge whose type is
    ``"parent"``."""
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ001", "name": "Parent", "description": "x" * 30})
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ002", "name": "Child", "description": "x" * 30,
        "parent": "REQ001"})

    res = client.get(f"/api/projects/{project}/trace-model")
    assert res.status_code == 200
    links = res.json()["links"]

    # No edge should have type "parent".
    parent_edges = [l for l in links if l["type"] == "parent"]
    assert parent_edges == []

    # Double-check the relationship exists in the model (the parent field is set).
    rr = client.get(f"/api/projects/{project}/requirements/REQ002").json()
    assert rr["parent"] == "REQ001"


def test_deduplication_prefers_stored(client, project):
    """An edge present both in traces.yaml and via the registry appears once,
    with ``stored: True``."""
    # Registry edge: component COMP1 satisfies REQ001.
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ001", "name": "Req", "description": "x" * 30})
    client.post(f"/api/projects/{project}/components", json={
        "id": "COMP1", "name": "Motor", "satisfies": ["REQ001"]})

    # Hand-authored trace with the same (source, target, type).
    client.put(f"/api/projects/{project}/traces", json={
        "links": [{"source": "COMP1", "target": "REQ001", "type": "satisfies"}]})

    res = client.get(f"/api/projects/{project}/trace-model")
    assert res.status_code == 200
    links = res.json()["links"]

    matches = [l for l in links
               if l["source"] == "COMP1" and l["target"] == "REQ001" and l["type"] == "satisfies"]
    assert len(matches) == 1
    assert matches[0]["stored"] is True


def test_seeded_demo_has_far_more_than_8_links(workspace):
    """Against the seeded demo the total is far above the 8 in traces.yaml."""
    from app.services.demo_seed import seed_demo_project

    seed_demo_project(Path(workspace) / "projects")

    store = YamlStore(Path(workspace) / "projects" / "cessna-172")
    links = all_links(store)
    assert len(links) > 100, f"expected > 100 links, got {len(links)}"


def test_output_is_sorted_and_stable(client, project):
    """Two calls return the same sorted result."""
    client.post(f"/api/projects/{project}/requirements", json={
        "id": "REQ001", "name": "A", "description": "x" * 30})
    client.post(f"/api/projects/{project}/components", json={
        "id": "COMP1", "name": "C1", "satisfies": ["REQ001"]})
    client.post(f"/api/projects/{project}/components", json={
        "id": "COMP2", "name": "C2", "satisfies": ["REQ001"]})

    a = client.get(f"/api/projects/{project}/trace-model").json()["links"]
    b = client.get(f"/api/projects/{project}/trace-model").json()["links"]

    assert a == b
    # Verify it's sorted by (source, target, type).
    for i in range(len(a) - 1):
        assert (a[i]["source"], a[i]["target"], a[i]["type"]) <= \
               (a[i+1]["source"], a[i+1]["target"], a[i+1]["type"]), \
               f"unsorted at index {i}: {a[i]} vs {a[i+1]}"
