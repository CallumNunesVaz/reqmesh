"""ReqIF 1.2 import — parse a ReqIF XML file back into reqmesh entities.

The parser is deliberately namespace-agnostic and tolerant: it matches on the
local (unqualified) tag name so files produced by DOORS, Polarion, Jama or by
reqmesh's own :mod:`reqif_export` all round-trip.  Attribute meaning is derived
from the ``LONG-NAME`` of the referenced attribute definition, so a tool that
labels its title column "Name" or "ReqIF.Text" still maps sensibly.

``parse_reqif`` returns a plain dict::

    {"requirements": [ {...}, ... ], "traces": [ {source, target, type}, ... ]}

so it stays independent of the storage layer; :mod:`app.services.importer`
turns that into persisted YAML.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element, fromstring, tostring
from xml.etree.ElementTree import ParseError as _XMLParseError


class ReqIFParseError(ValueError):
    """Raised when the supplied bytes are not usable ReqIF XML."""


def _local(tag: str) -> str:
    """Return an element's tag without its ``{namespace}`` prefix."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_all(root: Element, name: str) -> list[Element]:
    """Depth-first search for every element whose local tag == ``name``."""
    return [el for el in root.iter() if _local(el.tag) == name]


def _first_child(el: Element, name: str) -> Element | None:
    for child in el:
        if _local(child.tag) == name:
            return child
    return None

# Long-name (lower-cased, spaces/dots stripped) -> requirement field.  Several
# spellings map to the same field so imports from other tools land correctly.
_FIELD_ALIASES = {
    "id": None,  # handled via the SPEC-OBJECT IDENTIFIER, not an attribute
    "identifier": None,
    "name": "name",
    "title": "name",
    "reqiftext": "description",
    "text": "description",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "type": "type",
    "rationale": "rationale",
    "source": "source",
}


def _norm_key(long_name: str) -> str:
    return long_name.strip().lower().replace(" ", "").replace(".", "").replace("-", "").replace("_", "")


def _build_def_map(root: Element) -> dict[str, str]:
    """Map an attribute definition's IDENTIFIER -> its LONG-NAME.

    Values reference their definition by IDENTIFIER, so this lets us recover
    the human-readable column each value belongs to.
    """
    def_map: dict[str, str] = {}
    for el in root.iter():
        if _local(el.tag).startswith("ATTRIBUTE-DEFINITION-"):
            ident = el.get("IDENTIFIER")
            long_name = el.get("LONG-NAME")
            if ident and long_name:
                def_map[ident] = long_name
    return def_map


def _ref_target(value_el: Element) -> str | None:
    """The IDENTIFIER of the attribute definition a VALUE points at."""
    defn = _first_child(value_el, "DEFINITION")
    if defn is None:
        return None
    for child in defn:
        if _local(child.tag).endswith("-REF"):
            return (child.text or "").strip()
    return None


def _xhtml_value(value_el: Element) -> str:
    """Serialise the inner XHTML of an ATTRIBUTE-VALUE-XHTML's THE-VALUE."""
    the_value = _first_child(value_el, "THE-VALUE")
    if the_value is None:
        return ""
    parts: list[str] = []
    if the_value.text and the_value.text.strip():
        parts.append(the_value.text)
    for child in the_value:
        raw = tostring(child, encoding="unicode")
        # Strip namespace declarations/prefixes the serializer injects so the
        # stored description stays clean XHTML (<div>…</div>, not <ns0:div>).
        raw = raw.replace("xhtml:", "").replace("ns0:", "")
        parts.append(raw)
    text = "".join(parts).strip()
    return text


def _string_value(value_el: Element) -> str:
    the_value = _first_child(value_el, "THE-VALUE")
    if the_value is not None and the_value.text is not None:
        return the_value.text
    # Some tools store the value in a THE-VALUE attribute instead of a child.
    return value_el.get("THE-VALUE", "")


def _parse_spec_object(obj: Element, def_map: dict[str, str]) -> dict:
    req: dict = {
        "id": obj.get("IDENTIFIER", ""),
        "name": obj.get("LONG-NAME", "") or "",
        "attributes": [],
    }
    values = _first_child(obj, "VALUES")
    if values is None:
        return req

    for value_el in values:
        tag = _local(value_el.tag)
        if not tag.startswith("ATTRIBUTE-VALUE-"):
            continue
        ref = _ref_target(value_el)
        long_name = def_map.get(ref or "", ref or "")
        key = _norm_key(long_name)

        if tag == "ATTRIBUTE-VALUE-XHTML":
            content = _xhtml_value(value_el)
        else:
            content = _string_value(value_el)

        if key in _FIELD_ALIASES:
            field = _FIELD_ALIASES[key]
            if field is None:  # ID/identifier column — keep the richer one
                if content and not req.get("id"):
                    req["id"] = content
                continue
            # Description wins from XHTML; don't clobber it with an empty string.
            if content or not req.get(field):
                req[field] = content
        elif long_name and content:
            req["attributes"].append({"key": long_name, "value": content})
    return req


def _parse_relations(root: Element) -> list[dict]:
    traces: list[dict] = []
    for rel in _find_all(root, "SPEC-RELATION"):
        src_el = _first_child(rel, "SOURCE")
        tgt_el = _first_child(rel, "TARGET")
        src_ref = _first_child(src_el, "SPEC-OBJECT-REF") if src_el is not None else None
        tgt_ref = _first_child(tgt_el, "SPEC-OBJECT-REF") if tgt_el is not None else None
        source = (src_ref.text or "").strip() if src_ref is not None else ""
        target = (tgt_ref.text or "").strip() if tgt_ref is not None else ""
        if source and target:
            traces.append({"source": source, "target": target, "type": "traces"})
    return traces


def parse_reqif(content: str | bytes) -> dict:
    """Parse ReqIF XML text into ``{"requirements": [...], "traces": [...]}``."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    try:
        root = fromstring(content)
    except _XMLParseError as exc:
        raise ReqIFParseError(f"Not valid XML: {exc}") from exc

    if _local(root.tag) != "REQ-IF" and not _find_all(root, "SPEC-OBJECT"):
        raise ReqIFParseError("No ReqIF SPEC-OBJECTs found — is this a ReqIF file?")

    def_map = _build_def_map(root)
    requirements = [
        _parse_spec_object(obj, def_map) for obj in _find_all(root, "SPEC-OBJECT")
    ]
    requirements = [r for r in requirements if r.get("id")]
    traces = _parse_relations(root)
    return {"requirements": requirements, "traces": traces}
