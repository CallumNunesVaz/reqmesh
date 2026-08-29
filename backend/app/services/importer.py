"""Merge parsed ReqIF / SysML data into a project's YAML store.

The format parsers (:mod:`reqif_import`, :mod:`sysml_import`) return plain
dicts; this module is the single place that knows how to reconcile those with
existing entities, coerce values into the schema's enums, and write them out.
"""

from __future__ import annotations

from typing import Any

from app.core.ids import _ID_RE
from app.models.analysis import AnalysisCase
from app.models.definition import Definition
from app.models.requirement import (
    Priority,
    RequirementStatus,
    RequirementType,
    VerificationMethod,
)

_VALID_TYPES = {e.value for e in RequirementType}
_VALID_STATUSES = {e.value for e in RequirementStatus}
_VALID_PRIORITIES = {e.value for e in Priority}
_VALID_METHODS = {e.value for e in VerificationMethod}


def _clean_id(raw: str) -> str | None:
    """Return an id usable as a filename, or ``None`` if it can't be salvaged."""
    if not isinstance(raw, str):
        return None
    ident = raw.strip()
    if not ident or ".." in ident or not _ID_RE.match(ident):
        return None
    return ident


def _coerce(value, valid: set[str], default: str) -> str:
    if isinstance(value, str) and value.strip().lower() in valid:
        return value.strip().lower()
    return default


def _normalise_requirement(raw: dict) -> dict | None:
    rid = _clean_id(raw.get("id", ""))
    if rid is None:
        return None
    req = {
        "id": rid,
        "type": _coerce(raw.get("type"), _VALID_TYPES, "functional"),
        "name": str(raw.get("name") or rid),
        "description": str(raw.get("description") or ""),
        "priority": _coerce(raw.get("priority"), _VALID_PRIORITIES, "medium"),
        "status": _coerce(raw.get("status"), _VALID_STATUSES, "proposed"),
        "verification_method": _coerce(raw.get("verification_method"), _VALID_METHODS, "test"),
        "attributes": raw.get("attributes") or [],
        "relations": raw.get("relations") or [],
        "verification_cases": raw.get("verification_cases") or [],
        "verification_status": "pending",
        "rationale": str(raw.get("rationale") or ""),
        "source": str(raw.get("source") or ""),
        "parent": _clean_id(raw.get("parent", "")) if raw.get("parent") else None,
        # Parametrics carried through the SysML interchange.
        "parameters": raw.get("parameters") or [],
        "constraints": raw.get("constraints") or [],
    }
    if raw.get("subject"):
        req["subject"] = raw["subject"]
    if raw.get("cascade_from"):
        req["cascade_from"] = raw["cascade_from"]
    return req


def _normalise_component(raw: dict) -> dict | None:
    cid = _clean_id(raw.get("id", ""))
    if cid is None:
        return None
    return {
        "id": cid,
        "name": str(raw.get("name") or cid),
        "description": str(raw.get("description") or ""),
        "parent": _clean_id(raw.get("parent", "")) if raw.get("parent") else None,
        "quantity": int(raw.get("quantity") or 1),
        "satisfies": raw.get("satisfies") or [],
        "parameters": raw.get("parameters") or [],
    }


# Fields the import formats don't carry; seeded on create so imported records
# have the same shape as UI-created ones, but left untouched when updating an
# existing requirement (a merge must not wipe local-only data).
_CREATE_DEFAULTS: dict[str, Any] = {"allocated_to": "", "cascade_from": None, "baselines": []}


def import_into_store(store, parsed: dict, mode: str = "merge") -> dict:
    """Write parsed entities into ``store``.

    ``mode`` is ``"merge"`` (create new, update existing) or ``"replace"``
    (delete every current requirement/verification case first).  Returns a
    summary of what changed.
    """
    store.ensure_dirs()
    summary: dict[str, Any] = {"created": 0, "updated": 0, "skipped": 0, "traces_added": 0, "verification_cases": 0}
    summary["ignored"] = parsed.get("ignored") or {"lines": 0, "constructs": {}}

    # Normalise everything before touching the store. A malformed field (e.g.
    # a non-numeric component `quantity`) used to raise *after* replace mode
    # had deleted the requirements, verification cases and components, leaving
    # the project empty and the import incomplete.
    try:
        normalised_reqs = [_normalise_requirement(r) for r in parsed.get("requirements", [])]
        normalised_comps = [_normalise_component(c) for c in parsed.get("components", [])]
    except Exception as exc:
        raise ValueError(f"Could not parse the import (nothing was changed): {exc}") from exc

    if mode == "replace":
        for r in store.list_requirements():
            store.delete_requirement(r["id"])
        for vc in store.list_verification_cases():
            store.delete_verification_case(vc["id"])
        for c in store.list_components():
            store.delete_component(c["id"])
        for d in store.list_items("definitions"):
            store.delete_item("definitions", d["id"])
        for a in store.list_items("analysis_cases"):
            store.delete_item("analysis_cases", a["id"])

    for req in normalised_reqs:
        if req is None:
            summary["skipped"] += 1
            continue
        if store.get_requirement(req["id"]):
            store.update_requirement(req["id"], req)
            summary["updated"] += 1
        else:
            store.create_requirement({**_CREATE_DEFAULTS, **req})
            summary["created"] += 1

    for raw in parsed.get("verification_cases", []):
        vid = _clean_id(raw.get("id", ""))
        if vid is None:
            summary["skipped"] += 1
            continue
        vc = {
            "id": vid,
            "name": str(raw.get("name") or vid),
            "description": str(raw.get("description") or ""),
            "method": _coerce(raw.get("method"), _VALID_METHODS, "test"),
            "status": "pending",
            "result": None,
            "verified_requirements": raw.get("verified_requirements") or [],
        }
        if store.get_verification_case(vid):
            store.update_verification_case(vid, vc)
        else:
            store.create_verification_case(vc)
        summary["verification_cases"] += 1

    # Components (SysML part defs) — carry the design tree that rollups sum over.
    #
    # A component's parent must be another component. The file is not trusted to
    # honour that, and `parent` used to be written through verbatim, so an
    # import could seed a component parented to a requirement id — a shape the
    # API refuses everywhere else. Resolve against the components this import
    # can actually see: the ones already in the store, plus the ones arriving
    # alongside (a file listing a child before its parent is ordinary, so the
    # incoming set has to count).
    #
    # An unresolvable parent is dropped to top level and reported rather than
    # failing the import. Refusing the whole file over one bad pointer leaves
    # the user with nothing imported and no way to see what was wrong; landing
    # it with the repair named is recoverable.
    incoming_ids = {c["id"] for c in normalised_comps if c is not None}
    for comp in normalised_comps:
        if comp is None:
            summary["skipped"] += 1
            continue
        parent = comp.get("parent")
        if parent and parent not in incoming_ids and not store.get_component(parent):
            summary.setdefault("repaired_parents", []).append(
                {"component": comp["id"], "dropped_parent": parent}
            )
            comp["parent"] = None
        if store.get_component(comp["id"]):
            store.update_component(comp["id"], comp)
        else:
            store.create_component(comp)
        summary["components"] = summary.get("components", 0) + 1

    # Definitions (constraint def / calc def)
    for raw in parsed.get("definitions", []):
        did = _clean_id(raw.get("id", ""))
        if did is None:
            summary["skipped"] += 1
            continue
        item = {
            "id": did,
            "type": raw.get("type", "constraint"),
            "name": str(raw.get("name") or did),
            "parameters": raw.get("parameters") or [],
            "expr": str(raw.get("expr") or ""),
            "unit": str(raw.get("unit") or ""),
            "doc": str(raw.get("doc") or ""),
        }
        if not item["expr"]:
            summary["skipped"] += 1
            continue
        try:
            Definition(**item)
        except Exception:
            summary["skipped"] += 1
            continue
        store.write_item("definitions", did, item)
        summary["definitions"] = summary.get("definitions", 0) + 1

    # Analysis cases
    for raw in parsed.get("analysis_cases", []):
        aid = _clean_id(raw.get("id", ""))
        if aid is None:
            summary["skipped"] += 1
            continue
        item = {
            "id": aid,
            "name": str(raw.get("name") or aid),
            "doc": str(raw.get("doc") or ""),
            "scope": raw.get("scope") or [],
            "scope_components": raw.get("scope_components") or [],
            "overrides": raw.get("overrides") or {},
        }
        try:
            AnalysisCase(**item)
        except Exception:
            summary["skipped"] += 1
            continue
        store.write_item("analysis_cases", aid, item)
        summary["analysis_cases"] = summary.get("analysis_cases", 0) + 1

    # Merge traces, de-duplicating against what's already stored.
    incoming = parsed.get("traces", [])
    if incoming:
        existing = store.read_traces()
        links = existing.get("links", [])
        seen = {(l.get("source"), l.get("target"), l.get("type")) for l in links}
        for t in incoming:
            key = (t.get("source"), t.get("target"), t.get("type"))
            if key[0] and key[1] and key not in seen:
                links.append({"source": t["source"], "target": t["target"], "type": t.get("type", "traces")})
                seen.add(key)
                summary["traces_added"] += 1
        store.write_traces({"links": links})

    return summary


def parse_and_import(store, content: str | bytes, fmt: str = "auto", mode: str = "merge") -> dict:
    """Detect/parse ``content`` and import it. ``fmt`` is auto/reqif/sysml."""
    from app.services.reqif_import import parse_reqif
    from app.services.sysml_import import parse_sysml

    if isinstance(content, bytes):
        sniff = content.lstrip()[:200].decode("utf-8", errors="replace")
    else:
        sniff = content.lstrip()[:200]

    if fmt == "auto":
        fmt = "reqif" if ("<REQ-IF" in sniff or "<?xml" in sniff or "<reqif" in sniff.lower()) else "sysml"

    if fmt == "reqif":
        parsed = parse_reqif(content)
    elif fmt == "sysml":
        parsed = parse_sysml(content)
    else:
        raise ValueError(f"Unknown import format: {fmt}")

    result = import_into_store(store, parsed, mode=mode)
    result["format"] = fmt
    return result
