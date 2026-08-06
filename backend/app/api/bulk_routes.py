"""Bulk operations on requirements, components, verification cases,
specifications, risks, and change requests. Extracted from ``extra_routes.py``.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import ValidationError

from app.core.dependencies import get_store, require_maintain
from app.models.requirement import RequirementUpdate
from app.models.component import ComponentUpdate
from app.models.risk import RiskUpdate
from app.models.specification import SpecificationUpdate
from app.models.verification import VerificationCaseUpdate
from app.models.change_request import ChangeRequestUpdate
from app.services.history import record_change

router = APIRouter()


def _bulk_delete(store, ids: list[str], get_fn, delete_fn, record_type: str, username: str) -> int:
    deleted = 0
    for item_id in ids:
        before = get_fn(item_id)
        if before is None:
            continue
        if delete_fn(item_id):
            record_change(store, item_id, "delete", before, None, username)
            deleted += 1
    return deleted


def _bulk_update(store, ids: list[str], updates: dict, update_fn, username: str = "") -> int:
    """Apply *updates* to every item in *ids* via *update_fn*(item_id, updates).

    *update_fn* is typically ``store.update_requirement`` or
    ``store.update_component``. Returns the count of successful updates.
    """
    updated = 0
    for item_id in ids:
        if update_fn(item_id, updates):
            updated += 1
    return updated


# ── Requirements ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/bulk")
def bulk_update_requirements(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = RequirementUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")

    # Validate workflow transitions for every requirement before writing anything.
    # A single violation rejects the whole batch — a partially applied bulk
    # update is worse than a rejected one.
    if "status" in updates:
        from app.services.workflow import validate_transition
        meta = store.read_meta()
        for req_id in ids:
            before = store.get_requirement(req_id)
            if before is None:
                continue
            new_status = updates["status"]
            if before.get("status") != new_status:
                err = validate_transition(meta, before.get("status", "proposed"), new_status)
                if err:
                    raise HTTPException(
                        status_code=409,
                        detail=f"{req_id}: {err}",
                    )

    updated = []
    skipped = []
    for req_id in ids:
        before = store.get_requirement(req_id)
        if before is None:
            continue
        result = store.update_requirement(req_id, updates)
        if result:
            record_change(store, req_id, "update", before, result, user.get("username", ""))
            updated.append(req_id)
    return {"updated": len(updated), "ids": updated, "skipped": skipped}


@router.post("/projects/{project_id}/requirements/bulk-delete")
def bulk_delete_requirements(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = 0
    for req_id in data.get("ids", []):
        before = store.get_requirement(req_id)
        if store.delete_requirement(req_id):
            record_change(store, req_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


# ── Components ────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/components/bulk")
def bulk_update_components(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = ComponentUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    updated = 0
    for comp_id in ids:
        if store.update_component(comp_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/components/bulk-delete")
def bulk_delete_components(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = 0
    for comp_id in data.get("ids", []):
        before = store.get_component(comp_id)
        if before is None:
            continue
        promoted = []
        for child in store.list_components():
            if child.get("parent") == comp_id:
                store.update_component(child["id"], {"parent": before.get("parent")})
                promoted.append(child["id"])
                record_change(store, child["id"], "reparent",
                              {"parent": comp_id},
                              {"parent": before.get("parent")},
                              user.get("username", ""))
        if store.delete_component(comp_id):
            record_change(store, comp_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


@router.post("/projects/{project_id}/components/bulk-reparent")
def bulk_reparent_components(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    """Assign multiple components to a new parent (set parent=None to detach)."""
    store = get_store(project_id)
    ids = data.get("ids", [])
    parent = data.get("parent", None)
    updated = 0
    for comp_id in ids:
        if store.update_component(comp_id, {"parent": parent or None}):
            updated += 1
    return {"updated": updated}


# ── Verification Cases ────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/verification/bulk")
def bulk_update_verification_cases(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = VerificationCaseUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    updated = 0
    for vc_id in ids:
        if store.update_verification_case(vc_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/verification/bulk-delete")
def bulk_delete_verification_cases(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = _bulk_delete(store, data.get("ids", []), store.get_verification_case, store.delete_verification_case, "verification", user.get("username", ""))
    return {"deleted": deleted}


# ── Specifications ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/specifications/bulk")
def bulk_update_specifications(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = SpecificationUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    updated = 0
    for spec_id in ids:
        if store.update_specification(spec_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/specifications/bulk-delete")
def bulk_delete_specifications(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = _bulk_delete(store, data.get("ids", []), store.get_specification, store.delete_specification, "specification", user.get("username", ""))
    return {"deleted": deleted}


# ── Risks ─────────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/risks/bulk")
def bulk_update_risks(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = RiskUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    updated = 0
    for risk_id in ids:
        if store.update_item("risks", risk_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/risks/bulk-delete")
def bulk_delete_risks(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = 0
    for risk_id in data.get("ids", []):
        before = store.get_item("risks", risk_id)
        if before is None:
            continue
        if store.delete_item("risks", risk_id):
            record_change(store, risk_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


# ── Change Requests ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/change-requests/bulk")
def bulk_update_change_requests(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = ChangeRequestUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    updated = 0
    for cr_id in ids:
        if store.update_item("change_requests", cr_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/change-requests/bulk-delete")
def bulk_delete_change_requests(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    deleted = 0
    for cr_id in data.get("ids", []):
        before = store.get_item("change_requests", cr_id)
        if before is None:
            continue
        if store.delete_item("change_requests", cr_id):
            record_change(store, cr_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


# ── Bulk reparent + re-prefix for requirements ────────────────────────────────

def _collect_subtree(children_by_parent: dict[str, list[str]], root_id: str) -> list[str]:
    """Return root_id followed by all transitive descendant ids (pre-order)."""
    out = [root_id]
    for child_id in children_by_parent.get(root_id, []):
        out.extend(_collect_subtree(children_by_parent, child_id))
    return out


def _leading_prefix(item_id: str) -> str:
    """The leading alphabetic run of an ID, e.g. 'REQ' from 'REQ-0001'."""
    m = re.match(r"^([A-Za-z]+)", item_id or "")
    return m.group(1) if m else ""


@router.post("/projects/{project_id}/requirements/bulk-reparent")
def bulk_reparent_requirements(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    """Move selected requirements under a new parent and optionally re-prefix IDs.

    With ``re_prefix`` set and the new parent's prefix differing from a moved
    requirement's, that requirement and its entire descendant subtree are
    renamed to the new prefix. Parent pointers and relation targets — both
    inside the subtree and elsewhere in the project — are rewritten to the new
    IDs so nothing is left dangling.
    """
    store = get_store(project_id)
    ids = data.get("ids", [])
    new_parent = data.get("parent", None) or None
    re_prefix = data.get("re_prefix", False)

    # Snapshot the hierarchy before any mutation so subtree collection is stable.
    children_by_parent: dict[str, list[str]] = {}
    for r in store.list_requirements():
        children_by_parent.setdefault(r.get("parent"), []).append(r["id"])

    new_prefix = _leading_prefix(new_parent) if new_parent else ""

    # Pre-scan all requirements once to build the used-numbers set for the
    # destination prefix.  The per-id rescan in the old code was O(n·m) with
    # a regex per pair; moving 200 requirements in a 5000-requirement project
    # was a million regex matches.  This single scan feeds a live set that
    # each group updates with its own allocations, matching the old rescan
    # result exactly.
    used_nums_by_prefix: dict[str, set[int]] = {}
    if new_prefix and re_prefix:
        for r in store.list_requirements():
            mm = re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", r["id"])
            if mm:
                used_nums_by_prefix.setdefault(new_prefix, set()).add(int(mm.group(1)))

    updated: list[str] = []
    id_map: dict[str, str] = {}  # old_id -> new_id, across every moved subtree

    for req_id in ids:
        req = store.get_requirement(req_id)
        if req is None:
            continue
        old_prefix = _leading_prefix(req_id)
        if re_prefix and new_parent and new_prefix and old_prefix and old_prefix != new_prefix:
            subtree = _collect_subtree(children_by_parent, req_id)
            # Mirror the new parent's ID shape (separator + zero-padded width)
            # so re-prefixed IDs match the destination namespace's convention.
            pm = re.match(r"^[A-Za-z]+(\D*)(\d+)$", new_parent)
            sep, width = (pm.group(1), len(pm.group(2))) if pm else ("", 4)
            # Use the pre-scanned used-numbers set, warmed by allocations from
            # earlier groups.  Exclude any subtree node that already bears the
            # new prefix — the old per-id scan did the same, and changing it
            # would shift the allocation.
            live_nums = used_nums_by_prefix.setdefault(new_prefix, set())
            subtree_new_nums = {int(mm.group(1)) for old_id in subtree
                                if (mm := re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", old_id))}
            effective_used = live_nums - subtree_new_nums
            next_num = (max(effective_used) + 1) if effective_used else 1
            # Only nodes that share the moved group's prefix are renamed; other
            # descendants keep their ID but still get their parent pointer fixed.
            local_map = {old_id: old_id for old_id in subtree}
            for old_id in subtree:
                if old_id.startswith(old_prefix):
                    local_map[old_id] = f"{new_prefix}{sep}{str(next_num).zfill(width)}"
                    live_nums.add(next_num)
                    next_num += 1
            for old_id in subtree:
                node = store.get_requirement(old_id)
                if node is None:
                    continue
                node = dict(node)
                node["id"] = local_map[old_id]
                if old_id == req_id:
                    node["parent"] = new_parent
                else:
                    node["parent"] = local_map.get(node.get("parent"), node.get("parent"))
                for rel in node.get("relations", []):
                    if rel.get("target") in local_map:
                        rel["target"] = local_map[rel["target"]]
                store.delete_requirement(old_id)
                store.create_requirement(node)
                updated.append(node["id"])
            id_map.update({k: v for k, v in local_map.items() if k != v})
            continue
        if store.update_requirement(req_id, {"parent": new_parent}):
            updated.append(req_id)

    # Rewrite relation targets that point at renamed IDs from outside the moves.
    if id_map:
        renamed_new_ids = set(id_map.values())
        for r in store.list_requirements():
            if r["id"] in renamed_new_ids:
                continue  # its internal relations were already remapped above
            rels = r.get("relations", [])
            changed = False
            for rel in rels:
                tgt = rel.get("target")
                if tgt in id_map:
                    rel["target"] = id_map[tgt]
                    changed = True
            if changed:
                store.update_requirement(r["id"], {"relations": rels})

    return {"updated": len(updated), "ids": updated}
