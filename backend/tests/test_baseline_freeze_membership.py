"""Freeze captures only ticked membership — not every record in the project.

Before this change, ``freeze_baseline`` iterated *all* requirements and
components and appended the baseline name to each, ignoring the membership the
allocation matrix exists to curate.  These tests prove that the sweep is gone:
only ticked records land in the snapshot, and no record is modified by the
freeze.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.yaml_store import YamlStore
from tests.conftest import make_req


def _store(project_id: str) -> YamlStore:
    return YamlStore(Path(settings.data_root) / project_id)


def _make_component(client, project_id, cid, **fields):
    body = {"id": cid, "name": cid, **fields}
    res = client.post(f"/api/projects/{project_id}/components", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _tick(client, project_id, req_id, baseline_name):
    res = client.put(
        f"/api/projects/{project_id}/requirements/{req_id}",
        json={"baselines": [baseline_name]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _tick_component(client, project_id, comp_id, baseline_name):
    res = client.put(
        f"/api/projects/{project_id}/components/{comp_id}",
        json={"baselines": [baseline_name]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _freeze(client, project_id, name):
    res = client.post(f"/api/projects/{project_id}/baselines/{name}/freeze")
    assert res.status_code == 200, res.text
    return res.json()


# ── requirements ─────────────────────────────────────────────────────────────


def test_freeze_captures_only_ticked_requirements(client, project):
    """Three requirements, one ticked.  After freeze the snapshot holds exactly
    that one, and R-2/R-3 still have empty baselines."""
    make_req(client, project, "R-1")
    make_req(client, project, "R-2")
    make_req(client, project, "R-3")

    _tick(client, project, "R-1", "SRR")

    _freeze(client, project, "SRR")

    # Only R-1 is in the snapshot.
    frozen = _store(project).get_item("baselines", "SRR")
    assert frozen is not None
    snap = frozen["snapshot"]
    assert set(snap.keys()) == {"R-1"}

    # R-2 and R-3 were NOT swept — baselines stay empty.
    r2 = client.get(f"/api/projects/{project}/requirements/R-2").json()
    r3 = client.get(f"/api/projects/{project}/requirements/R-3").json()
    assert r2.get("baselines") == [] or r2.get("baselines") is None
    assert r3.get("baselines") == [] or r3.get("baselines") is None


# ── components ───────────────────────────────────────────────────────────────


def test_freeze_captures_only_ticked_components(client, project):
    """Three components, one ticked.  After freeze only that one is captured."""
    _make_component(client, project, "C-1")
    _make_component(client, project, "C-2")
    _make_component(client, project, "C-3")

    _tick_component(client, project, "C-1", "SRR")

    _freeze(client, project, "SRR")

    frozen = _store(project).get_item("baselines", "SRR")
    assert frozen is not None
    csnap = frozen["component_snapshot"]
    assert set(csnap.keys()) == {"C-1"}


# ── empty baseline ───────────────────────────────────────────────────────────


def test_freeze_with_nothing_ticked_succeeds(client, project):
    """Freezing a baseline nobody is ticked into succeeds with empty snapshots."""
    make_req(client, project, "R-1")
    _make_component(client, project, "C-1")

    result = _freeze(client, project, "SRR")

    assert result["requirements"] == 0

    frozen = _store(project).get_item("baselines", "SRR")
    assert frozen is not None
    assert frozen["snapshot"] == {}
    assert frozen["component_snapshot"] == {}


# ── two baselines ────────────────────────────────────────────────────────────


def test_requirement_ticked_into_two_baselines(client, project):
    """A requirement ticked into two baselines is captured by both freezes and
    belongs to both afterwards."""
    make_req(client, project, "R-DUAL")

    client.put(
        f"/api/projects/{project}/requirements/R-DUAL",
        json={"baselines": ["SRR", "PDR"]},
    )

    _freeze(client, project, "SRR")
    _freeze(client, project, "PDR")

    srr = _store(project).get_item("baselines", "SRR")
    pdr = _store(project).get_item("baselines", "PDR")
    assert srr is not None
    assert pdr is not None

    assert "R-DUAL" in srr["snapshot"]
    assert "R-DUAL" in pdr["snapshot"]

    req = client.get(f"/api/projects/{project}/requirements/R-DUAL").json()
    assert set(req["baselines"]) == {"SRR", "PDR"}


# ── modified is untouched ────────────────────────────────────────────────────


def test_freeze_does_not_change_modified(client, project):
    """Proof that the write-back loops are gone: freezing must not modify any
    requirement."""
    make_req(client, project, "R-1")
    _tick(client, project, "R-1", "SRR")
    make_req(client, project, "R-2")
    make_req(client, project, "R-3")

    before = {}
    for rid in ["R-1", "R-2", "R-3"]:
        req = client.get(f"/api/projects/{project}/requirements/{rid}").json()
        before[rid] = req["modified"]

    _freeze(client, project, "SRR")

    for rid in ["R-1", "R-2", "R-3"]:
        req = client.get(f"/api/projects/{project}/requirements/{rid}").json()
        assert req["modified"] == before[rid], f"{rid} modified changed"
