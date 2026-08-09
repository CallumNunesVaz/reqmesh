"""SysML v2 id fidelity: hyphenated and dotted ids survive export → import.

Before this was implemented, the exporter rewrote REQ-001 to REQ_001 and the
importer never reversed it, so a merge-mode re-import created duplicates of
every hyphenated entity.  These tests assert that the round-trip preserves the
original ids and that every intra-file reference resolves to the restored id.
"""

from __future__ import annotations

from pathlib import Path

from app.services.importer import import_into_store
from app.services.sysml_export import export_sysml_v2, _safe_name, _decl
from app.services.sysml_import import parse_sysml
from app.services.yaml_store import YamlStore


# ── helpers ───────────────────────────────────────────────────────────────────

def _store(tmp_path: Path) -> YamlStore:
    root = tmp_path / "project"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "Fidelity"})
    return store


def _fresh(tmp_path: Path) -> YamlStore:
    root = tmp_path / "target"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "Target"})
    return store


# ── _safe_name / _decl helpers ─────────────────────────────────────────────────

def test_safe_name_replaces_dashes_and_dots():
    assert _safe_name("REQ-001") == "REQ_001"
    assert _safe_name("SYS.1.2") == "SYS_1_2"
    assert _safe_name("PLAIN") == "PLAIN"
    assert _safe_name("A-B.C") == "A_B_C"


def test_decl_adds_short_name_when_id_is_mangled():
    assert _decl("requirement def", "REQ-001") == "requirement def <'REQ-001'> REQ_001"
    assert _decl("part def", "PWR.01") == "part def <'PWR.01'> PWR_01"


def test_decl_omits_short_name_for_plain_ids():
    assert _decl("requirement def", "WING") == "requirement def WING"
    assert _decl("part def", "PLAIN") == "part def PLAIN"


def test_decl_escapes_single_quote_in_id():
    assert _decl("requirement def", "IT'S-OK") == "requirement def <'IT\\'S-OK'> IT'S_OK"


def test_decl_accepts_suffix():
    assert _decl("requirement", "REQ-001", " : REQ_SOURCE") == (
        "requirement <'REQ-001'> REQ_001 : REQ_SOURCE"
    )
    assert _decl("requirement def", "PLAIN", "") == "requirement def PLAIN"


# ── round-trip of hyphenated ids ──────────────────────────────────────────────

def test_hyphenated_id_round_trips(tmp_path):
    """REQ-001 exports with <'REQ-001'> and re-imports with id 'REQ-001'."""
    store = _store(tmp_path)
    store.create_requirement({"id": "REQ-001", "name": "Hyphenated"})

    out = export_sysml_v2(store)
    assert "<'REQ-001'>" in out, f"short name missing from export:\n{out}"

    parsed = parse_sysml(out)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    assert reqs[0]["id"] == "REQ-001"


def test_dotted_id_round_trips(tmp_path):
    """SYS.1.2 exports with <'SYS.1.2'> and re-imports with id 'SYS.1.2'."""
    store = _store(tmp_path)
    store.create_requirement({"id": "SYS.1.2", "name": "Dotted"})

    out = export_sysml_v2(store)
    assert "<'SYS.1.2'>" in out

    parsed = parse_sysml(out)
    assert parsed["requirements"][0]["id"] == "SYS.1.2"


# ── idempotent merge ──────────────────────────────────────────────────────────

def test_idempotent_merge_does_not_create_duplicates(tmp_path):
    """Importing the same export twice into a store that already holds the
    entities must leave the counts identical after the second import, and no
    id may contain a _ that didn't contain _ originally."""
    src = _store(tmp_path)
    src.create_requirement({"id": "REQ-001", "name": "One"})
    src.create_requirement({"id": "REQ-002", "name": "Two"})
    src.create_component({"id": "COMP-A.1", "name": "Comp"})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    reqs1 = target.list_requirements()
    comps1 = target.list_components()
    assert len(reqs1) == 2
    assert len(comps1) == 1

    # Second import with merge should not change counts.
    parsed2 = parse_sysml(text)
    import_into_store(target, parsed2, mode="merge")

    reqs2 = target.list_requirements()
    comps2 = target.list_components()
    assert len(reqs2) == len(reqs1), "merge created duplicate requirements"
    assert len(comps2) == len(comps1), "merge created duplicate components"

    # No id should contain an _ that it didn't have originally.
    for r in reqs2:
        assert "_" not in r["id"], f"mangled id survived merge: {r['id']}"
    for c in comps2:
        assert "_" not in c["id"], f"mangled id survived merge: {c['id']}"


# ── relation target restoration ───────────────────────────────────────────────

def test_relation_target_restores_hyphenated_id(tmp_path):
    """REQ-001 refines REQ-002 → the re-imported relation has target REQ-002,
    not REQ_002."""
    src = _store(tmp_path)
    src.create_requirement({
        "id": "REQ-001", "name": "One",
        "relations": [{"type": "refines", "target": "REQ-002"}],
    })
    src.create_requirement({"id": "REQ-002", "name": "Two"})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    req1 = target.get_requirement("REQ-001")
    assert req1 is not None
    rels = req1.get("relations", [])
    assert len(rels) == 1
    assert rels[0]["target"] == "REQ-002", (
        f"target not restored: {rels[0]['target']!r}"
    )


# ── parent, cascade_from, subject ─────────────────────────────────────────────

def test_parent_nesting_restores_hyphenated_ids(tmp_path):
    """A child nested under a hyphenated parent keeps the real parent id."""
    src = _store(tmp_path)
    src.create_requirement({"id": "REQ-PARENT", "name": "Parent"})
    src.create_requirement({"id": "REQ-CHILD", "name": "Child", "parent": "REQ-PARENT"})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    child = target.get_requirement("REQ-CHILD")
    assert child is not None
    assert child["parent"] == "REQ-PARENT", (
        f"parent not restored: {child['parent']!r}"
    )


def test_cascade_from_restores_hyphenated_ids(tmp_path):
    """A cascaded requirement restores cascade_from to the original id."""
    src = _store(tmp_path)
    src.create_requirement({"id": "M-1", "name": "Master"})
    src.create_requirement({"id": "C-1", "name": "Copy", "cascade_from": "M-1"})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    c = target.get_requirement("C-1")
    assert c is not None
    assert c["cascade_from"] == "M-1", (
        f"cascade_from not restored: {c['cascade_from']!r}"
    )


def test_subject_restores_hyphenated_ids(tmp_path):
    """A requirement with an explicit hyphenated subject that names an entity
    in the file restores it.  (The exporter mangles the subject on the wire;
    the importer resolves it through the alias map.)"""
    src = _store(tmp_path)
    src.create_component({"id": "SUBJ-A", "name": "SubjectComp"})
    src.create_requirement({"id": "REQ-001", "name": "One", "subject": "SUBJ-A"})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    r = target.get_requirement("REQ-001")
    assert r is not None
    assert r["subject"] == "SUBJ-A", (
        f"subject not restored: {r['subject']!r}"
    )


# ── component satisfies ───────────────────────────────────────────────────────

def test_component_satisfies_restores_both_ids(tmp_path):
    """A component PWR-1 with satisfies: [REQ-001] restores both hyphenated ids."""
    src = _store(tmp_path)
    src.create_requirement({"id": "REQ-001", "name": "Req"})
    src.create_component({"id": "PWR-1", "name": "Power", "satisfies": ["REQ-001"]})

    text = export_sysml_v2(src)
    parsed = parse_sysml(text)

    target = _fresh(tmp_path)
    import_into_store(target, parsed, mode="replace")

    c = target.get_component("PWR-1")
    assert c is not None
    assert c["id"] == "PWR-1", f"component id not restored: {c['id']!r}"
    assert c["satisfies"] == ["REQ-001"], (
        f"satisfies not restored: {c['satisfies']!r}"
    )


# ── backward compatibility ────────────────────────────────────────────────────

def test_backward_compatible_no_short_names(tmp_path):
    """A file in the old format (no short names) still imports correctly, with
    declared names as ids."""
    old_format = """// Test
package Legacy {
  requirement def REQ_001 {
    doc /* One */
  }
  requirement REQ_002 : REQ_001 {
    doc /* Two */
    refine requirement REQ_001;
  }
  part def COMP_A {
    doc /* Comp */
    satisfy requirement REQ_001;
  }
}
"""
    parsed = parse_sysml(old_format)
    reqs = parsed["requirements"]
    comps = parsed["components"]

    assert len(reqs) == 2
    assert {r["id"] for r in reqs} == {"REQ_001", "REQ_002"}
    child = [r for r in reqs if r["id"] == "REQ_002"][0]
    assert child["cascade_from"] == "REQ_001"

    assert len(comps) == 1
    assert comps[0]["id"] == "COMP_A"
    assert comps[0]["satisfies"] == ["REQ_001"]


# ── plain ids emit no short name ──────────────────────────────────────────────

def test_plain_id_emits_no_short_name(tmp_path):
    """An id that needs no mangling emits no short name (no <' in the block
    opener)."""
    store = _store(tmp_path)
    store.create_requirement({"id": "PLAINID", "name": "Plain"})

    out = export_sysml_v2(store)
    assert "<'" not in out, (
        f"plain id should not produce a short name:\n{out}"
    )
    assert "requirement def PLAINID {" in out


# ── external reference pass-through ───────────────────────────────────────────

def test_relation_to_external_id_is_preserved(tmp_path):
    """A relation target naming an entity not in the file is passed through
    untouched — it must not be mangled or dropped."""
    sysml = """// Test
package Ext {
  requirement def REQ_001 {
    doc /* One */
    refine requirement EXTERNAL_REF;
  }
}
"""
    parsed = parse_sysml(sysml)
    reqs = parsed["requirements"]
    assert len(reqs) == 1
    rels = reqs[0].get("relations", [])
    assert len(rels) == 1
    assert rels[0]["target"] == "EXTERNAL_REF", (
        f"external reference was mangled: {rels[0]['target']!r}"
    )
