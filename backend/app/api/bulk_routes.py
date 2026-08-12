"""Bulk operations on requirements, components, verification cases,
specifications, risks, and change requests. Extracted from ``extra_routes.py``.
"""
from __future__ import annotations


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
from app.services.baseline_membership import apply_membership, defined_baseline_names
from app.services.reparent import apply_reparent, plan_reparent, validate_component_parent
from app.services.delete_guard import check_deletable

router = APIRouter()


# ── Requirements ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/bulk")
def bulk_update_requirements(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    ids = data.get("ids", [])

    # Additive baseline membership. `updates.baselines` replaces the list, which
    # is right for the edit modal (it says so) but wrong for the one-click bulk
    # bar, where it silently dropped every other baseline a row carried.
    add = data.get("baselines_add") or []
    remove = data.get("baselines_remove") or []
    if add or remove:
        if not ids:
            raise HTTPException(status_code=400, detail="ids required")
        if "baselines" in (data.get("updates") or {}):
            raise HTTPException(
                status_code=409,
                detail="baselines_add/baselines_remove cannot be combined with updates.baselines",
            )
        defined = defined_baseline_names(store.read_meta())
        unknown = sorted({b for b in [*add, *remove] if b not in defined})
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Baseline not defined in this project: {', '.join(unknown)}",
            )
        return apply_membership(store, ids, add, remove, user.get("username", ""))

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
    force = data.get("force", False)
    deleted = 0
    refused = []
    for req_id in data.get("ids", []):
        before = store.get_requirement(req_id)
        if before is None:
            continue
        try:
            check_deletable(store, "requirements", req_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
        if store.delete_requirement(req_id):
            record_change(store, req_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


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
    force = data.get("force", False)
    deleted = 0
    refused = []
    for comp_id in data.get("ids", []):
        before = store.get_component(comp_id)
        if before is None:
            continue
        try:
            check_deletable(store, "components", comp_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
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
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


@router.post("/projects/{project_id}/components/bulk-reparent")
def bulk_reparent_components(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    """Assign multiple components to a new parent (set parent=None to detach)."""
    store = get_store(project_id)
    ids = data.get("ids", [])
    parent = data.get("parent", None) or None

    # The single-item PUT has always refused a cycle; this path did not, so the
    # move the API rejects one at a time was accepted in a batch — detaching the
    # branch from /tree, which then silently stopped returning it. One scan is
    # shared across every id rather than re-read per component.
    components = store.list_components()
    for comp_id in ids:
        reason = validate_component_parent(components, comp_id, parent)
        if reason:
            raise HTTPException(status_code=400, detail=reason)

    updated = 0
    for comp_id in ids:
        if store.update_component(comp_id, {"parent": parent}):
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
        before = store.get_verification_case(vc_id)
        if before is None:
            continue
        result = store.update_verification_case(vc_id, updates)
        if result:
            record_change(store, vc_id, "update", before, result, user.get("username", ""))
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/verification/bulk-delete")
def bulk_delete_verification_cases(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    force = data.get("force", False)
    deleted = 0
    refused = []
    for vc_id in data.get("ids", []):
        before = store.get_verification_case(vc_id)
        if before is None:
            continue
        try:
            check_deletable(store, "verification_cases", vc_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
        if store.delete_verification_case(vc_id):
            record_change(store, vc_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


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
        before = store.get_specification(spec_id)
        if before is None:
            continue
        result = store.update_specification(spec_id, updates)
        if result:
            record_change(store, spec_id, "update", before, result, user.get("username", ""))
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/specifications/bulk-delete")
def bulk_delete_specifications(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    force = data.get("force", False)
    deleted = 0
    refused = []
    for spec_id in data.get("ids", []):
        before = store.get_specification(spec_id)
        if before is None:
            continue
        try:
            check_deletable(store, "specifications", spec_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
        if store.delete_specification(spec_id):
            record_change(store, spec_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


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
        before = store.get_item("risks", risk_id)
        if before is None:
            continue
        result = store.update_item("risks", risk_id, updates)
        if result:
            record_change(store, risk_id, "update", before, result, user.get("username", ""))
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/risks/bulk-delete")
def bulk_delete_risks(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    force = data.get("force", False)
    deleted = 0
    refused = []
    for risk_id in data.get("ids", []):
        before = store.get_item("risks", risk_id)
        if before is None:
            continue
        try:
            check_deletable(store, "risks", risk_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
        if store.delete_item("risks", risk_id):
            record_change(store, risk_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


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
        before = store.get_item("change_requests", cr_id)
        if before is None:
            continue
        result = store.update_item("change_requests", cr_id, updates)
        if result:
            record_change(store, cr_id, "update", before, result, user.get("username", ""))
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/change-requests/bulk-delete")
def bulk_delete_change_requests(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    force = data.get("force", False)
    deleted = 0
    refused = []
    for cr_id in data.get("ids", []):
        before = store.get_item("change_requests", cr_id)
        if before is None:
            continue
        try:
            check_deletable(store, "change_requests", cr_id, force)
        except HTTPException as exc:
            if exc.status_code == 409:
                refused.append(exc.detail)
                continue
            raise
        if store.delete_item("change_requests", cr_id):
            record_change(store, cr_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    resp = {"deleted": deleted}
    if refused:
        resp["refused"] = refused
    return resp


# ── Bulk reparent + re-prefix for requirements ────────────────────────────────

@router.post("/projects/{project_id}/requirements/bulk-reparent")
def bulk_reparent_requirements(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    """Move selected requirements under a new parent and optionally re-prefix IDs.

    With ``re_prefix`` set and the new parent's prefix differing from a moved
    requirement's, that requirement and its entire descendant subtree are
    renamed to the new prefix. Parent pointers and relation targets — both
    inside the subtree and elsewhere in the project — are rewritten to the new
    IDs so nothing is left dangling.

    ``dry_run`` returns the same ``renames`` the real call would perform without
    writing anything, so the UI can show the rename before the user commits to
    it. The planning is shared with the write path rather than reimplemented, so
    the preview cannot drift from what actually happens.
    """
    store = get_store(project_id)
    ids = data.get("ids", [])
    new_parent = data.get("parent", None) or None
    re_prefix = data.get("re_prefix", False)
    dry_run = bool(data.get("dry_run", False))

    plan = plan_reparent(store.list_requirements(), ids, new_parent, re_prefix)

    if plan.rejected:
        raise HTTPException(status_code=400, detail=plan.rejected[0][1])

    if dry_run:
        return {
            "dry_run": True,
            "updated": plan.affected_count,
            "ids": [],
            "renames": plan.renames,
        }

    return apply_reparent(store, plan, user.get("username", ""))
