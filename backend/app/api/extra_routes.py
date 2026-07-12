from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import ValidationError

from app.core.dependencies import get_store, require_edit, get_current_user
from app.core.ids import safe_id
from app.models.change_request import ChangeRequestCreate, ChangeRequestUpdate
from app.models.requirement import RequirementUpdate
from app.models.risk import RiskCreate, RiskUpdate, CommentCreate, DecisionRecordCreate, DecisionRecordUpdate
from app.services.publisher import Publisher
from app.services.integrity import IntegrityChecker, mark_links_suspect, clear_suspect_links
from app.services.git_hooks import install_hook, uninstall_hook
from app.services.history import record_change

router = APIRouter()


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
    return store.create_item("change_requests", cr)


@router.put("/projects/{project_id}/change-requests/{cr_id}")
async def update_change_request(project_id: str, cr_id: str, data: ChangeRequestUpdate, user: dict = Depends(require_edit)):
    result = get_store(project_id).update_item("change_requests", cr_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return result


@router.delete("/projects/{project_id}/change-requests/{cr_id}")
async def delete_change_request(project_id: str, cr_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("change_requests", cr_id):
        raise HTTPException(status_code=404)
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
    return get_store(project_id).create_item("risks", r)


@router.put("/projects/{project_id}/risks/{risk_id}")
async def update_risk(project_id: str, risk_id: str, data: RiskUpdate, user: dict = Depends(require_edit)):
    result = get_store(project_id).update_item("risks", risk_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404)
    return result


@router.delete("/projects/{project_id}/risks/{risk_id}")
async def delete_risk(project_id: str, risk_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("risks", risk_id):
        raise HTTPException(status_code=404)
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
    return get_store(project_id).create_item("comments", c)


@router.delete("/projects/{project_id}/comments/{comment_id}")
async def delete_comment(project_id: str, comment_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("comments", comment_id):
        raise HTTPException(status_code=404)
    return {"ok": True}


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
    return get_store(project_id).create_item("decisions", d)


@router.put("/projects/{project_id}/decisions/{dec_id}")
async def update_decision(project_id: str, dec_id: str, data: DecisionRecordUpdate, user: dict = Depends(require_edit)):
    result = get_store(project_id).update_item("decisions", dec_id, data.model_dump(mode="json", exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404)
    return result


@router.delete("/projects/{project_id}/decisions/{dec_id}")
async def delete_decision(project_id: str, dec_id: str, user: dict = Depends(require_edit)):
    if not get_store(project_id).delete_item("decisions", dec_id):
        raise HTTPException(status_code=404)
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
    updated = []
    for req_id in ids:
        before = store.get_requirement(req_id)
        result = store.update_requirement(req_id, updates)
        if result:
            record_change(store, req_id, "update", before, result, user.get("username", ""))
            updated.append(req_id)
    return {"updated": len(updated), "ids": updated}


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


# ── Impact Analysis ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/requirements/{req_id}/impact")
async def get_impact(project_id: str, req_id: str):
    store = get_store(project_id)
    all_reqs = store.list_requirements()
    req = store.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404)
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
    store = get_store(project_id)
    reqs = store.list_requirements()
    vcs = store.list_verification_cases()
    vc_req_map: dict[str, list[str]] = {}
    for vc in vcs:
        for rid in vc.get("verified_requirements", []):
            vc_req_map.setdefault(rid, []).append(vc["id"])
    results = []
    for r in reqs:
        vc_count = len(vc_req_map.get(r["id"], []))
        rel_count = len(r.get("relations", []))
        results.append({
            "id": r["id"], "name": r.get("name", ""),
            "verification_cases": vc_count,
            "relations": rel_count,
            "covered": vc_count > 0 and rel_count > 0,
        })
    covered = sum(1 for r in results if r["covered"])
    return {"total": len(reqs), "covered": covered, "coverage_pct": round(covered / len(reqs) * 100) if reqs else 0, "items": results}


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
        if r.get("baseline"): baselines.add(r["baseline"])
        if r.get("description", "").strip(): with_desc += 1
        if r.get("rationale", "").strip(): with_rationale += 1
        if r.get("source", "").strip(): with_source += 1
        if r.get("allocated_to", "").strip(): with_alloc += 1
        if r.get("relations"): with_trace += 1
        if r.get("cascade_from"): with_cascade += 1

    return {
        "total": total,
        "verification_cases": len(vcs),
        "baselines": len(baselines),
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


# ── Publishing ────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/publish")
async def publish_project(project_id: str, data: dict, user: dict = Depends(get_current_user)):
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
    raise HTTPException(status_code=400, detail=f"Unknown format: {fmt} (use html, pdf, md, or latex)")


@router.get("/projects/{project_id}/publish/download")
async def download_report(project_id: str, format: str = "html", subsystems: str = ""):
    store = get_store(project_id)
    sub_list = [s.strip() for s in subsystems.split(",") if s.strip()] if subsystems else None
    pub = Publisher(store, sub_list)
    import tempfile
    ext_map = {"html": "html", "pdf": "pdf", "md": "md", "latex": "tex", "reqif": "xml", "sysml": "sysml"}
    if format not in ext_map:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    ext = ext_map[format]

    if format in ("reqif", "sysml"):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=f".{ext}")
        content = ""
        if format == "reqif":
            from app.services.reqif_export import export_reqif
            content = export_reqif(store)
        elif format == "sysml":
            from app.services.sysml_export import export_sysml_v2
            content = export_sysml_v2(store)
        with os.fdopen(fd, "w") as f:
            f.write(content)
    else:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            path = tmp.name
        if format == "html":
            pub.to_html_file(path)
        elif format == "pdf":
            pub.to_pdf_file(path)
        elif format == "md":
            pub.to_markdown_file(path)
        elif format == "latex":
            pub.to_latex_file(path)
    from fastapi.responses import FileResponse
    project_name = store.read_meta().get("name", project_id)
    return FileResponse(path, filename=f"{project_name.replace(' ', '_')}_report.{ext}", media_type="application/octet-stream")


# ── Validation ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/validate")
async def validate_project(project_id: str):
    store = get_store(project_id)
    checker = IntegrityChecker(store)
    return checker.check_all()


@router.get("/projects/{project_id}/suspect-links")
async def get_suspect_links(project_id: str):
    store = get_store(project_id)
    suspect_file = store.root / "_suspect.yaml"
    if not suspect_file.exists():
        return {"links": [], "count": 0}
    links = store._read_yaml(suspect_file).get("links", [])
    return {"links": links, "count": len(links)}


@router.post("/projects/{project_id}/suspect-links/clear")
async def clear_suspects(project_id: str, data: dict | None = None, user: dict = Depends(require_edit)):
    store = get_store(project_id)
    clear_suspect_links(store, (data or {}).get("ids"))
    return {"ok": True}


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
        raise HTTPException(status_code=404)
    before = dict(req)
    status = data.get("status", "in_review")
    req["review_status"] = status
    req["reviewers"] = data.get("reviewers", [])
    reviews = req.get("review_comments", [])
    comment = data.get("comment")
    if comment:
        reviews.append({
            "author": user.get("username", "unknown"),
            "comment": comment,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    req["review_comments"] = reviews
    result = store.update_requirement(req_id, req)
    record_change(store, req_id, "review", before, result, user.get("username", ""))
    mark_links_suspect(store, req_id)
    return result


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
        store.update_requirement(r["id"], {"baseline": name})
    return {"name": name, "requirements": len(snapshot)}


@router.get("/projects/{project_id}/baselines/{name}/diff")
async def diff_baseline(project_id: str, name: str):
    store = get_store(project_id)
    baseline = store.get_item("baselines", name)
    if baseline is None:
        raise HTTPException(status_code=404)
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


# ── SSE Change Notifications ──────────────────────────────────────────────────

import asyncio
import json
from fastapi.responses import StreamingResponse


@router.get("/projects/{project_id}/events")
async def project_events(project_id: str):
    """Server-Sent Events stream for real-time collaboration.

    Clients open a persistent connection and receive JSON events whenever
    a mutation occurs in the project.
    """
    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)

    async def event_stream():
        try:
            # Send an initial heartbeat so the client knows the connection is alive.
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: change\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
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
