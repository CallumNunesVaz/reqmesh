"""Tests for the publisher's guard against requirement parent cycles.

A parent cycle on disk (hand-edited or git-pulled YAML) must truncate the
export, not recurse until the stack gives out and turn the report into a 500.
"""
from __future__ import annotations

from app.services.publisher import Publisher
from app.services.yaml_store import YamlStore


# ── helpers ───────────────────────────────────────────────────────────────────


def _write_req(store: YamlStore, rid: str, parent: str | None = None) -> None:
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
        "baselines": [],
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


def _store(tmp_path) -> YamlStore:
    s = YamlStore(tmp_path / "cycle")
    s.ensure_dirs()
    return s


# ── cycles ────────────────────────────────────────────────────────────────────


def test_two_node_cycle_renders_and_terminates(tmp_path):
    """REQ0001 <-> REQ0002 renders both ids and does not recurse."""
    s = _store(tmp_path)
    _write_req(s, "REQ0001", parent="REQ0002")
    _write_req(s, "REQ0002", parent="REQ0001")

    pub = Publisher(s)
    html = pub.build_html()

    # Truncation, not deletion: both ids survive in the document.
    assert "REQ0001" in html
    assert "REQ0002" in html


def test_self_parent_renders_and_terminates(tmp_path):
    """REQ0001.parent = REQ0001 renders and does not recurse."""
    s = _store(tmp_path)
    _write_req(s, "REQ0001", parent="REQ0001")

    pub = Publisher(s)
    html = pub.build_html()

    assert "REQ0001" in html


def test_subsystem_scope_over_cycle_terminates(tmp_path):
    """Subsystem scope over a parent cycle returns a finite scope set."""
    s = _store(tmp_path)
    _write_req(s, "REQ0001", parent="REQ0002")
    _write_req(s, "REQ0002", parent="REQ0001")

    pub = Publisher(s, subsystems=["REQ0001"])

    ids = {r["id"] for r in pub.reqs}
    assert ids == {"REQ0001", "REQ0002"}


# ── legitimate trees must not be flattened ────────────────────────────────────


def test_siblings_both_render(tmp_path):
    """Two children under one parent both render (path set, not global set)."""
    s = _store(tmp_path)
    _write_req(s, "REQ0001")
    _write_req(s, "REQ0002", parent="REQ0001")
    _write_req(s, "REQ0003", parent="REQ0001")

    pub = Publisher(s)
    html = pub.build_html()

    assert 'id="req-REQ0002"' in html
    assert 'id="req-REQ0003"' in html


def test_three_level_tree_still_nests(tmp_path):
    """A three-level tree keeps distinct per-depth indents."""
    s = _store(tmp_path)
    _write_req(s, "REQ0001")
    _write_req(s, "REQ0002", parent="REQ0001")
    _write_req(s, "REQ0003", parent="REQ0002")

    pub = Publisher(s)
    html = pub.build_html()

    assert "margin-left:20px" in html
    assert "margin-left:40px" in html
