"""ReqIF conformance tests — structural validity of export and import.

These tests verify the fixes for the four structural defects listed in
the ReqIF conformance task:

1. Emit a DATATYPES section and reference datatypes properly.
2. Emit ATTRIBUTE-DEFINITION-XHTML for the XHTML attribute.
3. Declare SPEC-RELATION-TYPEs and give SPEC-RELATION a TYPE.
4. Give the SPECIFICATION a real SPECIFICATION-TYPE.
5. Read the relation type back on import.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from xml.etree.ElementTree import fromstring

from app.services.reqif_export import export_reqif
from app.services.reqif_import import _find_all, _first_child, _local, parse_reqif


def _make_store(project_name: str = "Src"):
    """Create a temporary YamlStore pre-populated with one requirement."""
    from app.services.yaml_store import YamlStore

    root = Path(tempfile.mkdtemp())
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": project_name})
    return store


# ---------------------------------------------------------------------- test 1

def test_datatypes_section_and_order():
    """The export contains exactly one DATATYPES element which precedes
    SPEC-TYPES in document order."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    xml_text = export_reqif(store)
    root = fromstring(xml_text)

    datatypes_els = _find_all(root, "DATATYPES")
    assert len(datatypes_els) == 1, "There must be exactly one DATATYPES element"

    # Walk CORE-CONTENT children to check order
    core = _first_child(root, "CORE-CONTENT")
    assert core is not None, "Missing CORE-CONTENT"

    # Find the positions of DATATYPES and SPEC-TYPES among direct children
    datatypes_idx = None
    spectypes_idx = None
    for i, child in enumerate(core):
        tag = _local(child.tag)
        if tag == "DATATYPES":
            datatypes_idx = i
        elif tag == "SPEC-TYPES":
            spectypes_idx = i

    assert datatypes_idx is not None, "DATATYPES not found in CORE-CONTENT"
    assert spectypes_idx is not None, "SPEC-TYPES not found in CORE-CONTENT"
    assert datatypes_idx < spectypes_idx, "DATATYPES must precede SPEC-TYPES"


# ---------------------------------------------------------------------- test 2

def test_description_is_xhtml_definition():
    """ATTR-DESCRIPTION is defined by an ATTRIBUTE-DEFINITION-XHTML element."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First", "description": "<p>desc</p>"})
    xml_text = export_reqif(store)
    root = fromstring(xml_text)

    # Find the attribute definition with IDENTIFIER="ATTR-DESCRIPTION"
    desc_def = None
    for el in root.iter():
        if el.get("IDENTIFIER") == "ATTR-DESCRIPTION":
            desc_def = el
            break

    assert desc_def is not None, "ATTR-DESCRIPTION definition not found"
    assert _local(desc_def.tag) == "ATTRIBUTE-DEFINITION-XHTML", (
        f"Expected ATTRIBUTE-DEFINITION-XHTML, got {_local(desc_def.tag)}"
    )


# ---------------------------------------------------------------------- test 3

def test_attribute_def_type_refs():
    """Every ATTRIBUTE-DEFINITION-* TYPE holds a datatype ref (not bare text)."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    xml_text = export_reqif(store)
    root = fromstring(xml_text)

    # Collect all declared datatype identifiers
    datatype_ids: set[str] = set()
    for dt in root.iter():
        if _local(dt.tag).startswith("DATATYPE-DEFINITION-"):
            ident = dt.get("IDENTIFIER")
            if ident:
                datatype_ids.add(ident)

    assert datatype_ids, "No datatype definitions found"

    # Check every ATTRIBUTE-DEFINITION-* element (exclude -REF references)
    for el in root.iter():
        tag = _local(el.tag)
        if not tag.startswith("ATTRIBUTE-DEFINITION-") or tag.endswith("-REF"):
            continue
        type_el = _first_child(el, "TYPE")
        assert type_el is not None, f"{el.get('IDENTIFIER')}: missing TYPE child"
        # Must not hold bare text
        assert type_el.text is None or type_el.text.strip() == "", (
            f"{el.get('IDENTIFIER')}: TYPE element has bare text: {type_el.text!r}"
        )
        # Must have a DATATYPE-DEFINITION-...-REF child
        ref_child = None
        ref_text = None
        for child in type_el:
            if _local(child.tag).endswith("-REF") and "DATATYPE-DEFINITION-" in _local(child.tag):
                ref_child = child
                ref_text = (child.text or "").strip()
                break
        assert ref_child is not None, (
            f"{el.get('IDENTIFIER')}: TYPE has no DATATYPE-DEFINITION-*-REF child"
        )
        assert ref_text in datatype_ids, (
            f"{el.get('IDENTIFIER')}: ref {ref_text!r} does not match any declared datatype {datatype_ids}"
        )


# ---------------------------------------------------------------------- test 4

def test_spec_relation_has_type():
    """Every SPEC-RELATION has a TYPE whose SPEC-RELATION-TYPE-REF resolves."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    store.create_requirement({
        "id": "REQ-2", "name": "Second",
        "relations": [{"type": "refines", "target": "REQ-1"}],
    })
    store.write_traces({
        "links": [{"source": "REQ-2", "target": "REQ-1", "type": "refines"}],
    })
    xml_text = export_reqif(store)
    root = fromstring(xml_text)

    # Collect declared SPEC-RELATION-TYPE identifiers
    rel_type_ids: set[str] = set()
    for rt in _find_all(root, "SPEC-RELATION-TYPE"):
        ident = rt.get("IDENTIFIER")
        if ident:
            rel_type_ids.add(ident)

    assert rel_type_ids, "No SPEC-RELATION-TYPEs declared"

    rels = _find_all(root, "SPEC-RELATION")
    assert rels, "No SPEC-RELATION elements found"

    for rel in rels:
        type_el = _first_child(rel, "TYPE")
        assert type_el is not None, (
            f"SPEC-RELATION {rel.get('IDENTIFIER')}: missing TYPE child"
        )
        ref_found = None
        for child in type_el:
            if "SPEC-RELATION-TYPE-REF" in _local(child.tag):
                ref_found = (child.text or "").strip()
                break
        assert ref_found is not None, (
            f"SPEC-RELATION {rel.get('IDENTIFIER')}: TYPE has no SPEC-RELATION-TYPE-REF"
        )
        assert ref_found in rel_type_ids, (
            f"SPEC-RELATION {rel.get('IDENTIFIER')}: ref {ref_found!r} "
            f"not in declared types {rel_type_ids}"
        )


# ---------------------------------------------------------------------- test 5

def test_relation_types_roundtrip():
    """A project with refines, satisfies and conflicts round-trips all types."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    store.create_requirement({
        "id": "REQ-2", "name": "Second",
        "relations": [
            {"type": "refines", "target": "REQ-1"},
            {"type": "satisfies", "target": "REQ-1"},
        ],
    })
    store.create_requirement({
        "id": "REQ-3", "name": "Third",
        "relations": [
            {"type": "conflicts", "target": "REQ-1"},
        ],
    })
    xml_text = export_reqif(store)
    parsed = parse_reqif(xml_text)

    rel_types = {t["type"] for t in parsed["traces"]}
    assert "refines" in rel_types, f"Missing 'refines' in {rel_types}"
    assert "satisfies" in rel_types, f"Missing 'satisfies' in {rel_types}"
    assert "conflicts" in rel_types, f"Missing 'conflicts' in {rel_types}"


# ---------------------------------------------------------------------- test 6

def test_trace_no_type_defaults_to_traces():
    """A trace with no type round-trips as 'traces' rather than being dropped."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    store.create_requirement({"id": "REQ-2", "name": "Second"})
    # Write a trace with no type field
    store.write_traces({
        "links": [{"source": "REQ-2", "target": "REQ-1"}],
    })
    xml_text = export_reqif(store)
    parsed = parse_reqif(xml_text)

    traces = parsed["traces"]
    # Should find the trace with type="traces"
    found = [t for t in traces if t["source"] == "REQ-2" and t["target"] == "REQ-1"]
    assert len(found) == 1, f"Expected exactly one trace, got {found}"
    assert found[0]["type"] == "traces", f"Expected 'traces', got {found[0]['type']!r}"


# ---------------------------------------------------------------------- test 7

def test_specification_type_is_specification_type_ref():
    """The SPECIFICATION's TYPE is a SPECIFICATION-TYPE-REF and resolves."""
    store = _make_store()
    store.create_requirement({"id": "REQ-1", "name": "First"})
    xml_text = export_reqif(store)
    root = fromstring(xml_text)

    # Collect SPECIFICATION-TYPE identifiers
    spec_type_ids: set[str] = set()
    for st in _find_all(root, "SPECIFICATION-TYPE"):
        ident = st.get("IDENTIFIER")
        if ident:
            spec_type_ids.add(ident)

    assert spec_type_ids, "No SPECIFICATION-TYPE declared"

    specs = _find_all(root, "SPECIFICATION")
    assert specs, "No SPECIFICATION element found"

    for spec in specs:
        type_el = _first_child(spec, "TYPE")
        assert type_el is not None, "SPECIFICATION: missing TYPE child"
        ref_child = None
        for child in type_el:
            if "SPECIFICATION-TYPE-REF" in _local(child.tag):
                ref_child = child
                break
        assert ref_child is not None, "SPECIFICATION TYPE has no SPECIFICATION-TYPE-REF"
        ref_text = (ref_child.text or "").strip()
        assert ref_text in spec_type_ids, (
            f"SPECIFICATION-TYPE-REF {ref_text!r} not in declared types {spec_type_ids}"
        )


# ---------------------------------------------------------------------- test 8

def test_descriptions_roundtrip():
    """Descriptions still round-trip through the XHTML value path."""
    store = _make_store()
    store.create_requirement({
        "id": "REQ-1",
        "name": "First",
        "description": "<div>Shall authenticate all users.</div>",
    })
    xml_text = export_reqif(store)
    parsed = parse_reqif(xml_text)

    by_id = {r["id"]: r for r in parsed["requirements"]}
    assert "REQ-1" in by_id
    desc = by_id["REQ-1"].get("description", "")
    assert "authenticate" in desc, f"Description lost XHTML content: {desc!r}"


# ---------------------------------------------------------------------- test 9

def test_full_roundtrip_preserves_requirement_data():
    """Export→import preserves requirement count, ids, names, statuses and
    priorities."""
    store = _make_store()
    reqs_data = [
        {"id": "REQ-1", "name": "Auth", "status": "approved", "priority": "high", "type": "functional"},
        {"id": "REQ-2", "name": "Logging", "status": "proposed", "priority": "medium", "type": "non-functional"},
        {"id": "REQ-3", "name": "Caching", "status": "review", "priority": "low", "type": "functional"},
    ]
    for rd in reqs_data:
        store.create_requirement(rd)

    store.write_traces({
        "links": [
            {"source": "REQ-2", "target": "REQ-1", "type": "refines"},
            {"source": "REQ-3", "target": "REQ-1", "type": "satisfies"},
        ],
    })

    xml_text = export_reqif(store)
    parsed = parse_reqif(xml_text)

    reqs = parsed["requirements"]
    assert len(reqs) == 3, f"Expected 3 requirements, got {len(reqs)}"

    by_id = {r["id"]: r for r in reqs}
    assert set(by_id) == {"REQ-1", "REQ-2", "REQ-3"}

    assert by_id["REQ-1"]["name"] == "Auth"
    assert by_id["REQ-1"]["status"] == "approved"
    assert by_id["REQ-1"]["priority"] == "high"

    assert by_id["REQ-2"]["name"] == "Logging"
    assert by_id["REQ-2"]["status"] == "proposed"
    assert by_id["REQ-2"]["priority"] == "medium"

    assert by_id["REQ-3"]["name"] == "Caching"
    assert by_id["REQ-3"]["status"] == "review"
    assert by_id["REQ-3"]["priority"] == "low"

    # Verify traces round-trip
    traces = parsed["traces"]
    trace_pairs = {(t["source"], t["target"], t["type"]) for t in traces}
    assert ("REQ-2", "REQ-1", "refines") in trace_pairs
    assert ("REQ-3", "REQ-1", "satisfies") in trace_pairs


def test_relations_to_non_requirements_are_not_dangled():
    """Only requirements become SPEC-OBJECTs. A relation to a verification case
    has no object to point at, and emitting it anyway yields a SPEC-OBJECT-REF
    to an identifier that appears nowhere in the file — invalid ReqIF."""
    store = _make_store()
    store.create_requirement({
        "id": "REQ-1", "name": "One",
        "relations": [
            {"type": "refines", "target": "REQ-2"},
            {"type": "verified_by", "target": "VC-1"},
        ],
    })
    store.create_requirement({"id": "REQ-2", "name": "Two"})

    root = fromstring(export_reqif(store).encode())
    declared = {e.get("IDENTIFIER") for e in root.iter() if e.get("IDENTIFIER")}

    unresolved = [
        (e.tag.split("}")[-1], e.text.strip())
        for e in root.iter()
        if e.tag.split("}")[-1].endswith("-REF")
        and (e.text or "").strip()
        and e.text.strip() not in declared
    ]
    assert unresolved == [], f"dangling references: {unresolved}"

    # The representable relation still survives.
    targets = [
        e.text.strip() for e in root.iter()
        if e.tag.split("}")[-1] == "SPEC-OBJECT-REF"
    ]
    assert "REQ-2" in targets
