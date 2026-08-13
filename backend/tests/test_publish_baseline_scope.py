"""Tests for baseline-scoped export and the three-filter intersection rule.

Uses a small, hand-built project (two components, two baselines, three groups)
so the exported set can be asserted exactly, rather than reasoning about the
seeded demo's 57 requirements.

The critical property under test is that the three scope filters — subsystems,
components, baselines — combine by *intersection*, and that an omitted filter
(None) and an empty filter ([]) stay distinct: an empty filter exports nothing,
an absent filter exports everything.
"""
from __future__ import annotations

import pytest

from app.services.publisher import Publisher
from app.services.yaml_store import YamlStore

from .conftest import make_req


# ── fixtures ──────────────────────────────────────────────────────────────────


def _write_req(store: YamlStore, rid: str, parent: str | None = None,
               baselines: tuple[str, ...] = ()) -> None:
    store.create_requirement({
        "id": rid,
        "name": rid,
        "description": "",
        "type": "functional",
        "status": "proposed",
        "priority": "medium",
        "parent": parent,
        "rationale": "",
        "source": "",
        "verification_method": "test",
        "verification_status": "pending",
        "baselines": list(baselines),
        "allocated_to": "",
        "cascade_from": None,
        "attributes": [],
        "relations": [],
        "verification_cases": [],
        "references": [],
        "needs": [],
        "derived": False,
        "normative": True,
        "priorities": {},
        "reviewed": None,
    })


@pytest.fixture
def store(tmp_path):
    """Two components, two baselines, three requirement groups.

    Requirements (parent in brackets) and their baseline names:

        G1 [] — B1                 G2 [] — B2                 G3 [] — B1, B2
        └─ R1 — B1                 └─ R2 — B1, B2             ├─ R3 — B2
                                                            └─ R4 — B2

    Components and the requirements they satisfy: C1 → {R1, R2}, C2 → {R2, R3}.
    """
    s = YamlStore(tmp_path / "scoped")
    s.ensure_dirs()

    _write_req(s, "G1", baselines=("B1",))
    _write_req(s, "R1", parent="G1", baselines=("B1",))
    _write_req(s, "G2", baselines=("B2",))
    _write_req(s, "R2", parent="G2", baselines=("B1", "B2"))
    _write_req(s, "G3", baselines=("B1", "B2"))
    _write_req(s, "R3", parent="G3", baselines=("B2",))
    _write_req(s, "R4", parent="G3", baselines=("B2",))

    s.create_component({"id": "C1", "name": "Comp 1", "type": "part",
                        "parent": None, "satisfies": ["R1", "R2"]})
    s.create_component({"id": "C2", "name": "Comp 2", "type": "part",
                        "parent": None, "satisfies": ["R2", "R3"]})
    return s


def req_ids(pub: Publisher) -> set[str]:
    return {r["id"] for r in pub.reqs}


# ── per filter ────────────────────────────────────────────────────────────────


class TestSingleFilter:
    def test_components_only_c1(self, store):
        assert req_ids(Publisher(store, components=["C1"])) == {"R1", "R2"}

    def test_components_only_c2(self, store):
        assert req_ids(Publisher(store, components=["C2"])) == {"R2", "R3"}

    def test_baselines_only_b1(self, store):
        assert req_ids(Publisher(store, baselines=["B1"])) == {"G1", "R1", "R2", "G3"}

    def test_baselines_only_b2(self, store):
        assert req_ids(Publisher(store, baselines=["B2"])) == {"G2", "R2", "G3", "R3", "R4"}


# ── combinations — intersection, not union ────────────────────────────────────


class TestCombinations:
    def test_components_baselines_c1_b1(self, store):
        assert req_ids(Publisher(store, components=["C1"], baselines=["B1"])) == {"R1", "R2"}

    def test_components_baselines_c1_b2(self, store):
        # Union would be {R1, R2} ∪ {G2, R2, G3, R3, R4}; intersection is {R2}.
        assert req_ids(Publisher(store, components=["C1"], baselines=["B2"])) == {"R2"}

    def test_components_baselines_c2_b1(self, store):
        assert req_ids(Publisher(store, components=["C2"], baselines=["B1"])) == {"R2"}

    def test_components_baselines_c2_b2(self, store):
        assert req_ids(Publisher(store, components=["C2"], baselines=["B2"])) == {"R2", "R3"}

    def test_subsystems_baselines(self, store):
        # G3 subtree is {G3, R3, R4}; intersected with B1's {G1, R1, R2, G3}.
        assert req_ids(Publisher(store, subsystems=["G3"], baselines=["B1"])) == {"G3"}

    def test_subsystems_components(self, store):
        # G3 subtree ∩ C2's requirements.
        assert req_ids(Publisher(store, subsystems=["G3"], components=["C2"])) == {"R3"}

    def test_all_three(self, store):
        assert req_ids(Publisher(store, subsystems=["G3"], components=["C2"],
                                 baselines=["B2"])) == {"R3"}


# ── omitted vs empty ──────────────────────────────────────────────────────────


class TestOmittedVsEmpty:
    def test_omitted_baselines_exports_everything(self, store):
        assert req_ids(Publisher(store)) == {"G1", "R1", "G2", "R2", "G3", "R3", "R4"}

    def test_empty_baselines_exports_nothing(self, store):
        assert req_ids(Publisher(store, baselines=[])) == set()

    def test_empty_components_exports_nothing(self, store):
        assert req_ids(Publisher(store, components=[])) == set()

    def test_empty_subsystems_exports_nothing(self, store):
        assert req_ids(Publisher(store, subsystems=[])) == set()


# ── download route wiring ─────────────────────────────────────────────────────


class TestDownloadRoute:
    def test_baselines_param_filters(self, client, project):
        make_req(client, project, "R1", baselines=["B1"])
        make_req(client, project, "R2", baselines=["B2"])
        res = client.get(f"/api/projects/{project}/publish/download?format=md&baselines=B1")
        assert res.status_code == 200
        assert "R1" in res.text
        assert "R2" not in res.text

    def test_empty_baselines_param_exports_nothing(self, client, project):
        make_req(client, project, "R1", baselines=["B1"])
        res = client.get(f"/api/projects/{project}/publish/download?format=md&baselines=")
        assert res.status_code == 200
        assert "R1" not in res.text

    def test_absent_baselines_param_exports_everything(self, client, project):
        make_req(client, project, "R1", baselines=["B1"])
        make_req(client, project, "R2", baselines=["B2"])
        res = client.get(f"/api/projects/{project}/publish/download?format=md")
        assert res.status_code == 200
        assert "R1" in res.text
        assert "R2" in res.text
