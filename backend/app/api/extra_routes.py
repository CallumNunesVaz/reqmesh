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
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import settings
from app.core.dependencies import get_store, require_edit, require_maintain, require_admin
from app.core.rate_limit import rate_limit
from app.core.ids import safe_id
from app.services.meta_defs import normalize_baseline_defs
from app.api._utils import sorted_by_modified, read_upload_capped, paginate, check_precondition, enforce_naming
from app.models.change_request import ChangeRequestCreate, ChangeRequestUpdate
from app.models.requirement import RequirementCreate, RequirementUpdate
from app.services.change_requests import redline as compute_redline
from app.models.risk import RiskCreate, RiskUpdate, CommentCreate, DecisionRecordCreate, DecisionRecordUpdate
from app.services.errors import error_envelope
from app.services.history import record_change
from app.services.delete_guard import check_deletable
from app.services.integrity import IntegrityChecker
from app.services.git_hooks import install_hook, uninstall_hook
from app.services.link_validation import first_missing

logger = logging.getLogger(__name__)


class CommentUpdate(BaseModel):
    resolved: Optional[bool] = None
    text: Optional[str] = None


class _StrictRequirementUpdate(RequirementUpdate):
    """`RequirementUpdate` with unknown keys forbidden.

    Used only when executing a change request, where a proposed patch must be
    validated before it is merged. `RequirementUpdate` itself stays permissive
    on the normal requirement PUT path — tightening that is out of scope here.
    """
    model_config = ConfigDict(extra="forbid")


class ReviewRequest(BaseModel):
    comment: str = ""


class GitRestoreRequest(BaseModel):
    hash: str = ""


class GitTestRemoteRequest(BaseModel):
    remote_url: str = ""


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


@router.get("/projects/{project_id}/change-requests/{cr_id}")
def get_change_request(project_id: str, cr_id: str):
    store = get_store(project_id)
    cr = store.get_item("change_requests", cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return cr


@router.post("/projects/{project_id}/change-requests", status_code=201)
def create_change_request(project_id: str, data: ChangeRequestCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(data.id, "change request id")
    enforce_naming(store, "change_requests", data.id)
    if store.get_item("change_requests", data.id):
        raise HTTPException(status_code=409, detail="Change request already exists")
    reason = first_missing(store, [("requirements", data.affected_requirements)],
                           allowed=set(data.creates))
    if reason:
        raise HTTPException(status_code=400, detail=reason)
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
def update_change_request(project_id: str, cr_id: str, data: ChangeRequestUpdate,
                          request: Request, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("change_requests", cr_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    check_precondition(request, before)
    reason = first_missing(store, [("requirements", data.affected_requirements)],
                           allowed=set(data.creates or []))
    if reason:
        raise HTTPException(status_code=400, detail=reason)
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


@router.get("/projects/{project_id}/change-requests/{cr_id}/redline", summary="Change request redline")
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
    #: Ids this execution brought into existence, in redline order. The caller
    #: needs them to focus the new requirement afterwards, and cannot derive
    #: them from `cr["creates"]` — that lists what was *proposed*, including
    #: entries with no proposal body, which are skipped below.
    created_ids: list[str] = []
    for target in rl["targets"]:
        target_id = target["id"]
        proposed = changes.get(target_id, {})
        if not proposed:
            continue

        # Validate the proposal before merging it into a requirement. Unknown
        # keys and wrong-typed values are rejected here rather than silently
        # dropped (a silent drop would "succeed" while writing nothing the
        # caller asked for).
        try:
            _StrictRequirementUpdate.model_validate(proposed)
        except ValidationError as exc:
            errors = exc.errors()
            raise HTTPException(
                status_code=400,
                detail=error_envelope(
                    "invalid_change",
                    f"{target_id}: {errors[0]['msg']}",
                    requirement_id=target_id,
                    errors=errors,
                ),
            ) from exc

        if target.get("creates"):
            safe_id(target_id)
            # Go through the same model and defaults as POST /requirements. A
            # change request proposes only the fields it cares about, so writing
            # `proposed` straight out produced a requirement with no type, no
            # priority and no status — one the UI could not render.
            try:
                new_req = RequirementCreate(**{**proposed, "id": target_id}).model_dump(mode="json")
            except ValidationError as exc:
                raise HTTPException(status_code=400, detail=f"{target_id}: {exc.errors()[0]['msg']}") from exc
            new_req.setdefault("attributes", [])
            new_req.setdefault("relations", [])
            new_req.setdefault("verification_cases", [])
            new_req.setdefault("verification_status", "pending")
            result = store.create_requirement(new_req)
            record_change(store, target_id, "create", None, result, user.get("username", ""))
            updated_count += 1
            created_ids.append(target_id)
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

    return {"id": cr_id, "status": "implemented", "updated": updated_count, "created": created_ids}


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


@router.get("/projects/{project_id}/risks/{risk_id}")
def get_risk(project_id: str, risk_id: str):
    store = get_store(project_id)
    risk = store.get_item("risks", risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    return _rated(store, [risk])[0]


@router.post("/projects/{project_id}/risks", status_code=201)
def create_risk(project_id: str, data: RiskCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(data.id, "risk id")
    enforce_naming(store, "risks", data.id)
    if store.get_item("risks", data.id):
        raise HTTPException(status_code=409, detail="Risk already exists")
    r = data.model_dump(mode="json")
    r.setdefault("impact", "")
    r.setdefault("mitigation", "")
    r.setdefault("linked_requirements", [])
    r.setdefault("status", "open")
    result = store.create_item("risks", r)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    _rated(store, [result])
    from app.services.email_service import notify_risk, _safe_notify
    _safe_notify(notify_risk, store, project_id, result["id"], "created", user.get("username", ""))
    return result


@router.put("/projects/{project_id}/risks/{risk_id}")
def update_risk(project_id: str, risk_id: str, data: RiskUpdate,
                request: Request, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("risks", risk_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    check_precondition(request, before)
    reason = first_missing(store, [("requirements", data.linked_requirements)])
    if reason:
        raise HTTPException(status_code=400, detail=reason)
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
    entity_kind: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=2000),
):
    if entity_id and not entity_kind:
        raise HTTPException(status_code=400, detail="entity_kind is required when filtering by entity_id")
    comments = get_store(project_id).list_items("comments")
    if entity_kind:
        comments = [c for c in comments if c.get("entity_kind") == entity_kind]
    if entity_id:
        comments = [c for c in comments if c.get("entity_id") == entity_id]
    comments = sorted_by_modified(comments, key="created")
    return paginate(comments, offset, limit)


@router.post("/projects/{project_id}/comments", status_code=201)
def create_comment(project_id: str, data: CommentCreate, user: dict = Depends(require_edit)):
    c = data.model_dump(mode="json")
    c["id"] = f"COMMENT-{uuid.uuid4().hex[:8].upper()}"
    c["resolved"] = False
    c["author"] = user.get("username", "")
    store = get_store(project_id)
    result = store.create_item("comments", c)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    from app.services.email_service import notify_comment, _safe_notify
    _safe_notify(notify_comment, store, project_id, c["entity_kind"], c["entity_id"], user.get("username", ""), c["text"])
    return result


@router.delete("/projects/{project_id}/comments/{comment_id}")
def delete_comment(project_id: str, comment_id: str, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("comments", comment_id)
    if not store.delete_item("comments", comment_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    record_change(store, comment_id, "delete", before, None, user.get("username", ""))
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
    record_change(store, comment_id, "update", existing, result, user.get("username", ""))
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


@router.get("/projects/{project_id}/decisions/{dec_id}")
def get_decision(project_id: str, dec_id: str):
    store = get_store(project_id)
    decision = store.get_item("decisions", dec_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision


@router.post("/projects/{project_id}/decisions", status_code=201)
def create_decision(project_id: str, data: DecisionRecordCreate, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    safe_id(data.id, "decision id")
    if store.get_item("decisions", data.id):
        raise HTTPException(status_code=409, detail="Decision already exists")
    reason = first_missing(store, [("requirements", data.linked_requirements)])
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    d = data.model_dump(mode="json")
    d.setdefault("rationale", "")
    d.setdefault("consequences", "")
    d.setdefault("linked_requirements", [])
    d.setdefault("status", "accepted")
    d.setdefault("decided_by", user.get("username", ""))
    result = store.create_item("decisions", d)
    record_change(store, result["id"], "create", None, result, user.get("username", ""))
    from app.services.email_service import notify_decision, _safe_notify
    _safe_notify(notify_decision, store, project_id, result["id"], "created", user.get("username", ""))
    return result


@router.put("/projects/{project_id}/decisions/{dec_id}")
def update_decision(project_id: str, dec_id: str, data: DecisionRecordUpdate,
                    request: Request, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    before = store.get_item("decisions", dec_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    check_precondition(request, before)
    reason = first_missing(store, [("requirements", data.linked_requirements)])
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    result = store.update_item("decisions", dec_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    record_change(store, dec_id, "update", before, result, user.get("username", ""))
    from app.services.email_service import notify_decision, _safe_notify
    _safe_notify(notify_decision, store, project_id, dec_id, "updated", user.get("username", ""))
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

@router.get("/projects/{project_id}/history/{item_id}")
def item_history(project_id: str, item_id: str):
    return get_store(project_id).list_history(item_id)[:50]


# ── Activity (aggregated audit graph) ─────────────────────────────────────────

@router.get("/projects/{project_id}/activity")
def activity(
    project_id: str,
    since: str = Query(""),
    until: str = Query(""),
    bucket: str = Query("day"),
):
    """Aggregated audit activity bucketed by date and entity kind.

    Counts **distinct item ids** per bucket per kind, not raw audit entries.
    A bulk status change writes N entries in one action and would otherwise
    spike a single day into the darkest bucket and dwarf every real day beside
    it.
    """
    from collections import defaultdict
    from datetime import date, datetime, timedelta, timezone

    from app.services.entity_kinds import resolve_entity_label, KIND_LABEL_TO_KEY

    if bucket not in ("day", "week"):
        raise HTTPException(status_code=400, detail="bucket must be 'day' or 'week'")

    # A date the caller typed wrong is a 400. `date.fromisoformat` raises
    # ValueError, which FastAPI does not translate, so `?since=0` came back as a
    # 500 with a stack trace in the log.
    def _as_date(value: str, field: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"{field} must be an ISO date (YYYY-MM-DD)"
            ) from None

    today = datetime.now(timezone.utc).date()
    until_dt = _as_date(until, "until") if until else today

    if since:
        since_dt = _as_date(since, "since")
    else:
        since_dt = until_dt - timedelta(days=90)

    # Cap the look-back window at 365 days.
    max_since = until_dt - timedelta(days=365)
    if since_dt < max_since:
        since_dt = max_since

    since_iso = since_dt.isoformat()
    until_iso = until_dt.isoformat()

    store = get_store(project_id)
    raw = store.list_all_history(since_iso, until_iso)

    # Stream-bucket: one pass over the history, one dict per bucket day.
    # days_in_range is computed *after* clamping every date to the window so
    # we never return a zero-day that falls outside the clamped period.
    days_in_range = (until_dt - since_dt).days + 1
    # seed every date in the range with an empty set per kind
    bucket_data: dict[str, dict[str, set[str]]] = {}
    for i in range(days_in_range):
        d = since_dt + timedelta(days=i)
        if bucket == "week":
            # ISO week: Monday of the week containing *d*.
            key = (d - timedelta(days=d.weekday())).isoformat()
        else:
            key = d.isoformat()
        if key not in bucket_data:
            bucket_data[key] = defaultdict(set)

    for entry in raw:
        item_id = str(entry.get("item_id", ""))
        ts = str(entry.get("timestamp", ""))
        if not item_id or not ts:
            continue

        try:
            entry_date = date.fromisoformat(ts[:10])
        except (ValueError, TypeError):
            continue

        # Skip entries outside the clamped window (list_all_history bounding
        # is `>=` / `<=` on string timestamps; epsilon is safe here).
        if entry_date < since_dt or entry_date > until_dt:
            continue

        if bucket == "week":
            key = (entry_date - timedelta(days=entry_date.weekday())).isoformat()
        else:
            key = entry_date.isoformat()

        kind_label, _name = resolve_entity_label(store, item_id)
        kind_key = KIND_LABEL_TO_KEY.get(kind_label, "item")
        bucket_data[key][kind_key].add(item_id)

    # Assemble the ordered list of buckets.  Kinds with a nonzero total are
    # tracked so the legend only shows what actually exists.
    all_kind_keys = ["verification", "change", "specification", "requirement",
                     "component", "decision", "risk"]

    buckets_out = []
    for i in range(days_in_range):
        d = since_dt + timedelta(days=i)
        if bucket == "week":
            key = (d - timedelta(days=d.weekday())).isoformat()
        else:
            key = d.isoformat()

        bd = bucket_data.get(key, {})
        b = {"date": key, **{k: len(bd.get(k, set())) for k in all_kind_keys}}
        buckets_out.append(b)

    # Deduplicate consecutive week keys (the loop produces the same key for Mon–Sun).
    if bucket == "week":
        seen: set[str] = set()
        deduped = []
        for b in buckets_out:
            if b["date"] not in seen:
                seen.add(b["date"])
                deduped.append(b)
        buckets_out = deduped

    # Compute totals from the final (deduplicated) buckets, not the per-day
    # loop, so a week's activity is not summed once per weekday in the range.
    kind_totals: dict[str, int] = {k: 0 for k in all_kind_keys}
    total = 0
    for b in buckets_out:
        for k in all_kind_keys:
            n = b[k]
            kind_totals[k] += n
            total += n

    kinds = [k for k in all_kind_keys if kind_totals[k] > 0]

    return {
        "buckets": buckets_out,
        "kinds": kinds,
        "total": total,
        "since": since_iso,
        "until": until_iso,
        "bucket": bucket,
    }


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
def git_restore(project_id: str, data: GitRestoreRequest, user: dict = Depends(require_maintain)):
    from app.services import git_service

    commit_hash = data.hash.strip()
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
def git_test_remote(project_id: str, data: GitTestRemoteRequest, user: dict = Depends(require_admin)):
    """Check that a candidate remote is reachable before it is saved.

    Admin-only, matching `router._guard_git_settings`: this makes the server
    perform a network (or filesystem) operation against a caller-supplied URL,
    which is the same authority as setting the remote and belongs behind the
    same gate. The URL is validated against the shared scheme allowlist here
    *and* inside ``git_service.test_remote``.
    """
    from app.services import git_service

    remote_url = data.remote_url.strip()
    if not remote_url:
        raise HTTPException(status_code=400, detail="remote_url is required")
    if not git_service.is_allowed_remote(remote_url):
        raise HTTPException(status_code=400, detail=git_service.REMOTE_SCHEME_ERROR)

    store = get_store(project_id)
    return git_service.test_remote(store.root, remote_url)


@router.get("/projects/{project_id}/git/status")
def git_status(project_id: str, user: dict = Depends(require_maintain)):
    """Return the git repository status for a project.

    Performs no network access — ``ahead`` is computed against the local
    remote-tracking ref so the call never hangs when the remote is unreachable.
    ``remote_url`` is redacted before it leaves the server.
    """
    from app.services import git_service

    store = get_store(project_id)
    return git_service.get_status(store.root)


@router.post("/projects/{project_id}/git/init", status_code=201)
def git_init(project_id: str, user: dict = Depends(require_maintain)):
    """Initialise a git repository in the project directory.

    Returns 409 if the project is already a repository.  Safe to call — the
    service layer also checks for a parent repo and refuses to nest.
    """
    from app.services import git_service

    store = get_store(project_id)
    if git_service.is_repo(store.root):
        raise HTTPException(status_code=409, detail="Project is already a git repository")
    if not git_service.init_repo(store.root, user.get("username", "")):
        raise HTTPException(status_code=500, detail="Failed to initialise repository — check server logs")
    return {"initialised": True}


@router.post("/projects/{project_id}/git/push")
def git_push(project_id: str, user: dict = Depends(require_maintain)):
    """Push commits to the configured remote synchronously.

    Returns the real outcome, including the redacted error on failure.
    Unlike ``schedule_push``, which runs from a background timer and logs
    to a file nobody reads, this route makes a broken remote immediately
    diagnosable.
    """
    from app.services import git_service

    store = get_store(project_id)
    ok = git_service.push_to_remote(store.root)
    outcome = git_service._push_outcomes.get(store.root.resolve(), {})

    if not ok:
        error = outcome.get("error", "Push failed — check server logs")
        logger.warning("Manual push failed for %s: %s", project_id, error)
        raise HTTPException(status_code=502, detail=error)

    return {"ok": True, "error": None}


@router.delete("/projects/{project_id}/git/remote")
def git_delete_remote(project_id: str, user: dict = Depends(require_admin)):
    """Remove the git remote *and* clear ``remote_url`` from project settings.

    Admin-only: changing where a project ships its history is the same
    authority as setting it, and removing a remote is a one-way operation
    that stops the project from being backed up.
    """
    from app.services import git_service

    store = get_store(project_id)
    git_service.delete_remote(store.root)
    return {"ok": True}


# ── Git deploy keys ───────────────────────────────────────────────────────────

def _git_key_info(project_id: str) -> dict | None:
    from app.services import git_keys

    store = get_store(project_id)
    return git_keys.get_info(store.root)


@router.get("/projects/{project_id}/git/key")
def git_get_key(project_id: str, user: dict = Depends(require_admin)):
    """The project's deploy key's public half and fingerprint, or 404.

    Admin-only, matching the other admin git routes. The private key is never
    returned — under any role, ever — because the moment such an endpoint
    exists it is one authorisation bug away from being reachable.
    """
    info = _git_key_info(project_id)
    if info is None:
        raise HTTPException(status_code=404, detail="No deploy key exists for this project")
    return info


@router.post("/projects/{project_id}/git/key", status_code=201)
def git_create_key(project_id: str, user: dict = Depends(require_admin)):
    """Generate an ed25519 deploy keypair for the project. 409 if one exists."""
    from app.services import git_keys

    store = get_store(project_id)
    if git_keys.get_info(store.root) is not None:
        raise HTTPException(status_code=409, detail="A deploy key already exists for this project")
    try:
        info = git_keys.generate(store.root)
    except git_keys.SshKeygenNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    record_change(store, "git-key", "create", None, info, user.get("username", ""))
    return info


@router.post("/projects/{project_id}/git/key/rotate")
def git_rotate_key(project_id: str, user: dict = Depends(require_admin)):
    """Replace the deploy key. The old private key is discarded.

    Pushes will fail until the new public key is registered at the host — that
    is the whole danger of this button, and the UI's confirmation text says so.
    """
    from app.services import git_keys

    store = get_store(project_id)
    try:
        # Inside the try: `get_info` shells out to ssh-keygen for the
        # fingerprint, so it fails for exactly the same reasons the rotation
        # does and must be reported the same way rather than as a traceback.
        before = git_keys.get_info(store.root)
        info = git_keys.rotate(store.root)
    except git_keys.SshKeygenNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception as exc:
        # `rotate` swaps the new key in only once it is complete, so a failure
        # here means the existing key is still in place and pushes still work.
        # Saying so is the difference between an operator who retries and one
        # who assumes their backup path is broken and starts digging.
        logger.exception("Deploy key rotation failed for %s", project_id)
        raise HTTPException(
            status_code=500,
            detail=("Key rotation failed; the existing deploy key is unchanged "
                    f"and still in use. Cause: {exc}"),
        ) from None
    record_change(store, "git-key", "rotate", before, info, user.get("username", ""))
    return info


@router.delete("/projects/{project_id}/git/key", status_code=204)
def git_delete_key(project_id: str, user: dict = Depends(require_admin)):
    """Remove the deploy key. 204 whether or not one existed."""
    from app.services import git_keys

    store = get_store(project_id)
    before = git_keys.get_info(store.root)
    git_keys.delete(store.root)
    record_change(store, "git-key", "delete", before, None, user.get("username", ""))
    return Response(status_code=204)


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
def clear_suspects(project_id: str, user: dict = Depends(require_maintain)):
    from app.services.fingerprint import review_all
    return {"ok": True, **review_all(get_store(project_id), user.get("username", ""))}


# ── Git Hooks ─────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/hooks/install")
def install_git_hook(project_id: str, user: dict = Depends(require_maintain)):
    try:
        path = install_hook(str(get_store(project_id).root))
        return {"installed": True, "path": path}
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No .git directory found. Run 'git init' first.") from None


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
        raise HTTPException(status_code=404, detail="Requirement not found")
    before = dict(req)

    from app.services.fingerprint import review_item

    result = review_item(store, req_id, reviewer=user.get("username", ""), comment=data.comment)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    record_change(store, req_id, "review", before, result, user.get("username", ""))
    from app.services.email_service import notify_reviewed, _safe_notify
    _safe_notify(notify_reviewed, store, project_id, req_id, user.get("username", ""), data.comment)
    return result


@router.post("/projects/{project_id}/review-all", summary="Review all requirements")
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
    reqs = [r for r in store.list_requirements() if name in (r.get("baselines") or [])]
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
    comps = [c for c in store.list_components() if name in (c.get("baselines") or [])]
    component_snapshot = {}
    for c in comps:
        component_snapshot[c["id"]] = {
            "name": c.get("name", ""),
            "description": c.get("description", ""),
            "type": c.get("type", "assembly"),
            "parent": c.get("parent"),
            "part_number": c.get("part_number", ""),
            "supplier": c.get("supplier", ""),
            "quantity": c.get("quantity", 1),
            "satisfies": c.get("satisfies", []),
            "verification_cases": c.get("verification_cases", []),
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
            "frozen": True, "snapshot": snapshot,
            "component_snapshot": component_snapshot}
    store.write_item("baselines", name, data)
    return {"name": name, "symbol": sym, "description": desc, "requirements": len(snapshot)}


@router.get("/projects/{project_id}/baselines/{name}/diff")
def diff_baseline(project_id: str, name: str, against: str | None = None):
    """Compare a frozen baseline against the current requirements or another
    frozen baseline.

    ``name`` is always the "before" snapshot; ``against`` is the "after".
    When ``against`` is absent the comparison is against the live requirements.

    Read ``SRR`` against ``PDR`` as "what PDR did to SRR".
    """
    store = get_store(project_id)
    baseline = store.get_item("baselines", name)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Not found")

    snapshot = baseline.get("snapshot", {})

    if against is not None:
        safe_id(against, "baseline name")
        against_baseline = store.get_item("baselines", against)
        if against_baseline is None or not against_baseline.get("frozen"):
            raise HTTPException(status_code=404,
                                detail=f"Baseline '{against}' not found or is not frozen")
        against_snapshot = against_baseline.get("snapshot", {})

        changes = []
        for rid, r_data in against_snapshot.items():
            if rid in snapshot:
                snap = snapshot[rid]
                diffs = {}
                for field in ["status", "priority", "name", "description"]:
                    before_val = snap.get(field, "")
                    after_val = r_data.get(field, "")
                    if before_val != after_val:
                        diffs[field] = {"before": before_val, "after": after_val}
                if diffs:
                    changes.append({"id": rid, "type": "modified", "diffs": diffs})
            else:
                changes.append({"id": rid, "type": "added"})
        for rid in snapshot:
            if rid not in against_snapshot:
                changes.append({"id": rid, "type": "removed"})
        return {"baseline": name, "against": against,
                "symbol": baseline.get("symbol", ""),
                "description": baseline.get("description", ""),
                "frozen_at": baseline.get("frozen_at"), "changes": changes,
                "changed_count": len(changes)}

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
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    format: str = Form("auto"),
    mode: str = Form("merge"),
    dry_run: bool = Form(False),
    user: dict = Depends(require_maintain),
):
    """Import requirements from a ReqIF 1.2, SysML v2 or spreadsheet file.

    ``format`` is ``auto`` (sniff from content), ``reqif``, ``sysml``, ``csv``,
    ``tsv`` or ``xlsx``.
    ``mode`` is ``merge`` (create/update) or ``replace`` (wipe existing first).
    ``dry_run`` previews the change without writing, and is available for the
    table formats only.

    Supply exactly one of ``file`` (uploaded file) or ``text`` (pasted content).
    Pasting is supported for csv, tsv and auto only.
    """
    store = get_store(project_id)
    if format not in ("auto", "reqif", "sysml", "csv", "tsv", "xlsx"):
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    if (file is not None) == (text is not None):
        raise HTTPException(status_code=400, detail="Provide either a file or pasted text")

    if text is not None and format not in ("auto", "csv", "tsv"):
        raise HTTPException(status_code=400, detail="Pasted text is only supported for csv and tsv")

    # parse_and_import has no dry-run path, so honouring the flag for those
    # formats would mean performing a real import behind a button labelled
    # "Preview". `auto` is refused too: the format is not known until the
    # content has been sniffed, which happens inside parse_and_import.
    if dry_run and format not in ("csv", "tsv", "xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Dry run is only available for csv, tsv and xlsx",
        )

    username = user.get("username", "")

    def _normalise_summary(summary: dict) -> dict:
        """Give every format's summary the same key set.

        `ignored` is the fidelity report: only the SysML parser can name dropped
        constructs, but the client reads `ignored.lines` unconditionally — so the
        spreadsheet paths, which never touch import_into_store, have to carry the
        zero default or the import dialog throws on an otherwise successful CSV
        import. The `dry_run`/`would_*`/`rows` defaults do the same job for the
        preview fields, so the TypeScript type can declare them required and no
        caller has to branch on which format produced the summary.
        """
        summary.setdefault("ignored", {"lines": 0, "constructs": {}})
        summary.setdefault("dry_run", False)
        summary.setdefault("would_create", 0)
        summary.setdefault("would_update", 0)
        summary.setdefault("would_delete", 0)
        summary.setdefault("rows", 0)
        return summary

    if text is not None:
        limit = max(1, settings.max_upload_size_mb) * 1024 * 1024
        if len(text.encode("utf-8")) > limit:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_upload_size_mb} MB limit.")

        if format == "auto":
            fmt = "tsv" if "\t" in text.split("\n")[0] else "csv"
        else:
            fmt = format

        if dry_run and fmt not in ("csv", "tsv"):
            raise HTTPException(
                status_code=400,
                detail="Dry run is only available for csv, tsv and xlsx",
            )

        from app.services.table_io import import_table as table_import
        try:
            return _normalise_summary(table_import(store, text, fmt=fmt, mode=mode,
                                                   dry_run=dry_run, username=username))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    content = read_upload_capped(file, settings.max_upload_size_mb)

    if format in ("csv", "tsv"):
        from app.services.table_io import import_table as table_import
        try:
            return _normalise_summary(table_import(store, content.decode("utf-8", errors="replace"),
                                                   fmt=format, mode=mode, dry_run=dry_run, username=username))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    if format == "xlsx":
        from app.services.table_io import import_xlsx
        try:
            return _normalise_summary(import_xlsx(store, content, mode=mode, dry_run=dry_run))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    from app.services.importer import parse_and_import
    from app.services.reqif_import import ReqIFParseError
    from app.services.sysml_import import SysMLParseError

    try:
        summary = parse_and_import(store, content, fmt=format, mode=mode)
    except (ReqIFParseError, SysMLParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc
    return _normalise_summary(summary)
