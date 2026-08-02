"""The SysML v2 subject clause is derived from the allocating component(s)
when no explicit subject is stored on the requirement, and only when a
single component allocates — zero or many produce no subject clause."""

from pathlib import Path

import pytest

from app.services.sysml_export import export_sysml_v2
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path) -> YamlStore:
    """A fresh project root with a minimal _meta.yaml, ready for writes."""
    root = tmp_path / "project"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "TestProject"})
    return store


def _req(store: YamlStore, **kw) -> dict:
    """Write and return a requirement dict."""
    defaults = {
        "id": "REQ-001",
        "name": "Test Requirement",
        "status": "proposed",
        "priority": "medium",
        "verification_method": "test",
    }
    data = {**defaults, **kw}
    store.write_item("requirements", data["id"], data)
    return data


def _comp(store: YamlStore, **kw) -> dict:
    """Write and return a component dict."""
    defaults = {"id": "COMP-001", "name": "Test Component"}
    data = {**defaults, **kw}
    store.write_item("components", data["id"], data)
    return data


def test_single_component_emits_subject(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X")
    _comp(store, id="COMP-A", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject COMP_A;" in out


def test_two_components_no_subject(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X")
    _comp(store, id="COMP-A", satisfies=["REQ-X"])
    _comp(store, id="COMP-B", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject" not in out


def test_zero_components_no_subject(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X")
    _comp(store, id="COMP-A")  # satisfies nothing
    out = export_sysml_v2(store)
    assert "subject" not in out


def test_explicit_subject_wins_over_single_allocating_component(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X", subject="EXPLICIT-SUBJECT")
    _comp(store, id="COMP-A", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject EXPLICIT_SUBJECT;" in out
    assert "subject COMP_A;" not in out


def test_explicit_subject_wins_when_two_components_allocate(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X", subject="EXPLICIT-SUBJECT")
    _comp(store, id="COMP-A", satisfies=["REQ-X"])
    _comp(store, id="COMP-B", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject EXPLICIT_SUBJECT;" in out


def test_component_name_with_comma_yields_id_not_name(tmp_path):
    """A component named 'Wing, Left' must still export its id, proving the
    derivation didn't go through a display string."""
    store = _store(tmp_path)
    _req(store, id="REQ-X")
    _comp(store, id="COMP-WING-LEFT", name="Wing, Left", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject COMP_WING_LEFT;" in out


def test_ids_with_dashes_and_dots_are_sanitised(tmp_path):
    store = _store(tmp_path)
    _req(store, id="REQ-X")
    _comp(store, id="COMP-A.1-b", satisfies=["REQ-X"])
    out = export_sysml_v2(store)
    assert "subject COMP_A_1_b;" in out
