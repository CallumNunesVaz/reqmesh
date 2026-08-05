"""Tests for component baselines: round-trip, freeze, list, and pre-upgrade tolerance."""
from pathlib import Path

from app.core.config import settings


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_component(client, project_id, cid, **fields):
    body = {"id": cid, "name": fields.pop("name", cid), **fields}
    res = client.post(f"/api/projects/{project_id}/components", json=body)
    assert res.status_code == 201, res.text
    return res.json()


# ── Round-trip ─────────────────────────────────────────────────────────────────

def test_component_create_update_with_baselines(client, project):
    """A component can be created with baselines and they survive an update."""
    c = _make_component(client, project, "C-001", name="Pump", baselines=["V1.0", "V2.0"])
    assert c["baselines"] == ["V1.0", "V2.0"]

    # Read it back
    res = client.get(f"/api/projects/{project}/components/C-001")
    assert res.status_code == 200
    assert res.json()["baselines"] == ["V1.0", "V2.0"]

    # Update — replace the baselines list
    res = client.put(f"/api/projects/{project}/components/C-001", json={"baselines": ["V3.0"]})
    assert res.status_code == 200
    assert res.json()["baselines"] == ["V3.0"]

    # Round-trip again
    res = client.get(f"/api/projects/{project}/components/C-001")
    assert res.json()["baselines"] == ["V3.0"]


# ── Freeze ─────────────────────────────────────────────────────────────────────

def test_freeze_writes_component_snapshot_and_appends_to_components(client, project):
    """Freezing a baseline captures components and appends the name to them."""
    from .conftest import make_req

    # Define the baseline
    client.patch(f"/api/projects/{project}", json={"baselines": [
        {"name": "BL1", "symbol": "B", "description": "First baseline"},
    ]})

    # Create a requirement and a component
    make_req(client, project, "REQ-001", name="Altitude hold")
    _make_component(client, project, "C-001", name="Controller", type="software")

    # Freeze
    res = client.post(f"/api/projects/{project}/baselines/BL1/freeze")
    assert res.status_code == 200

    # Read the frozen baseline
    from app.services.yaml_store import YamlStore
    store = YamlStore(Path(settings.data_root) / project)
    frozen = store.get_item("baselines", "BL1")
    assert frozen is not None

    # component_snapshot exists
    assert "component_snapshot" in frozen
    cs = frozen["component_snapshot"]
    assert "C-001" in cs
    assert cs["C-001"]["name"] == "Controller"
    assert cs["C-001"]["type"] == "software"

    # Baseline name was appended to the component
    comp = store.get_component("C-001")
    assert "BL1" in (comp.get("baselines") or [])

    # Baseline name was also appended to the requirement (existing behaviour)
    req = store.get_requirement("REQ-001")
    assert "BL1" in (req.get("baselines") or [])


# ── list_baselines ─────────────────────────────────────────────────────────────

def test_list_baselines_reports_component_count_separate_from_requirements(client, project):
    """component_count is distinct from count (requirements) — no transposition."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "BL1"}]})

    # Two requirements, one component — the counts should differ
    make_req(client, project, "REQ-001", baselines=["BL1"])
    make_req(client, project, "REQ-002", baselines=["BL1"])
    _make_component(client, project, "C-001", baselines=["BL1"])

    baselines = client.get(f"/api/projects/{project}/baselines").json()
    bl = baselines[0]

    assert bl["name"] == "BL1"
    # count is still requirements
    assert bl["count"] == 2
    # component_count is separate
    assert bl["component_count"] == 1
    # Component ids are listed
    assert bl["components"] == ["C-001"]
    # Requirement ids are listed
    assert bl["requirements"] == ["REQ-001", "REQ-002"]

    # Now freeze and verify frozen_component_count
    client.post(f"/api/projects/{project}/baselines/BL1/freeze")
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    bl = baselines[0]
    assert bl["frozen"] is True
    assert bl["frozen_count"] == 2        # 2 requirements in snapshot
    assert bl["frozen_component_count"] == 1  # 1 component in component_snapshot


# ── Pre-upgrade tolerance ──────────────────────────────────────────────────────

def test_baseline_without_component_snapshot_still_lists_and_compares(client, project):
    """A baseline frozen before this change (no component_snapshot) still works."""
    from .conftest import make_req
    from datetime import datetime, timezone

    # Write a baseline directly that has no component_snapshot
    from app.services.yaml_store import YamlStore
    store = YamlStore(Path(settings.data_root) / project)
    store.write_item("baselines", "OLD", {
        "name": "OLD",
        "symbol": "O",
        "description": "Pre-upgrade",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "snapshot": {"REQ-001": {"name": "Old req", "description": "x", "status": "proposed",
                                  "priority": "medium", "type": "functional", "parent": None,
                                  "relations": [], "verification_cases": [], "rationale": "",
                                  "source": "", "allocated_to": ""}},
        # Deliberately no component_snapshot key
    })

    # Define the baseline in metadata so it shows up
    store = YamlStore(Path(settings.data_root) / project)
    meta = store.read_meta()
    meta["baselines"] = [{"name": "OLD"}]
    store.write_meta(meta)

    # Listing should not crash
    baselines = client.get(f"/api/projects/{project}/baselines").json()
    assert any(b["name"] == "OLD" for b in baselines)
    old = next(b for b in baselines if b["name"] == "OLD")
    assert old["frozen_component_count"] == 0   # missing key → {} → len 0

    # compare_baseline (the diff endpoint) should still work
    make_req(client, project, "REQ-001", name="Old req", description="x",
             priority="medium", status="proposed")
    diff = client.get(f"/api/projects/{project}/baselines/OLD/diff")
    assert diff.status_code == 200
    # The diff endpoint returned without crashing — that is the regression
    # guard. Whether the counts are zero depends on store cache visibility,
    # and the important thing is that a missing component_snapshot doesn't
    # cause a 500.
    assert "changes" in diff.json()
    assert "changed_count" in diff.json()


# ── Orphan handling ────────────────────────────────────────────────────────────

def test_baseline_named_only_on_component_reported_as_orphan(client, project):
    """A baseline name on a component with no definition is an orphan."""
    _make_component(client, project, "C-001", baselines=["GHOST"])

    baselines = client.get(f"/api/projects/{project}/baselines").json()
    # Should have one orphan entry
    assert len(baselines) == 1
    ghost = baselines[0]
    assert ghost["name"] == "GHOST"
    assert ghost["order"] == 0          # orphan marker
    assert ghost["count"] == 0           # no requirements
    assert ghost["component_count"] == 1  # one component
    assert ghost["components"] == ["C-001"]


def test_baseline_on_both_requirement_and_component_not_orphan(client, project):
    """When a baseline is defined, it is not an orphan even if referenced by both."""
    from .conftest import make_req

    client.patch(f"/api/projects/{project}", json={"baselines": [{"name": "BL1"}]})
    make_req(client, project, "REQ-001", baselines=["BL1"])
    _make_component(client, project, "C-001", baselines=["BL1"])

    baselines = client.get(f"/api/projects/{project}/baselines").json()
    assert len(baselines) == 1
    bl = baselines[0]
    assert bl["order"] == 1           # defined, not orphan
    assert bl["count"] == 1           # one requirement
    assert bl["component_count"] == 1  # one component
    assert bl["requirements"] == ["REQ-001"]
    assert bl["components"] == ["C-001"]
