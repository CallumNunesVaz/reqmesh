from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, File, Form, UploadFile
from pydantic import ValidationError

from app.core.config import settings
from app.core.dependencies import get_store, require_edit, get_current_user
from app.core.ids import safe_id
from app.models.change_request import ChangeRequestCreate, ChangeRequestUpdate
from app.models.component import ComponentCreate, ComponentUpdate
from app.models.requirement import RequirementUpdate
from app.models.risk import RiskCreate, RiskUpdate, CommentCreate, DecisionRecordCreate, DecisionRecordUpdate
from app.models.verification import VerificationCaseCreate, VerificationCaseUpdate
from app.models.specification import SpecificationCreate, SpecificationUpdate
from app.services.publisher import Publisher
from app.services.integrity import IntegrityChecker, clear_suspect_links
from app.services.git_hooks import install_hook, uninstall_hook
from app.services.history import record_change

router = APIRouter()


async def _read_upload_capped(file: UploadFile, limit_mb: int) -> bytes:
    """Read an uploaded file into memory, aborting with 413 once it exceeds the
    configured limit so a large upload can't exhaust memory."""
    limit = max(1, limit_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(4 * 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {limit_mb} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _sorted_by_modified(items: list[dict], key: str = "modified") -> list[dict]:
    return sorted(items, key=lambda x: x.get(key, ""), reverse=True)


# ── Change Requests ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/change-requests")
async def list_change_requests(project_id: str):
    return _sorted_by_modified(get_store(project_id).list_items("change_requests"))


@router.post("/projects/{project_id}/change-requests", status_code=201)
async def create_change_request(project_id: str, data: ChangeRequestCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    cr = data.model_dump(mode="json")
    cr.setdefault("status", "submitted")
    cr.setdefault("submitted_by", user.get("username", ""))
    cr.setdefault("reviewed_by", "")
    cr.setdefault("approved_by", "")
    result = store.create_item("change_requests", cr)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_change_request
        notify_change_request(store, project_id, result["id"], "created", user.get("username", ""))
    except Exception:
        pass
    return result


@router.put("/projects/{project_id}/change-requests/{cr_id}")
async def update_change_request(project_id: str, cr_id: str, data: ChangeRequestUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("change_requests", cr_id)
    result = store.update_item("change_requests", cr_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    record_change(store, cr_id, "update", before, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_change_request
        notify_change_request(store, project_id, cr_id, "updated", user.get("username", ""))
    except Exception:
        pass
    return result


@router.delete("/projects/{project_id}/change-requests/{cr_id}")
async def delete_change_request(project_id: str, cr_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("change_requests", cr_id)
    if not store.delete_item("change_requests", cr_id):
        raise HTTPException(status_code=404, detail="Change request not found")
    record_change(store, cr_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Risks ─────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/risks")
async def list_risks(project_id: str):
    return _sorted_by_modified(get_store(project_id).list_items("risks"))


@router.post("/projects/{project_id}/risks", status_code=201)
async def create_risk(project_id: str, data: RiskCreate, user: dict = Depends(require_edit)):
    r = data.model_dump(mode="json")
    r.setdefault("impact", "")
    r.setdefault("mitigation", "")
    r.setdefault("linked_requirements", [])
    r.setdefault("status", "open")
    store = get_store(project_id)
    result = store.create_item("risks", r)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_risk
        notify_risk(store, project_id, result["id"], "created", user.get("username", ""))
    except Exception:
        pass
    return result


@router.put("/projects/{project_id}/risks/{risk_id}")
async def update_risk(project_id: str, risk_id: str, data: RiskUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("risks", risk_id)
    result = store.update_item("risks", risk_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    record_change(store, risk_id, "update", before, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_risk
        notify_risk(get_store(project_id), project_id, risk_id, "updated", user.get("username", ""))
    except Exception:
        pass
    return result


@router.delete("/projects/{project_id}/risks/{risk_id}")
async def delete_risk(project_id: str, risk_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("risks", risk_id)
    if not store.delete_item("risks", risk_id):
        raise HTTPException(status_code=404, detail="Risk not found")
    record_change(store, risk_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Comments ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/comments")
async def list_comments(project_id: str, requirement_id: Optional[str] = Query(None)):
    comments = get_store(project_id).list_items("comments")
    if requirement_id:
        comments = [c for c in comments if c.get("requirement_id") == requirement_id]
    return _sorted_by_modified(comments, key="created")


@router.post("/projects/{project_id}/comments", status_code=201)
async def create_comment(project_id: str, data: CommentCreate, user: dict = Depends(require_edit)):
    c = data.model_dump(mode="json")
    c["id"] = f"COMMENT-{uuid.uuid4().hex[:8].upper()}"
    c["resolved"] = False
    c.setdefault("author", user.get("username", ""))
    result = get_store(project_id).create_item("comments", c)
    try:
        from app.services.email_service import notify_comment
        notify_comment(get_store(project_id), project_id, data.requirement_id, user.get("username", ""), data.text)
    except Exception:
        pass
    return result


@router.delete("/projects/{project_id}/comments/{comment_id}")
async def delete_comment(project_id: str, comment_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("comments", comment_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.patch("/projects/{project_id}/comments/{comment_id}")
async def update_comment(project_id: str, comment_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    existing = store.get_item("comments", comment_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    updates = {}
    if "resolved" in data:
        updates["resolved"] = bool(data["resolved"])
    if "text" in data and data["text"] is not None:
        updates["text"] = str(data["text"])
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = store.update_item("comments", comment_id, updates)
    return result


# ── Decision Records ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/decisions")
async def list_decisions(project_id: str):
    return _sorted_by_modified(get_store(project_id).list_items("decisions"))


@router.post("/projects/{project_id}/decisions", status_code=201)
async def create_decision(project_id: str, data: DecisionRecordCreate, user: dict = Depends(require_edit)):
    d = data.model_dump(mode="json")
    d.setdefault("rationale", "")
    d.setdefault("consequences", "")
    d.setdefault("linked_requirements", [])
    d.setdefault("status", "accepted")
    d.setdefault("decided_by", user.get("username", ""))
    result = get_store(project_id).create_item("decisions", d)
    record_change(get_store(project_id), result["id"], "create", None, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_decision
        notify_decision(get_store(project_id), project_id, result["id"], "created", user.get("username", ""))
    except Exception:
        pass
    return result


@router.put("/projects/{project_id}/decisions/{dec_id}")
async def update_decision(project_id: str, dec_id: str, data: DecisionRecordUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("decisions", dec_id)
    result = store.update_item("decisions", dec_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    record_change(store, dec_id, "update", before, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_decision
        notify_decision(get_store(project_id), project_id, dec_id, "updated", user.get("username", ""))
    except Exception:
        pass
    return result


@router.delete("/projects/{project_id}/decisions/{dec_id}")
async def delete_decision(project_id: str, dec_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("decisions", dec_id)
    if not store.delete_item("decisions", dec_id):
        raise HTTPException(status_code=404, detail="Decision not found")
    record_change(store, dec_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Bulk Operations ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/bulk")
async def bulk_update_requirements(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    ids = data.get("ids", [])
    try:
        updates = RequirementUpdate.model_validate(data.get("updates", {})).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    if not ids or not updates:
        raise HTTPException(status_code=400, detail="ids and updates required")
    meta = store.read_meta() if "status" in updates else None
    updated = []
    skipped = []
    for req_id in ids:
        before = store.get_requirement(req_id)
        if before is None:
            continue
        # Enforce the same workflow rules as the single-requirement update.
        if meta is not None and before.get("status") != updates["status"]:
            from app.services.workflow import validate_transition
            err = validate_transition(meta, before.get("status", "proposed"), updates["status"])
            if err:
                skipped.append({"id": req_id, "reason": err})
                continue
        result = store.update_requirement(req_id, updates)
        if result:
            record_change(store, req_id, "update", before, result, user.get("username", ""))
            updated.append(req_id)
    return {"updated": len(updated), "ids": updated, "skipped": skipped}


@router.post("/projects/{project_id}/requirements/bulk-delete")
async def bulk_delete_requirements(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    deleted = 0
    for req_id in data.get("ids", []):
        before = store.get_requirement(req_id)
        if store.delete_requirement(req_id):
            record_change(store, req_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


# ── Bulk operations for other entity types ─────────────────────────────────────

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


@router.post("/projects/{project_id}/components/bulk")
async def bulk_update_components(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
async def bulk_delete_components(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
        if store.delete_component(comp_id):
            record_change(store, comp_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


@router.post("/projects/{project_id}/components/bulk-reparent")
async def bulk_reparent_components(project_id: str, data: dict, user: dict = Depends(require_edit)):
    """Assign multiple components to a new parent (set parent=None to detach)."""
    store = get_store(project_id)
    ids = data.get("ids", [])
    parent = data.get("parent", None)
    updated = 0
    for comp_id in ids:
        if store.update_component(comp_id, {"parent": parent or None}):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/verification/bulk")
async def bulk_update_verification_cases(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
async def bulk_delete_verification_cases(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    deleted = _bulk_delete(store, data.get("ids", []), store.get_verification_case, store.delete_verification_case, "verification", user.get("username", ""))
    return {"deleted": deleted}


@router.post("/projects/{project_id}/specifications/bulk")
async def bulk_update_specifications(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
async def bulk_delete_specifications(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    deleted = _bulk_delete(store, data.get("ids", []), store.get_specification, store.delete_specification, "specification", user.get("username", ""))
    return {"deleted": deleted}


@router.post("/projects/{project_id}/risks/bulk")
async def bulk_update_risks(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
async def bulk_delete_risks(project_id: str, data: dict, user: dict = Depends(require_edit)):
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


@router.post("/projects/{project_id}/change-requests/bulk")
async def bulk_update_change_requests(project_id: str, data: dict, user: dict = Depends(require_edit)):
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
        if store.update_item("change-requests", cr_id, updates):
            updated += 1
    return {"updated": updated}


@router.post("/projects/{project_id}/change-requests/bulk-delete")
async def bulk_delete_change_requests(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    deleted = 0
    for cr_id in data.get("ids", []):
        before = store.get_item("change-requests", cr_id)
        if before is None:
            continue
        if store.delete_item("change-requests", cr_id):
            record_change(store, cr_id, "delete", before, None, user.get("username", ""))
            deleted += 1
    return {"deleted": deleted}


# ── Bulk reparent + re-prefix for requirements ─────────────────────────────────

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
async def bulk_reparent_requirements(project_id: str, data: dict, user: dict = Depends(require_edit)):
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

    updated: list[str] = []
    id_map: dict[str, str] = {}  # old_id -> new_id, across every moved subtree

    for req_id in ids:
        req = store.get_requirement(req_id)
        if req is None:
            continue
        old_prefix = _leading_prefix(req_id)
        if re_prefix and new_parent and new_prefix and old_prefix and old_prefix != new_prefix:
            subtree = _collect_subtree(children_by_parent, req_id)
            subtree_set = set(subtree)
            # Mirror the new parent's ID shape (separator + zero-padded width)
            # so re-prefixed IDs match the destination namespace's convention.
            pm = re.match(r"^[A-Za-z]+(\D*)(\d+)$", new_parent)
            sep, width = (pm.group(1), len(pm.group(2))) if pm else ("", 4)
            # Allocate fresh suffixes past whatever the new prefix already uses,
            # so a moved item never overwrites an existing ID (e.g. the parent).
            used_nums = set()
            for r in store.list_requirements():
                if r["id"] in subtree_set:
                    continue
                mm = re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", r["id"])
                if mm:
                    used_nums.add(int(mm.group(1)))
            next_num = (max(used_nums) + 1) if used_nums else 1
            # Only nodes that share the moved group's prefix are renamed; other
            # descendants keep their ID but still get their parent pointer fixed.
            local_map = {old_id: old_id for old_id in subtree}
            for old_id in subtree:
                if old_id.startswith(old_prefix):
                    local_map[old_id] = f"{new_prefix}{sep}{str(next_num).zfill(width)}"
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


# ── Impact Analysis ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/impact")
async def get_impact(project_id: str, req_id: str):
    store = get_store(project_id)
    all_reqs = store.list_requirements()
    req = store.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    dependents = []
    cascades = []
    for r in all_reqs:
        for rel in r.get("relations", []):
            if rel.get("target") == req_id:
                dependents.append({"id": r["id"], "name": r.get("name", ""), "relation": rel["type"]})
        if r.get("cascade_from") == req_id:
            cascades.append(r["id"])
        if r.get("parent") == req_id:
            dependents.append({"id": r["id"], "name": r.get("name", ""), "relation": "child"})
    return {"requirement": req_id, "dependents": dependents, "cascade_children": cascades, "count": len(dependents) + len(cascades)}


# ── Gap Analysis ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/gap-analysis")
async def gap_analysis(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    gaps = []
    for r in reqs:
        issues = []
        if not r.get("description", "").strip(): issues.append("no_description")
        if not r.get("rationale", "").strip(): issues.append("no_rationale")
        if not r.get("source", "").strip(): issues.append("no_source")
        if not r.get("relations"): issues.append("unlinked")
        if issues:
            gaps.append({"id": r["id"], "name": r.get("name", ""), "issues": issues})
    return {"total": len(reqs), "gaps": len(gaps), "items": gaps}


# ── Coverage Analysis ─────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/coverage")
async def coverage_analysis(project_id: str):
    from app.services.tracing import trace_all
    items = trace_all(get_store(project_id))
    total = len(items)
    if total == 0:
        return {"total": 0, "shallow_covered": 0, "deep_covered": 0, "coverage_pct": 0, "deep_pct": 0, "items": []}
    shallow = sum(1 for i in items if i["shallow"])
    deep = sum(1 for i in items if i["deep"])
    return {
        "total": total, "shallow_covered": shallow, "deep_covered": deep,
        "coverage_pct": round(shallow / total * 100),
        "deep_pct": round(deep / total * 100),
        "items": items,
    }


@router.get("/projects/{project_id}/trace")
async def trace_report(project_id: str, format: str = "json"):
    from app.services.tracing import trace_all
    items = trace_all(get_store(project_id))
    if format == "text":
        lines = []
        for item in items:
            status = "ok" if item["deep"] else "not ok"
            lines.append(f"{status} [ {item['id']} ] shallow={item['shallow']} deep={item['deep']}")
        return {"format": "text", "content": "\n".join(lines)}
    return items


# ── Conflict Detection ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/conflicts")
async def detect_conflicts(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    conflicts = []
    for r in reqs:
        for rel in r.get("relations", []):
            if rel["type"] == "conflicts":
                conflicts.append({"a": r["id"], "b": rel["target"], "type": "explicit_conflict"})

    duplicate_names: dict[str, list[str]] = {}
    for r in reqs:
        name_key = r.get("name", "").strip().lower()
        if name_key:
            duplicate_names.setdefault(name_key, []).append(r["id"])
    for name, ids in duplicate_names.items():
        if len(ids) > 1:
            conflicts.append({"ids": ids, "type": "duplicate_name", "name": name})
    return {"count": len(conflicts), "conflicts": conflicts}


# ── Version History ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/history")
async def requirement_history(project_id: str, req_id: str):
    return get_store(project_id).list_history(req_id)[:50]


# ── Git Log ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/git/log")
async def git_log(project_id: str, limit: int = Query(50, ge=1, le=500)):
    from app.services import git_service

    store = get_store(project_id)
    return {
        "is_repo": git_service.is_repo(store.root),
        "commits": git_service.log(store.root, limit),
    }


# ── Compliance ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/compliance")
async def compliance_status(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    standards: dict[str, int] = {}
    for r in reqs:
        for attr in r.get("attributes", []):
            if attr.get("key") == "standard" and attr.get("value"):
                std = attr["value"]
                standards[std] = (standards.get(std) or 0) + 1
    return {"standards": [{"name": k, "count": v} for k, v in sorted(standards.items())], "tracked_count": sum(standards.values()), "total_requirements": len(reqs)}


# ── Metrics ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/metrics")
async def project_metrics(project_id: str):
    store = get_store(project_id)
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    total = len(reqs)
    if total == 0:
        return {"total": 0}
    statuses: dict[str, int] = {}
    baselines = set()
    with_desc = with_rationale = with_source = with_alloc = with_trace = with_cascade = 0
    for r in reqs:
        statuses[r.get("status", "proposed")] = statuses.get(r.get("status", "proposed"), 0) + 1
        for b in (r.get("baselines") or []):
            if b: baselines.add(b)
        if r.get("description", "").strip(): with_desc += 1
        if r.get("rationale", "").strip(): with_rationale += 1
        if r.get("source", "").strip(): with_source += 1
        if r.get("allocated_to", "").strip(): with_alloc += 1
        if r.get("relations"): with_trace += 1
        if r.get("cascade_from"): with_cascade += 1

    effort_total = sum(r.get("effort") or 0 for r in reqs)
    effort_done = sum(r.get("effort") or 0 for r in reqs if r.get("status") in ("verified", "implemented", "deprecated"))

    return {
        "total": total,
        "verification_cases": len(vcs),
        "baselines": len(baselines),
        "total_effort": effort_total,
        "completed_effort": effort_done,
        "status_distribution": statuses,
        "quality": {
            "with_description": with_desc,
            "with_rationale": with_rationale,
            "with_source": with_source,
            "with_allocation": with_alloc,
            "with_traceability": with_trace,
            "cascaded": with_cascade,
        },
        "quality_pct": {
            "description": round(with_desc / total * 100),
            "rationale": round(with_rationale / total * 100),
            "source": round(with_source / total * 100),
            "allocation": round(with_alloc / total * 100),
            "traceability": round(with_trace / total * 100),
        },
    }


@router.get("/projects/{project_id}/backlog")
async def prioritized_backlog(project_id: str, sort: str = "priority"):
    store = get_store(project_id)
    reqs = store.list_requirements()
    results = []
    for r in reqs:
        if r.get("status") in ("rejected", "deprecated"):
            continue
        priorities = r.get("priorities", {})
        combined = sum(priorities.values()) if priorities else 0
        combined -= r.get("effort") or 0
        results.append({
            "id": r["id"], "name": r.get("name", ""), "status": r.get("status", "proposed"),
            "effort": r.get("effort"), "priorities": priorities, "combined_priority": combined,
        })
    if sort == "effort":
        results.sort(key=lambda x: -(x["effort"] or 0))
    else:
        results.sort(key=lambda x: -x["combined_priority"])
    e = sum(r.get("effort") or 0 for r in reqs)
    d = sum(r.get("effort") or 0 for r in reqs if r.get("status") in ("verified", "implemented", "deprecated"))
    return {"items": results, "total_effort": e, "completed_effort": d}


# ── Publishing ────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/publish")
async def publish_project(project_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    pub = Publisher(store, data.get("subsystems"))
    fmt = data.get("format", "html")
    sections = data.get("sections")

    if fmt == "html":
        return {"format": "html", "content": pub.build_html(sections)}
    elif fmt == "md":
        return {"format": "md", "content": pub.build_markdown()}
    elif fmt == "latex":
        return {"format": "latex", "content": pub.build_latex()}
    elif fmt in ("csv", "tsv"):
        from app.services.table_io import export_table
        return {"format": fmt, "content": export_table(store, fmt)}
    raise HTTPException(status_code=400, detail=f"Unknown format: {fmt} (use html, pdf, md, latex, csv, tsv, or xlsx)")


@router.get("/projects/{project_id}/publish/download")
async def download_report(project_id: str, format: str = "html", subsystems: str = ""):
    import os
    import tempfile

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    store = get_store(project_id)
    sub_list = [s.strip() for s in subsystems.split(",") if s.strip()] if subsystems else None
    pub = Publisher(store, sub_list)
    ext_map = {"html": "html", "pdf": "pdf", "md": "md", "latex": "tex", "reqif": "xml", "sysml": "sysml", "csv": "csv", "tsv": "tsv", "xlsx": "xlsx"}
    if format not in ext_map:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    ext = ext_map[format]

    fd, path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(fd)
    try:
        if format == "reqif":
            from app.services.reqif_export import export_reqif
            Path(path).write_text(export_reqif(store))
        elif format == "sysml":
            from app.services.sysml_export import export_sysml_v2
            Path(path).write_text(export_sysml_v2(store))
        elif format == "html":
            pub.to_html_file(path)
        elif format == "pdf":
            pub.to_pdf_file(path)
        elif format == "md":
            pub.to_markdown_file(path)
        elif format == "latex":
            pub.to_latex_file(path)
        elif format in ("csv", "tsv"):
            from app.services.table_io import export_table
            Path(path).write_text(export_table(store, format))
        elif format == "xlsx":
            from app.services.table_io import export_xlsx
            export_xlsx(store, path)
    except BaseException:
        os.unlink(path)
        raise

    project_name = store.read_meta().get("name", project_id)
    return FileResponse(
        path,
        filename=f"{project_name.replace(' ', '_')}_report.{ext}",
        media_type="application/octet-stream",
        # Remove the temp file once the response has been sent.
        background=BackgroundTask(os.unlink, path),
    )


# ══ Code & Test Traceability ═══════════════════════════════════════════════════


@router.post("/projects/{project_id}/scan")
async def scan_code(project_id: str, code_root: str = Form(""), user: dict = Depends(require_edit)):
    from app.services.code_scan import scan_tree, merge_references
    store = get_store(project_id)

    if code_root:
        root = Path(code_root).resolve()
        project_root = store.root.resolve()
        try:
            root.relative_to(project_root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"code_root must be inside the project directory: {project_root}",
            )
    else:
        root = store.root

    hits = scan_tree(root)
    summary = merge_references(store, hits)
    return summary


@router.get("/projects/{project_id}/references/freshness")
async def reference_freshness(project_id: str):
    from app.services.references import check_reference_freshness
    return check_reference_freshness(get_store(project_id), Path.cwd())


# ── Quality Analysis ──────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/quality")
async def quality_analysis(project_id: str):
    from app.services.quality import project_quality
    return project_quality(get_store(project_id))


# ── Parametric Evaluation ─────────────────────────────────────────────────────


@router.get("/projects/{project_id}/evaluation")
async def parametric_evaluation(project_id: str):
    """Evaluate every parameter, constraint and measurement in the project."""
    from app.services.evaluation import evaluate_project
    return evaluate_project(get_store(project_id))


# ── Validation ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/validate")
async def validate_project(project_id: str):
    store = get_store(project_id)
    checker = IntegrityChecker(store)
    return checker.check_all()


@router.get("/projects/{project_id}/suspect-links")
async def get_suspect_links(project_id: str):
    store = get_store(project_id)
    from app.services.fingerprint import check_suspect_links
    links = check_suspect_links(store)
    return {"links": links, "count": len(links)}


@router.post("/projects/{project_id}/suspect-links/clear")
async def clear_suspects(project_id: str, data: dict | None = None, user: dict = Depends(require_edit)):
    from app.services.fingerprint import review_all
    return {"ok": True, **review_all(get_store(project_id), user.get("username", ""))}


# ── Git Hooks ─────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/hooks/install")
async def install_git_hook(project_id: str, user: dict = Depends(require_edit)):
    try:
        path = install_hook(str(get_store(project_id).root))
        return {"installed": True, "path": path}
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No .git directory found. Run 'git init' first.")


@router.post("/projects/{project_id}/hooks/uninstall")
async def uninstall_git_hook(project_id: str, user: dict = Depends(require_edit)):
    uninstall_hook(str(get_store(project_id).root))
    return {"installed": False}


# ── Review Workflow ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/{req_id}/review")
async def submit_review(project_id: str, req_id: str, data: dict, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    before = dict(req)

    from app.services.fingerprint import review_item

    result = review_item(store, req_id, reviewer=user.get("username", ""), comment=data.get("comment", ""))
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    record_change(store, req_id, "review", before, result, user.get("username", ""))
    try:
        from app.services.email_service import notify_reviewed
        notify_reviewed(store, project_id, req_id, user.get("username", ""), data.get("comment", ""))
    except Exception:
        pass
    return result


@router.post("/projects/{project_id}/review-all")
async def review_all_endpoint(project_id: str, user: dict = Depends(require_edit)):
    from app.services.fingerprint import review_all
    return review_all(get_store(project_id), user.get("username", ""))


@router.get("/projects/{project_id}/unreviewed")
async def get_unreviewed(project_id: str):
    from app.services.fingerprint import check_unreviewed
    return {"items": check_unreviewed(get_store(project_id)), "count": None}


# ── Baselines (Enhanced) ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/baselines/{name}/freeze")
async def freeze_baseline(project_id: str, name: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(name, "baseline name")
    reqs = store.list_requirements()
    snapshot = {}
    for r in reqs:
        snapshot[r["id"]] = {
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "status": r.get("status", "proposed"),
            "priority": r.get("priority", "medium"),
            "type": r.get("type", "functional"),
            "parent": r.get("parent"),
            "relations": r.get("relations", []),
            "verification_cases": r.get("verification_cases", []),
            "rationale": r.get("rationale", ""),
            "source": r.get("source", ""),
            "allocated_to": r.get("allocated_to", ""),
        }
    data = {"name": name, "frozen_at": datetime.now(timezone.utc).isoformat(), "frozen": True, "snapshot": snapshot}
    store.write_item("baselines", name, data)
    for r in reqs:
        existing = list(r.get("baselines") or [])
        if name not in existing:
            existing.append(name)
            store.update_requirement(r["id"], {"baselines": existing})
    return {"name": name, "requirements": len(snapshot)}


@router.get("/projects/{project_id}/baselines/{name}/diff")
async def diff_baseline(project_id: str, name: str):
    store = get_store(project_id)
    baseline = store.get_item("baselines", name)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = baseline.get("snapshot", {})
    current = store.list_requirements()
    changes = []
    for r in current:
        if r["id"] in snapshot:
            snap = snapshot[r["id"]]
            diffs = {}
            for field in ["status", "priority", "name", "description"]:
                cur_val = r.get(field, "")
                snap_val = snap.get(field, "")
                if cur_val != snap_val:
                    diffs[field] = {"before": snap_val, "after": cur_val}
            if diffs:
                changes.append({"id": r["id"], "type": "modified", "diffs": diffs})
        else:
            changes.append({"id": r["id"], "type": "added"})
    for rid in snapshot:
        if not any(c["id"] == rid for c in changes):
            changes.append({"id": rid, "type": "removed"})
    return {"baseline": name, "frozen_at": baseline.get("frozen_at"), "changes": changes, "changed_count": len(changes)}


# ── Import (ReqIF / SysML) ────────────────────────────────────────────────────

@router.post("/projects/{project_id}/import")
async def import_project(
    project_id: str,
    file: UploadFile = File(...),
    format: str = Form("auto"),
    mode: str = Form("merge"),
    user: dict = Depends(require_edit),
):
    """Import requirements from a ReqIF 1.2 or SysML v2 file.

    ``format`` is ``auto`` (sniff from content), ``reqif`` or ``sysml``.
    ``mode`` is ``merge`` (create/update) or ``replace`` (wipe existing first).
    """
    store = get_store(project_id)
    if format not in ("auto", "reqif", "sysml", "csv", "tsv", "xlsx"):
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    content = await _read_upload_capped(file, settings.max_upload_size_mb)
    from app.services.table_io import import_table as table_import

    if format in ("csv", "tsv"):
        summary = table_import(store, content.decode("utf-8", errors="replace"), fmt=format, mode=mode)
        return summary

    if format == "xlsx":
        from app.services.table_io import import_xlsx
        return import_xlsx(store, content, mode=mode)

    from app.services.importer import parse_and_import
    from app.services.reqif_import import ReqIFParseError
    from app.services.sysml_import import SysMLParseError

    try:
        summary = parse_and_import(store, content, fmt=format, mode=mode)
    except (ReqIFParseError, SysMLParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc
    return summary


# ── SSE Change Notifications ──────────────────────────────────────────────────

import asyncio
import json
from fastapi.responses import StreamingResponse


@router.get("/projects/{project_id}/presence")
async def project_presence(project_id: str):
    """Return the users currently viewing the project (real-time roster)."""
    from app.services.event_bus import get_event_bus

    users = get_event_bus().roster(project_id)
    return {"users": users, "count": len({u["username"] for u in users})}


@router.get("/projects/{project_id}/events")
async def project_events(project_id: str, user: dict = Depends(get_current_user)):
    """Server-Sent Events stream for real-time collaboration."""
    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)
    client_id = uuid.uuid4().hex
    username = user.get("username", "guest")
    role = user.get("role", "viewer")

    async def event_stream():
        try:
            # Send an initial heartbeat so the client knows the connection is alive.
            yield "event: connected\ndata: {}\n\n"
            # Register presence (this broadcasts a presence event to everyone).
            bus.join(project_id, client_id, username, role)
            # Seed this client with the current roster immediately.
            yield f"event: presence\ndata: {json.dumps({'type': 'presence', 'users': bus.roster(project_id)})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    channel = "presence" if event.get("type") == "presence" else "change"
                    yield f"event: {channel}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bus.leave(project_id, client_id)
            bus.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
