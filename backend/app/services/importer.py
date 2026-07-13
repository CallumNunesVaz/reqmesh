"""Merge parsed ReqIF / SysML data into a project's YAML store.

The format parsers (:mod:`reqif_import`, :mod:`sysml_import`) return plain
dicts; this module is the single place that knows how to reconcile those with
existing entities, coerce values into the schema's enums, and write them out.
"""

from __future__ import annotations

from app.core.ids import _ID_RE
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
    }
    return req


# Fields the import formats don't carry; seeded on create so imported records
# have the same shape as UI-created ones, but left untouched when updating an
# existing requirement (a merge must not wipe local-only data).
_CREATE_DEFAULTS = {"allocated_to": "", "cascade_from": None, "baseline": None}


def import_into_store(store, parsed: dict, mode: str = "merge") -> dict:
    """Write parsed entities into ``store``.

    ``mode`` is ``"merge"`` (create new, update existing) or ``"replace"``
    (delete every current requirement/verification case first).  Returns a
    summary of what changed.
    """
    store.ensure_dirs()
    summary = {"created": 0, "updated": 0, "skipped": 0, "traces_added": 0, "verification_cases": 0}

    if mode == "replace":
        for r in store.list_requirements():
            store.delete_requirement(r["id"])
        for vc in store.list_verification_cases():
            store.delete_verification_case(vc["id"])

    for raw in parsed.get("requirements", []):
        req = _normalise_requirement(raw)
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
    from app.services.reqif_import import ReqIFParseError, parse_reqif
    from app.services.sysml_import import SysMLParseError, parse_sysml

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
