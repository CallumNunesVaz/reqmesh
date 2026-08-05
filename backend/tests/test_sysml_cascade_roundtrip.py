"""SysML v2 round-trip for cascaded requirements (definition/usage).

A cascade is reqmesh's master→slave copy.  SysML v2 represents this as a
``requirement`` usage typed by a ``requirement def``, so the link survives being
exported and re-imported — which it did not before this was implemented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.importer import import_into_store
from app.services.sysml_export import export_sysml_v2
from app.services.sysml_import import parse_sysml
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path) -> YamlStore:
    """A fresh project root ready for writes."""
    root = tmp_path / "project"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "TestProject"})
    return store


def _req(store: YamlStore, **kw) -> dict:
    """Write and return a requirement dict."""
    defaults: dict = {
        "id": "REQ-001",
        "name": "Test Requirement",
        "status": "proposed",
        "priority": "medium",
        "verification_method": "test",
    }
    data = {**defaults, **kw}
    store.create_requirement(data)
    return store.get_requirement(data["id"])


def _fresh_store(tmp_path: Path) -> YamlStore:
    """A second fresh project for round-trip import."""
    root = tmp_path / "target"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "TargetProject"})
    return store


# ── Export ────────────────────────────────────────────────────────────────────


def test_cascaded_child_exports_as_usage_typed_by_master(tmp_path):
    """A requirement with cascade_from is emitted as a usage, and its master
    stays a ``requirement def`` — asserting only the child would pass even if
    every requirement became a usage."""
    store = _store(tmp_path)
    _req(store, id="MASTER", name="Master")
    _req(store, id="CHILD", name="Child", cascade_from="MASTER")

    out = export_sysml_v2(store)

    assert "requirement CHILD : MASTER {" in out, (
        "cascaded requirement should emit as usage typed by master"
    )
    assert "requirement def MASTER {" in out, (
        "non-cascaded master should stay a `requirement def`"
    )


def test_cascaded_child_with_sanitised_ids(tmp_path):
    """Ids containing dashes and dots are sanitised to underscores in the
    SysML text, including the master reference."""
    store = _store(tmp_path)
    _req(store, id="REQ-SOURCE", name="Source")
    _req(store, id="REQ-COPY.X", name="Copy", cascade_from="REQ-SOURCE")

    out = export_sysml_v2(store)

    assert "requirement REQ_COPY_X : REQ_SOURCE {" in out


def test_derive_relation_still_emitted_alongside_cascade(tmp_path):
    """The ``derive`` line is separate stored data — the cascade typing must
    not suppress it."""
    store = _store(tmp_path)
    _req(store, id="ANCESTOR", name="Ancestor")
    _req(store, id="DERIVED", name="Derived",
         cascade_from="ANCESTOR",
         relations=[{"type": "derives", "target": "ANCESTOR"}])

    out = export_sysml_v2(store)

    assert "requirement DERIVED : ANCESTOR {" in out
    assert "derive requirement ANCESTOR;" in out


# ── Round-trip ────────────────────────────────────────────────────────────────


def test_cascade_round_trip_preserves_link(tmp_path):
    """Export a cascaded pair, re-import, and verify cascade_from is intact.
    This is the defect — without this the task proves nothing."""
    store = _store(tmp_path)
    _req(store, id="MASTER", name="Master")
    _req(store, id="CHILD", name="Child", cascade_from="MASTER")

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)

    target = _fresh_store(tmp_path)
    import_into_store(target, parsed, mode="replace")

    child = target.get_requirement("CHILD")
    assert child is not None
    assert child["cascade_from"] == "MASTER", (
        f"round-trip lost cascade_from: {child.get('cascade_from')!r}"
    )


def test_non_cascaded_round_trip_keeps_none(tmp_path):
    """A requirement without cascade_from must round-trip with cascade_from
    still None — the importer must not invent a cascade."""
    store = _store(tmp_path)
    _req(store, id="STANDALONE", name="Standalone")

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)

    target = _fresh_store(tmp_path)
    import_into_store(target, parsed, mode="replace")

    standalone = target.get_requirement("STANDALONE")
    assert standalone is not None
    assert standalone.get("cascade_from") is None, (
        f"non-cascaded requirement acquired a cascade_from: "
        f"{standalone.get('cascade_from')!r}"
    )


def test_transitive_chain_round_trip(tmp_path):
    """A → B → C: both cascade links survive."""
    store = _store(tmp_path)
    _req(store, id="A", name="A")
    _req(store, id="B", name="B", cascade_from="A")
    _req(store, id="C", name="C", cascade_from="B")

    text = export_sysml_v2(store)
    parsed = parse_sysml(text)

    target = _fresh_store(tmp_path)
    import_into_store(target, parsed, mode="replace")

    b = target.get_requirement("B")
    c = target.get_requirement("C")
    assert b is not None
    assert c is not None
    assert b["cascade_from"] == "A"
    assert c["cascade_from"] == "B"


# ── Dangling master ───────────────────────────────────────────────────────────


def test_child_without_master_in_scope_falls_back_to_def(tmp_path):
    """When cascade_from names a requirement not in the export, the child
    must be emitted as a ``requirement def`` so the file still parses.  A
    dangling type reference is worse than a lost link."""
    store = _store(tmp_path)
    _req(store, id="ORPHAN", name="Orphan", cascade_from="MISSING-MASTER")

    out = export_sysml_v2(store)

    assert "requirement def ORPHAN {" in out, (
        "child with missing master must fall back to `requirement def`"
    )
    # The output must still be parseable.
    parsed = parse_sysml(out)
    assert parsed.get("requirements"), "output with dangling master did not parse"


def test_dangling_type_reference_imports_without_cascade(tmp_path):
    """A usage whose type_id does not resolve to any requirement in the same
    file imports with cascade_from = None, not a dangling id string."""
    text = """// Test
    package Test {
      requirement def REQ_A {
        doc /* A */
      }
      requirement REQ_B : NONEXISTENT {
        doc /* B */
      }
    }
    """
    parsed = parse_sysml(text)
    assert len(parsed["requirements"]) == 2

    target = _fresh_store(tmp_path)
    import_into_store(target, parsed, mode="replace")

    a = target.get_requirement("REQ_A")
    b = target.get_requirement("REQ_B")
    assert a is not None
    assert b is not None
    assert b.get("cascade_from") is None, (
        f"dangling type reference should import with cascade_from=None, "
        f"got {b.get('cascade_from')!r}"
    )
