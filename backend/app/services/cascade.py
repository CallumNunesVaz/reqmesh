"""Cascade propagation for requirements.

A requirement with ``cascade_from`` set mirrors a fixed set of its source's
fields. These helpers own the transitive walk and the per-group copy creation,
lifted out of the API router so the logic is unit-testable without FastAPI.
"""
from __future__ import annotations

#: Fields a source edit propagates to its cascaded descendants. `verification_*`
#: is deliberately absent: verification is derived per requirement, and a child
#: has its own (usually empty) cases.
PROPAGATED_FIELDS = ("name", "description", "priority", "status", "type",
                     "rationale", "source", "allocated_to")

#: Fields a cascade copy takes from its source when first created.
CASCADE_FIELDS = ("name", "description", "priority", "status", "type")


def propagate(store, req_id: str, update_dict: dict, user: str = "") -> bool:
    """Apply the changed propagated fields to every transitive cascaded child.

    Returns True if any child changed. Only the fields that actually changed are
    written, so a concurrent edit to a child is not clobbered by a stale
    snapshot (the per-file lock cannot help once stale data is in the payload).
    """
    from app.services.history import record_change

    patch = {f: update_dict[f] for f in PROPAGATED_FIELDS if f in update_dict}
    if not patch:
        return False

    children_of: dict[str, list[dict]] = {}
    for r in store.list_requirements():
        src = r.get("cascade_from")
        if src:
            children_of.setdefault(src, []).append(r)

    changed = False
    seen = {req_id}
    queue = list(children_of.get(req_id, []))
    while queue:
        child = queue.pop(0)
        cid = child["id"]
        if cid in seen:
            continue
        seen.add(cid)
        child_before = dict(child)
        updated_child = store.update_requirement(cid, patch)
        if updated_child is not None:
            record_change(store, cid, "update", child_before, updated_child, user)
            changed = True
        queue.extend(children_of.get(cid, []))
    return changed


def create_copies(store, req_id: str, user: str = "") -> list[str]:
    """Create a cascaded copy under each direct child group; return the new ids.

    Empty when the source does not exist or has no child groups to cascade to.
    """
    from app.services.history import record_change
    from app.services.rename import suggest_id

    source = store.get_requirement(req_id)
    if source is None:
        return []

    all_reqs = store.list_requirements()
    meta = store.read_meta()
    # `known` grows as copies are allocated so the next suggestion sees the
    # previous one; suggest_id picks the next free slot by scanning the list.
    known = list(all_reqs)
    created: list[str] = []
    for child in all_reqs:
        if child.get("parent") == req_id and child.get("cascade_from") is None:
            new_id = suggest_id(known, meta, child["id"])
            new_req = {k: source[k] for k in CASCADE_FIELDS if k in source}
            new_req["id"] = new_id
            new_req["parent"] = child["id"]
            new_req["cascade_from"] = req_id
            new_req["attributes"] = []
            new_req["relations"] = [{"type": "derives", "target": req_id}]
            new_req["verification_cases"] = []
            new_req["verification_status"] = "pending"
            store.create_requirement(new_req)
            record_change(store, new_id, "create", None, new_req, user)
            known.append(new_req)
            created.append(new_id)
    return created


def break_link(store, req_id: str, break_children: bool = False) -> str:
    """Detach a cascaded requirement from its source; return the source id.

    Writes only ``cascade_from``, rather than the whole stale record the route
    used to send, which clobbered any concurrent edit.
    """
    req = store.get_requirement(req_id)
    if req is None:
        return ""
    source_id = req.get("cascade_from") or ""
    if not source_id:
        return ""
    store.update_requirement(req_id, {"cascade_from": None})
    if break_children:
        for r in store.list_requirements():
            if r.get("cascade_from") == req_id:
                store.update_requirement(r["id"], {"cascade_from": None})
    return source_id
