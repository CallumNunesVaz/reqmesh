"""ReqIF 1.2 XML export for interoperability with DOORS, Polarion, Jama, etc.

Generates a minimal but valid ReqIF file containing the project's requirements
and their attributes.  The spec-level ReqIF types are deliberately simple so
that every major tool can consume the output without customisation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

REQIF_NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
XHTML_NS = "http://www.w3.org/1999/xhtml"


def _ns_tag(tag: str) -> str:
    return f"{{{REQIF_NS}}}{tag}"


def _xhtml_tag(tag: str) -> str:
    return f"{{{XHTML_NS}}}{tag}"


def export_reqif(store) -> str:
    """Return a ReqIF 1.2 XML string for the given project."""
    meta = store.read_meta()
    reqs = store.list_requirements()
    project_name = meta.get("name", store.root.name)
    now = datetime.now(timezone.utc).isoformat()

    root = Element(_ns_tag("REQ-IF"), {
        "xmlns": REQIF_NS,
        "xmlns:xhtml": XHTML_NS,
    })

    # -- Core content ----------------------------------------------------------
    core = SubElement(root, _ns_tag("CORE-CONTENT"))
    req_type_id = "REQ-TYPE-001"
    spec_type_id = "SPEC-TYPE-001"

    # Spec-types
    spec_types = SubElement(core, _ns_tag("SPEC-TYPES"))
    _spec_object_type(spec_types, req_type_id, "Requirement")
    _spec_object_type(spec_types, spec_type_id, "Specification")

    # Spec-objects (one per requirement)
    spec_objs = SubElement(core, _ns_tag("SPEC-OBJECTS"))
    for r in reqs:
        _spec_object(spec_objs, r, req_type_id)

    # Specification
    specs = SubElement(core, _ns_tag("SPECIFICATIONS"))
    spec = SubElement(specs, _ns_tag("SPECIFICATION"), {
        "IDENTIFIER": f"SPEC-{uuid.uuid4().hex[:8].upper()}",
        "LAST-CHANGE": now,
        "LONG-NAME": project_name,
    })
    spec_type_ref = SubElement(spec, _ns_tag("TYPE"))
    SubElement(spec_type_ref, _ns_tag("SPEC-OBJECT-TYPE-REF")).text = spec_type_id
    children = SubElement(spec, _ns_tag("CHILDREN"))
    for r in reqs:
        child = SubElement(children, _ns_tag("SPEC-HIERARCHY"))
        obj_ref = SubElement(child, _ns_tag("OBJECT"))
        SubElement(obj_ref, _ns_tag("SPEC-OBJECT-REF")).text = r["id"]

    # Spec-relations (trace links plus per-requirement relations)
    traces = store.read_traces().get("links", [])
    rels = SubElement(core, _ns_tag("SPEC-RELATIONS"))
    index = 0
    for t in traces:
        _spec_relation(rels, t, index)
        index += 1
    for r in reqs:
        for rel in r.get("relations") or []:
            _spec_relation(rels, {"source": r["id"], "target": rel["target"], "type": rel["type"]}, index)
            index += 1

    # -- Pretty-print
    dom = minidom.parseString(tostring(root, "utf-8"))
    return dom.toprettyxml(indent="  ")


def _spec_object_type(parent: Element, type_id: str, name: str) -> None:
    sot = SubElement(parent, _ns_tag("SPEC-OBJECT-TYPE"), {
        "IDENTIFIER": type_id,
        "LONG-NAME": name,
    })
    _add_attribute_def(sot, "ID", "STRING", True)
    _add_attribute_def(sot, "Name", "STRING", True)
    _add_attribute_def(sot, "Description", "XHTML", False)
    _add_attribute_def(sot, "Status", "STRING", False)
    _add_attribute_def(sot, "Priority", "STRING", False)
    _add_attribute_def(sot, "Type", "STRING", False)
    _add_attribute_def(sot, "Rationale", "STRING", False)
    _add_attribute_def(sot, "Source", "STRING", False)


def _add_attribute_def(parent: Element, long_name: str, data_type: str, is_id: bool) -> None:
    attr_id = f"ATTR-{long_name.upper().replace(' ','-')}"
    attr_def = SubElement(parent, _ns_tag("ATTRIBUTE-DEFINITION-STRING"), {
        "IDENTIFIER": attr_id,
        "LONG-NAME": long_name,
    })
    SubElement(attr_def, _ns_tag("TYPE")).text = data_type
    if is_id:
        SubElement(attr_def, _ns_tag("IS-IDENTIFIER")).text = "true"


def _spec_object(parent: Element, req: dict, req_type_id: str) -> None:
    obj = SubElement(parent, _ns_tag("SPEC-OBJECT"), {
        "IDENTIFIER": req["id"],
        "LAST-CHANGE": req.get("modified", ""),
        "LONG-NAME": req.get("name", req["id"]),
    })
    type_ref = SubElement(obj, _ns_tag("TYPE"))
    SubElement(type_ref, _ns_tag("SPEC-OBJECT-TYPE-REF")).text = req_type_id

    values = SubElement(obj, _ns_tag("VALUES"))
    _attr_value(values, "ATTR-ID", req["id"])
    _attr_value(values, "ATTR-NAME", req.get("name", ""))
    _attr_value(values, "ATTR-STATUS", req.get("status", "proposed"))
    _attr_value(values, "ATTR-PRIORITY", req.get("priority", "medium"))
    _attr_value(values, "ATTR-TYPE", req.get("type", "functional"))
    _attr_value(values, "ATTR-RATIONALE", req.get("rationale", ""))
    _attr_value(values, "ATTR-SOURCE", req.get("source", ""))

    desc = req.get("description", "")
    if desc:
        desc_val = SubElement(values, _ns_tag("ATTRIBUTE-VALUE-XHTML"))
        defn = SubElement(desc_val, _ns_tag("DEFINITION"))
        SubElement(defn, _ns_tag("ATTRIBUTE-DEFINITION-XHTML-REF")).text = "ATTR-DESCRIPTION"
        the_val = SubElement(desc_val, _ns_tag("THE-VALUE"))
        div = SubElement(the_val, _xhtml_tag("div"))
        # Insert raw description as XHTML content (will be escaped properly)
        div.text = desc


def _attr_value(parent: Element, attr_id: str, value: str) -> None:
    av = SubElement(parent, _ns_tag("ATTRIBUTE-VALUE-STRING"))
    defn = SubElement(av, _ns_tag("DEFINITION"))
    SubElement(defn, _ns_tag("ATTRIBUTE-DEFINITION-STRING-REF")).text = attr_id
    SubElement(av, _ns_tag("THE-VALUE")).text = value


def _spec_relation(parent: Element, trace: dict, index: int) -> None:
    rel = SubElement(parent, _ns_tag("SPEC-RELATION"), {
        "IDENTIFIER": f"REL-{trace.get('source','')}-{trace.get('target','')}-{index}",
    })
    src = SubElement(rel, _ns_tag("SOURCE"))
    SubElement(src, _ns_tag("SPEC-OBJECT-REF")).text = trace["source"]
    tgt = SubElement(rel, _ns_tag("TARGET"))
    SubElement(tgt, _ns_tag("SPEC-OBJECT-REF")).text = trace["target"]
