"""Baseline definition bookkeeping.

A baseline is stored two ways: as an ordered definition in the project's
``_meta.yaml`` (name/symbol/description/due date), and as a name list on every
requirement and component that belongs to it. Keeping the two in step — across
create/upsert, reorder, rename and delete — is what this module owns. The routes
are thin wrappers that translate :class:`BaselineError` into an HTTP status.
"""
from __future__ import annotations

import datetime

from app.models.baseline import DUE_DATE_RE
from app.services.meta_defs import normalize_baseline_defs, serialize_meta_defs


class BaselineError(Exception):
    """A baseline operation that should surface as an HTTP error."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def validate_due_dates(baselines: list) -> None:
    """Every due date must be ``YYYY-MM-DD`` or empty, and not go backwards.

    Raises :class:`BaselineError` (400) on the first violation. The raw input is
    validated for individual dates because ``normalize_baseline_defs`` degrades
    malformed dates on the read path; the monotonic check runs on the normalized
    form, which knows the sequence order.
    """
    for item in (baselines or []):
        if isinstance(item, str) or not isinstance(item, dict):
            continue
        due = str(item.get("due_date", "") or "").strip()
        if not due:
            continue
        if not DUE_DATE_RE.match(due):
            raise BaselineError(f"Invalid due date: {due} (expected YYYY-MM-DD)")
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            raise BaselineError(f"Invalid due date: {due} (expected YYYY-MM-DD)") from None

    prev_date = None
    prev_name = None
    for d in normalize_baseline_defs(baselines):
        due = d.get("due_date", "")
        if not due:
            continue
        if prev_date is not None and due < prev_date:
            raise BaselineError(
                f"Due dates must not go backwards: {d['name']} ({due}) "
                f"is due before {prev_name} ({prev_date})"
            )
        prev_date = due
        prev_name = d["name"]


def upsert(store, name: str, symbol: str, description: str, due_date: str,
           requirements: list[str]) -> dict:
    """Create or update a baseline definition and assign it to requirements."""
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        existing = next((d for d in defs if d["name"] == name), None)
        if existing:
            existing["symbol"] = symbol or existing["symbol"]
            existing["description"] = description or existing["description"]
            if due_date:
                existing["due_date"] = due_date
        else:
            defs.append({"name": name, "symbol": symbol,
                         "description": description, "due_date": due_date})
        serialized = serialize_meta_defs(defs)
        validate_due_dates(serialized)
        meta["baselines"] = serialized
        store._write_meta_unlocked(meta)

    updated = 0
    for req_id in requirements:
        req = store.get_requirement(req_id)
        if req is None:
            continue
        blist = list(req.get("baselines") or [])
        if name not in blist:
            blist.append(name)
            if store.update_requirement(req_id, {"baselines": blist}):
                updated += 1
    return {"name": name, "symbol": symbol, "description": description,
            "due_date": due_date, "requirements_assigned": updated}


def reorder(store, names: list[str]) -> list:
    """Rewrite the baseline sequence; returns the normalized definitions."""
    with store.meta_lock():
        meta = store.read_meta()
        current_defs = normalize_baseline_defs(meta.get("baselines", []))
        defined_names = [d["name"] for d in current_defs]
        if set(names) != set(defined_names) or len(names) != len(defined_names):
            raise BaselineError("names must list every defined baseline exactly once")
        by_name = {d["name"]: d for d in current_defs}
        reordered = [dict(by_name[nm]) for nm in names]
        serialized = serialize_meta_defs(reordered)
        validate_due_dates(serialized)
        meta["baselines"] = serialized
        store._write_meta_unlocked(meta)
    return normalize_baseline_defs(serialized)


def rename(store, name: str, new_name: str, symbol: str | None,
           description: str | None, due_date: str | None) -> dict:
    """Rename (and optionally edit) a baseline across every holder."""
    if not new_name:
        raise BaselineError("New name is required")
    # A rename onto an existing frozen snapshot is a collision. Skipped when the
    # name is unchanged, so an edit on a frozen baseline is not refused as a
    # duplicate of itself.
    if new_name != name and store.get_item("baselines", new_name) is not None:
        raise BaselineError("A baseline with that name already exists", 409)

    found = False
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        if new_name != name and any(d["name"] == new_name for d in defs):
            raise BaselineError("A baseline with that name already exists", 409)
        for d in defs:
            if d["name"] == name:
                found = True
                d["name"] = new_name
                if symbol is not None:
                    d["symbol"] = symbol
                if description is not None:
                    d["description"] = description
                if due_date is not None:
                    d["due_date"] = due_date
        if found:
            serialized = serialize_meta_defs(defs)
            validate_due_dates(serialized)
            meta["baselines"] = serialized
            store._write_meta_unlocked(meta)

    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            store.update_requirement(r["id"], {"baselines": [new_name if b == name else b for b in blist]})
            updated += 1
    comps_updated = 0
    for c in store.list_components():
        blist = list(c.get("baselines") or [])
        if name in blist:
            store.update_item("components", c["id"], {"baselines": [new_name if b == name else b for b in blist]})
            comps_updated += 1

    frozen = store.get_item("baselines", name)
    if frozen is not None:
        if symbol is not None:
            frozen["symbol"] = symbol
        if description is not None:
            frozen["description"] = description
        if new_name != name:
            frozen["name"] = new_name
            store.write_item("baselines", new_name, frozen)
            store.delete_item("baselines", name)
        else:
            store.write_item("baselines", name, frozen)
    elif not found and updated == 0 and comps_updated == 0:
        raise BaselineError("Baseline not found", 404)
    return {"old_name": name, "new_name": new_name, "requirements_updated": updated}


def delete(store, name: str) -> dict:
    """Delete a baseline definition, its snapshot, and every membership."""
    baseline = store.get_item("baselines", name)
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    in_defs = any(d["name"] == name for d in defs)
    if baseline is None and not in_defs:
        raise BaselineError("Baseline not found", 404)
    store.delete_item("baselines", name)
    with store.meta_lock():
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        defs = [d for d in defs if d["name"] != name]
        meta["baselines"] = serialize_meta_defs(defs)
        store._write_meta_unlocked(meta)
    updated = 0
    for r in store.list_requirements():
        blist = list(r.get("baselines") or [])
        if name in blist:
            blist.remove(name)
            store.update_requirement(r["id"], {"baselines": blist})
            updated += 1
    for c in store.list_components():
        blist = list(c.get("baselines") or [])
        if name in blist:
            blist.remove(name)
            store.update_item("components", c["id"], {"baselines": blist})
    return {"name": name, "requirements_cleared": updated}
