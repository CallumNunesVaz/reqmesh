"""Real-time collaboration, search, allocation matrix, and test-result
import endpoints. Extracted from ``extra_routes.py``.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query, Depends, File, Form, UploadFile, WebSocket
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_store, require_maintain, get_current_user
from app.core.rate_limit import rate_limit
from app.api._utils import read_upload_capped

router = APIRouter()

# ── SSE state ─────────────────────────────────────────────────────────────────

_sse_lock: asyncio.Lock = asyncio.Lock()
_sse_conns_by_user: dict[str, int] = {}
_sse_conns_global: int = 0


# ── Presence roster ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/presence")
def project_presence(project_id: str):
    """Return the users currently viewing the project (real-time roster)."""
    from app.services.event_bus import get_event_bus

    users = get_event_bus().roster(project_id)
    return {"users": users, "count": len({u["username"] for u in users})}


# ── SSE Change Notifications ──────────────────────────────────────────────────

@router.get("/projects/{project_id}/events")
async def project_events(project_id: str, user: dict = Depends(get_current_user)):
    """Server-Sent Events stream for real-time collaboration."""
    from app.services.event_bus import get_event_bus

    username = user.get("username", "guest")
    async with _sse_lock:
        global _sse_conns_global
        if _sse_conns_global >= settings.max_sse_conns_global:
            raise HTTPException(status_code=429, detail="Too many SSE connections. Try again later.")
        if _sse_conns_by_user.get(username, 0) >= settings.max_sse_conns_per_user:
            raise HTTPException(status_code=429, detail="Too many SSE connections from this user. Try again later.")
        _sse_conns_global += 1
        _sse_conns_by_user[username] = _sse_conns_by_user.get(username, 0) + 1

    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)
    client_id = uuid.uuid4().hex
    role = user.get("role", "guest")

    async def event_stream():
        try:
            yield "event: connected\ndata: {}\n\n"
            bus.join(project_id, client_id, username, role)
            yield f"event: presence\ndata: {json.dumps({'type': 'presence', 'users': bus.roster(project_id)})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    bus.touch(project_id, client_id)
                    channel = "presence" if event.get("type") == "presence" else "change"
                    yield f"event: {channel}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    bus.touch(project_id, client_id)
                    yield "event: heartbeat\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bus.leave(project_id, client_id)
            bus.unsubscribe(project_id, queue)
            async with _sse_lock:
                _sse_conns_by_user[username] = _sse_conns_by_user.get(username, 0) - 1
                if _sse_conns_by_user[username] <= 0:
                    _sse_conns_by_user.pop(username, None)
                global _sse_conns_global
                _sse_conns_global -= 1

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Full-text search ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/search")
def search_project(project_id: str, q: str = Query(""), kind: str | None = Query(None),
                         _rate: None = Depends(rate_limit(20, 60))):
    """Full-text search across all entity types in a project."""
    from app.services.search import search_project as do_search

    store = get_store(project_id)
    results = do_search(store, q, kind, limit=50)
    return {"query": q, "results": results, "total": len(results)}


# ── Allocation matrix ─────────────────────────────────────────────────────────

class AllocationRequest(BaseModel):
    req_id: str
    component_id: str
    allocated: bool = True


@router.get("/projects/{project_id}/allocation-matrix")
def allocation_matrix(project_id: str, search: str = Query(""), filter_type: str = Query(""),
                            _rate: None = Depends(rate_limit(20, 60))):
    """Returns a requirements x components matrix showing allocation status."""
    store = get_store(project_id)
    reqs = store.list_requirements()
    comps = store.list_components()

    if filter_type:
        reqs = [r for r in reqs if r.get("type") == filter_type]
    if search:
        q = search.lower()
        reqs = [r for r in reqs if q in r["id"].lower() or q in r.get("name", "").lower()]
        comps = [c for c in comps if q in c["id"].lower() or q in c.get("name", "").lower()]

    allocation: dict[str, set[str]] = {}
    for c in comps:
        for rid in c.get("satisfies") or []:
            if rid:
                allocation.setdefault(rid, set()).add(c["id"])

    rows = []
    for r in reqs:
        alloc_set = allocation.get(r["id"], set())
        cells: dict[str, bool] = {}
        for c in comps:
            cells[c["id"]] = c["id"] in alloc_set
        rows.append({
            "req_id": r["id"],
            "req_name": r.get("name", ""),
            "req_status": r.get("status", ""),
            "allocated_to": r.get("allocated_to", ""),
            "cells": cells,
        })

    columns = [{"comp_id": c["id"], "comp_name": c.get("name", ""), "comp_type": c.get("type", "")}
               for c in comps]
    allocated = sum(1 for r in rows if any(r["cells"].values()))
    unallocated = len(rows) - allocated

    return {
        "rows": rows,
        "columns": columns,
        "total_requirements": len(rows),
        "total_components": len(columns),
        "allocated": allocated,
        "unallocated": unallocated,
        "allocation_pct": round(allocated / len(rows) * 100, 1) if rows else 0,
    }


@router.post("/projects/{project_id}/allocation")
def set_allocation(project_id: str, data: AllocationRequest, user: dict = Depends(require_maintain)):
    """Allocate or deallocate a requirement to/from a component."""
    store = get_store(project_id)
    req = store.get_requirement(data.req_id)
    comp = store.get_component(data.component_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    satisfies = list(comp.get("satisfies") or [])
    if data.allocated:
        if data.req_id not in satisfies:
            satisfies.append(data.req_id)
    else:
        satisfies = [r for r in satisfies if r != data.req_id]

    store.update_component(data.component_id, {"satisfies": satisfies})

    owners = [
        c.get("name") or c["id"]
        for c in store.list_components()
        if data.req_id in (c.get("satisfies") or [])
    ]
    allocated_to = ", ".join(sorted(owners))
    store.update_requirement(data.req_id, {"allocated_to": allocated_to})

    return {"req_id": data.req_id, "component_id": data.component_id,
            "allocated": data.allocated, "allocated_to": allocated_to}


# ── CI test-result import ─────────────────────────────────────────────────────

SAMPLE_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="reqmesh-vc" tests="3">
  <testcase classname="com.example.VerificationTests" name="VCAF0001"
            time="1.234">
  </testcase>
  <testcase classname="com.example.VerificationTests" name="VCPR0001"
            time="0.567">
    <failure message="assertion failed: expected True, got False">
      Traceback (most recent call last):
        test_engine.py:42 in test_thrust
      AssertionError: expected True, got False
    </failure>
  </testcase>
  <testcase classname="com.example.VerificationTests" name="UnknownTest"
            time="0.001">
    <skipped message="not applicable"/>
  </testcase>
</testsuite>"""


@router.get("/projects/{project_id}/test-results/sample")
def sample_test_result():
    """Return a sample JUnit XML showing the expected format for CI import."""
    return PlainTextResponse(content=SAMPLE_JUNIT, media_type="application/xml")


@router.post("/projects/{project_id}/test-results/import")
def import_test_results(
    project_id: str,
    file: UploadFile = File(...),
    format: str = Form("auto"),
    dry_run: bool = Form(False),
    user: dict = Depends(require_maintain),
):
    """Import CI test results (JUnit XML, CTRF JSON, TAP) and update
    verification case statuses."""
    from app.services.test_result_import import (
        detect_format, parse_results, import_test_results as do_import,
    )

    if format not in ("auto", "junit", "ctrf", "tap"):
        raise HTTPException(status_code=400,
                            detail=f"Unknown format '{format}'. Supported: auto, junit, ctrf, tap.")

    content = read_upload_capped(file, settings.max_upload_size_mb)

    detected = detect_format(content) if format == "auto" else format

    try:
        results = parse_results(content, detected)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400,
                            detail=f"Failed to parse test results: {exc}")

    store = get_store(project_id)
    summary = do_import(store, results, dry_run=dry_run)

    return {
        "format": format,
        "detected_format": detected,
        "dry_run": dry_run,
        "parsed": summary.parsed,
        "matched": summary.matched,
        "updated": summary.updated,
        "unmatched": summary.unmatched,
        "errors": summary.errors,
        "details": summary.details,
    }


# ── WebSocket (live events) ───────────────────────────────────────────────────

@router.websocket("/projects/{project_id}/ws")
async def project_websocket(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time collaboration."""
    from urllib.parse import parse_qs

    query_params = parse_qs(websocket.scope.get("query_string", b"").decode())
    token = (query_params.get("token", [""])[0]) or None
    from app.services.websocket_bus import websocket_handler
    await websocket_handler(websocket, project_id, token)
