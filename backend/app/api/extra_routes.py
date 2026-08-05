"""Change requests, risks, comments, decisions, history, git operations,
validation, hooks, review workflow, baselines, and import endpoints.

Large sections (bulk ops, analysis/metrics, publishing, collaboration)
were moved to sibling modules. This file holds the remaining entity CRUD
and project lifecycle endpoints.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_store, require_edit, require_maintain, require_admin
from app.core.rate_limit import rate_limit
from app.core.ids import safe_id
from app.api.router import normalize_baseline_defs
from app.api._utils import sorted_by_modified, read_upload_capped, paginate
from app.models.change_request import ChangeRequestCreate, ChangeRequestUpdate
from app.services.change_requests import redline as compute_redline
from app.models.risk import RiskCreate, RiskUpdate, CommentCreate, DecisionRecordCreate, DecisionRecordUpdate
from app.services.history import record_change
from app.services.delete_guard import check_deletable
from app.services.integrity import IntegrityChecker, clear_suspect_links
from app.services.git_hooks import install_hook, uninstall_hook

logger = logging.getLogger(__name__)


class CommentUpdate(BaseModel):
    resolved: Optional[bool] = None
    text: Optional[str] = None


class ReviewRequest(BaseModel):
    comment: str = ""


router = APIRouter()


# ── Change Requests ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/change-requests")
def list_change_requests(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    items = sorted_by_modified(get_store(project_id).list_items("change_requests"))
    return paginate(items, offset, limit)


@router.post("/projects/{project_id}/change-requests", status_code=201)
def create_change_request(project_id: str, data: ChangeRequestCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    cr = data.model_dump(mode="json")
    cr.setdefault("status", "submitted")
    cr.setdefault("submitted_by", user.get("username", ""))
    cr.setdefault("reviewed_by", "")
    cr.setdefault("approved_by", "")
    result = store.create_item("change_requests", cr)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    from app.services.email_service import notify_change_request, _safe_notify
    _safe_notify(notify_change_request, store, project_id, result["id"], "created", user.get("username", ""))
    return result


@router.put("/projects/{project_id}/change-requests/{cr_id}")
def update_change_request(project_id: str, cr_id: str, data: ChangeRequestUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("change_requests", cr_id)
    result = store.update_item("change_requests", cr_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    record_change(store, cr_id, "update", before, result, user.get("username", ""))
    from app.services.email_service import notify_change_request, _safe_notify
    _safe_notify(notify_change_request, store, project_id, cr_id, "updated", user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/change-requests/{cr_id}")
def delete_change_request(project_id: str, cr_id: str, force: bool = False, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    check_deletable(store, "change_requests", cr_id, force)
    before = store.get_item("change_requests", cr_id)
    if not store.delete_item("change_requests", cr_id):
        raise HTTPException(status_code=404, detail="Change request not found")
    record_change(store, cr_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


@router.get("/projects/{project_id}/change-requests/{cr_id}/redline")
def get_cr_redline(
    project_id: str,
    cr_id: str,
    _rate: None = Depends(rate_limit(20, 60)),
):
    store = get_store(project_id)
    cr = store.get_item("change_requests", cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return compute_redline(store, cr)


@router.post("/projects/{project_id}/change-requests/{cr_id}/execute")
def execute_change_request(
    project_id: str,
    cr_id: str,
    user: dict = Depends(require_maintain),
):
    store = get_store(project_id)
    cr = store.get_item("change_requests", cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")

    changes = cr.get("changes", {})
    if not changes:
        raise HTTPException(status_code=400, detail="Change request proposes no changes")

    # 1. Compute redline; refuse if stale.
    rl = compute_redline(store, cr)
    if rl["blocked"]:
        stale_ids = [t["id"] for t in rl["targets"] if t["stale"]]
        raise HTTPException(
            status_code=409,
            detail=f"Change request is stale: {', '.join(stale_ids)} changed since it was raised",
        )

    # 2. Apply each target's proposal.
    updated_count = 0
    for target in rl["targets"]:
        target_id = target["id"]
        proposed = changes.get(target_id, {})
        if not proposed:
            continue
        before = store.get_requirement(target_id)
        if before is None:
            continue
        result = store.update_requirement(target_id, proposed)
        if result is not None:
            updated_count += 1
            from app.services.history import record_change as rc
            rc(store, target_id, "update", before, result, user.get("username", ""))

    # 3. Mark the request as implemented.
    from app.services.history import record_change as rc
    before_cr = dict(cr)
    updated_cr = store.update_item("change_requests", cr_id, {
        "status": "implemented",
        "approved_by": user.get("username", ""),
    })
    rc(store, cr_id, "update", before_cr, updated_cr, user.get("username", ""))

    return {"id": cr_id, "status": "implemented", "updated": updated_count}


@router.post("/projects/{project_id}/change-requests/{cr_id}/reject")
def reject_change_request(
    project_id: str,
    cr_id: str,
    user: dict = Depends(require_maintain),
):
    store = get_store(project_id)
    cr = store.get_item("change_requests", cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")

    from app.services.history import record_change as rc
    before = dict(cr)
    result = store.update_item("change_requests", cr_id, {
        "status": "rejected",
        "reviewed_by": user.get("username", ""),
    })
    rc(store, cr_id, "update", before, result, user.get("username", ""))

    return {"id": cr_id, "status": "rejected"}


@router.get("/projects/{project_id}/requirements/{req_id}/fingerprint")
def get_requirement_fingerprint(project_id: str, req_id: str):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    from app.services.fingerprint import compute_fingerprint
    return {"id": req_id, "fingerprint": compute_fingerprint(req)}


# ── Risks ─────────────────────────────────────────────────────────────────────

def _rated(store, risks: list[dict]) -> list[dict]:
    """Attach the derived rating. Computed on read so that re-tuning the matrix
    re-rates the whole register at once instead of leaving stored ratings that
    disagree with the matrix they came from."""
    from app.services.risk_matrix import apply_rating
    return apply_rating(risks, store.read_meta().get("risk_matrix"))


@router.get("/projects/{project_id}/risk-matrix")
def get_risk_matrix(project_id: str):
    from app.services.risk_matrix import normalize_matrix
    return normalize_matrix(get_store(project_id).read_meta().get("risk_matrix"))


@router.get("/projects/{project_id}/risks")
def list_risks(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    store = get_store(project_id)
    items = _rated(store, sorted_by_modified(store.list_items("risks")))
    return paginate(items, offset, limit)


@router.post("/projects/{project_id}/risks", status_code=201)
def create_risk(project_id: str, data: RiskCreate, user: dict = Depends(require_edit)):
    r = data.model_dump(mode="json")
    r.setdefault("impact", "")
    r.setdefault("mitigation", "")
    r.setdefault("linked_requirements", [])
    r.setdefault("status", "open")
    store = get_store(project_id)
    result = store.create_item("risks", r)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    _rated(store, [result])
    from app.services.email_service import notify_risk, _safe_notify
    _safe_notify(notify_risk, store, project_id, result["id"], "created", user.get("username", ""))
    return result


@router.put("/projects/{project_id}/risks/{risk_id}")
def update_risk(project_id: str, risk_id: str, data: RiskUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("risks", risk_id)
    result = store.update_item("risks", risk_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    record_change(store, risk_id, "update", before, result, user.get("username", ""))
    _rated(store, [result])
    from app.services.email_service import notify_risk, _safe_notify
    _safe_notify(notify_risk, store, project_id, risk_id, "updated", user.get("username", ""))
    return result


@router.delete("/projects/{project_id}/risks/{risk_id}")
def delete_risk(project_id: str, risk_id: str, force: bool = False, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    check_deletable(store, "risks", risk_id, force)
    before = store.get_item("risks", risk_id)
    if not store.delete_item("risks", risk_id):
        raise HTTPException(status_code=404, detail="Risk not found")
    record_change(store, risk_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Comments ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/comments")
def list_comments(
    project_id: str,
    requirement_id: Optional[str] = Query(None),
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    comments = get_store(project_id).list_items("comments")
    if requirement_id:
        comments = [c for c in comments if c.get("requirement_id") == requirement_id]
    comments = sorted_by_modified(comments, key="created")
    if offset is None and limit is None:
        return comments
    off = offset or 0
    lim = limit or 500
    total = len(comments)
    return {"items": comments[off:off + lim], "total": total, "offset": off, "limit": lim}


@router.post("/projects/{project_id}/comments", status_code=201)
def create_comment(project_id: str, data: CommentCreate, user: dict = Depends(require_edit)):
    c = data.model_dump(mode="json")
    c["id"] = f"COMMENT-{uuid.uuid4().hex[:8].upper()}"
    c["resolved"] = False
    c.setdefault("author", user.get("username", ""))
    store = get_store(project_id)
    result = store.create_item("comments", c)
    from app.services.email_service import notify_comment, _safe_notify
    _safe_notify(notify_comment, store, project_id, data.requirement_id, user.get("username", ""), data.text)
    return result


@router.delete("/projects/{project_id}/comments/{comment_id}")
def delete_comment(project_id: str, comment_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("comments", comment_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.patch("/projects/{project_id}/comments/{comment_id}")
def update_comment(project_id: str, comment_id: str, data: CommentUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    existing = store.get_item("comments", comment_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    updates = {}
    if data.resolved is not None:
        updates["resolved"] = bool(data.resolved)
    if data.text is not None:
        updates["text"] = str(data.text)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = store.update_item("comments", comment_id, updates)
    return result


# ── Decision Records ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/decisions")
def list_decisions(
    project_id: str,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    items = sorted_by_modified(get_store(project_id).list_items("decisions"))
    return paginate(items, offset, limit)


@router.post("/projects/{project_id}/decisions", status_code=201)
def create_decision(project_id: str, data: DecisionRecordCreate, user: dict = Depends(require_edit)):
    d = data.model_dump(mode="json")
    d.setdefault("rationale", "")
    d.setdefault("consequences", "")
    d.setdefault("linked_requirements", [])
    d.setdefault("status", "accepted")
    d.setdefault("decided_by", user.get("username", ""))
    store = get_store(project_id)
    result = store.create_item("decisions", d)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    from app.services.email_service import notify_decision, _safe_notify
    _safe_notify(notify_decision, store, project_id, result["id"], "created", user.get("username", ""))
    return result


@router.put("/projects/{project_id}/decisions/{dec_id}")
def update_decision(project_id: str, dec_id: str, data: DecisionRecordUpdate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("decisions", dec_id)
    result = store.update_item("decisions", dec_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    record_change(store, dec_id, "update", before, result, user.get("username", ""))
    from app.services.email_service import notify_decision, _safe_notify
    _safe_notify(notify_decision, store, project_id, dec_id, "updated", user.get("username", ""))
    return result
    return result


@router.delete("/projects/{project_id}/decisions/{dec_id}")
def delete_decision(project_id: str, dec_id: str, force: bool = False, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    check_deletable(store, "decisions", dec_id, force)
    before = store.get_item("decisions", dec_id)
    if not store.delete_item("decisions", dec_id):
        raise HTTPException(status_code=404, detail="Decision not found")
    record_change(store, dec_id, "delete", before, None, user.get("username", ""))
    return {"ok": True}


# ── Version History ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/history")
def requirement_history(project_id: str, req_id: str):
    return get_store(project_id).list_history(req_id)[:50]


@router.get("/projects/{project_id}/history/{item_id}")
def item_history(project_id: str, item_id: str):
    return get_store(project_id).list_history(item_id)[:50]


# ── Git Log ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/git/log")
def git_log(project_id: str, limit: int = Query(50, ge=1, le=500)):
    from app.services import git_service

    store = get_store(project_id)
    return {
        "is_repo": git_service.is_repo(store.root),
        "commits": git_service.log(store.root, limit),
    }


@router.post("/projects/{project_id}/git/restore")
def git_restore(project_id: str, data: dict, user: dict = Depends(require_maintain)):
    from app.services import git_service

    commit_hash = data.get("hash", "").strip()
    if not commit_hash:
        raise HTTPException(status_code=400, detail="hash is required")

    store = get_store(project_id)
    if not git_service.is_repo(store.root):
        raise HTTPException(status_code=400, detail="project is not a git repository")

    if not git_service.restore_commit(store.root, commit_hash, user.get("username", "")):
        raise HTTPException(status_code=500, detail="restore failed — check server logs")

    if settings.git_push_on_commit:
        git_service.push_to_remote(store.root)

    return {"status": "ok", "message": f"Restored to {commit_hash[:8]}"}


@router.post("/projects/{project_id}/git/test-remote")
def git_test_remote(project_id: str, data: dict, user: dict = Depends(require_admin)):
    """Check that a candidate remote is reachable before it is saved.

    Admin-only, matching `router._guard_git_settings`: this makes the server
    perform a network (or filesystem) operation against a caller-supplied URL,
    which is the same authority as setting the remote and belongs behind the
    same gate. The URL is validated against the shared scheme allowlist here
    *and* inside `git_service.test_remote`.
    """
    from app.services import git_service

    remote_url = str(data.get("remote_url", "")).strip()
    if not remote_url:
        raise HTTPException(status_code=400, detail="remote_url is required")
    if not git_service.is_allowed_remote(remote_url):
        raise HTTPException(status_code=400, detail=git_service.REMOTE_SCHEME_ERROR)

    store = get_store(project_id)
    return git_service.test_remote(store.root, remote_url)


# ── Validation ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/validate")
def validate_project(project_id: str, _rate: None = Depends(rate_limit(20, 60))):
    store = get_store(project_id)
    checker = IntegrityChecker(store)
    return checker.check_all()


@router.get("/projects/{project_id}/suspect-links")
def get_suspect_links(project_id: str):
    store = get_store(project_id)
    from app.services.fingerprint import check_suspect_links
    links = check_suspect_links(store)
    return {"links": links, "count": len(links)}


@router.post("/projects/{project_id}/suspect-links/clear")
def clear_suspects(project_id: str, data: dict | None = None, user: dict = Depends(require_maintain)):
    from app.services.fingerprint import review_all
    return {"ok": True, **review_all(get_store(project_id), user.get("username", ""))}


# ── Git Hooks ─────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/hooks/install")
def install_git_hook(project_id: str, user: dict = Depends(require_maintain)):
    try:
        path = install_hook(str(get_store(project_id).root))
        return {"installed": True, "path": path}
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No .git directory found. Run 'git init' first.")


@router.post("/projects/{project_id}/hooks/uninstall")
def uninstall_git_hook(project_id: str, user: dict = Depends(require_maintain)):
    uninstall_hook(str(get_store(project_id).root))
    return {"installed": False}


# ── Review Workflow ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/requirements/{req_id}/review")
def submit_review(project_id: str, req_id: str, data: ReviewRequest, user: dict = Depends(require_maintain)):
    store = get_store(project_id)
    req = store.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    before = dict(req)

    from app.services.fingerprint import review_item

    result = review_item(store, req_id, reviewer=user.get("username", ""), comment=data.comment)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    record_change(store, req_id, "review", before, result, user.get("username", ""))
    from app.services.email_service import notify_reviewed, _safe_notify
    _safe_notify(notify_reviewed, store, project_id, req_id, user.get("username", ""), data.comment)
    return result


@router.post("/projects/{project_id}/review-all")
def review_all_endpoint(project_id: str, user: dict = Depends(require_maintain)):
    from app.services.fingerprint import review_all
    return review_all(get_store(project_id), user.get("username", ""))


@router.get("/projects/{project_id}/unreviewed")
def get_unreviewed(project_id: str):
    from app.services.fingerprint import check_unreviewed
    return {"items": check_unreviewed(get_store(project_id)), "count": None}


# ── Baselines (Enhanced) ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/baselines/{name}/freeze")
def freeze_baseline(project_id: str, name: str, user: dict = Depends(require_maintain)):
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
    meta = store.read_meta()
    defs = normalize_baseline_defs(meta.get("baselines", []))
    sym, desc = "", ""
    for d in defs:
        if d["name"] == name:
            sym, desc = d["symbol"], d["description"]
            break
    data = {"name": name, "symbol": sym, "description": desc,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "frozen": True, "snapshot": snapshot}
    store.write_item("baselines", name, data)
    for r in reqs:
        existing = list(r.get("baselines") or [])
        if name not in existing:
            existing.append(name)
            store.update_requirement(r["id"], {"baselines": existing})
    return {"name": name, "symbol": sym, "description": desc, "requirements": len(snapshot)}


@router.get("/projects/{project_id}/baselines/{name}/diff")
def diff_baseline(project_id: str, name: str):
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
    return {"baseline": name, "symbol": baseline.get("symbol", ""),
            "description": baseline.get("description", ""),
            "frozen_at": baseline.get("frozen_at"), "changes": changes,
            "changed_count": len(changes)}


# ── Import (ReqIF / SysML / CSV / TSV / XLSX) ────────────────────────────────

@router.post("/projects/{project_id}/import")
def import_project(
    project_id: str,
    file: UploadFile = File(...),
    format: str = Form("auto"),
    mode: str = Form("merge"),
    user: dict = Depends(require_maintain),
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

    content = read_upload_capped(file, settings.max_upload_size_mb)
    from app.services.table_io import import_table as table_import

    if format in ("csv", "tsv"):
        try:
            return table_import(store, content.decode("utf-8", errors="replace"),
                                fmt=format, mode=mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    if format == "xlsx":
        from app.services.table_io import import_xlsx
        try:
            return import_xlsx(store, content, mode=mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    from app.services.importer import parse_and_import
    from app.services.reqif_import import ReqIFParseError
    from app.services.sysml_import import SysMLParseError

    try:
        summary = parse_and_import(store, content, fmt=format, mode=mode)
    except (ReqIFParseError, SysMLParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc
    return summary
