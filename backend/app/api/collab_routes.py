"""Real-time collaboration, search, allocation matrix, and test-result
import endpoints. Extracted from ``extra_routes.py``.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query, Depends, File, Form, UploadFile, WebSocket
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_store, require_maintain, get_current_user
from app.core.filelock import file_lock
from app.core.rate_limit import rate_limit
from app.api._utils import read_upload_capped
from app.services.link_registry import COLLECTION_LABELS, LINKS
from app.api.router import normalize_baseline_defs

router = APIRouter()

# ── SSE state ─────────────────────────────────────────────────────────────────

_sse_lock: asyncio.Lock = asyncio.Lock()

# Open SSE connections, as *leases* rather than bare counters: client_id ->
# (username, last_seen_monotonic).
#
# A plain counter incremented in the handler and decremented in the generator's
# `finally` leaks whenever the generator never runs to completion — the response
# is abandoned before it is iterated, the worker is killed mid-stream, an
# exception fires between acquire and the first `yield`. Nothing ever gives the
# slot back, so the count only ever rises. On the production host this had
# reached the per-user cap of 5, and every reconnect had 429'd for eight hours
# while the browser retried in a tight loop.
#
# A lease cannot leak permanently: it is renewed by the same 30 s heartbeat the
# presence roster uses (see EventBus._PRESENCE_TTL_SECONDS, deliberately the
# same ten-missed-beats budget), and anything that stops heartbeating is
# reclaimed on the next acquire. Release on clean exit is still immediate — the
# TTL is the backstop, not the mechanism.
_sse_leases: dict[str, tuple[str, float]] = {}
_SSE_LEASE_TTL_SECONDS = 300


def _reap_expired_leases(now: float) -> None:
    """Drop leases that have stopped heartbeating. Caller must hold ``_sse_lock``."""
    for cid in [c for c, (_, seen) in _sse_leases.items()
                if now - seen > _SSE_LEASE_TTL_SECONDS]:
        del _sse_leases[cid]


def _acquire_lease(client_id: str, username: str, now: float) -> str | None:
    """Take an SSE slot for ``username``, or return why it cannot be taken.

    Split out from the route so the cap can be tested without opening a real
    stream — an SSE response never ends on its own, so a test that drives it
    over HTTP hangs rather than asserts. Caller must hold ``_sse_lock``.
    """
    _reap_expired_leases(now)
    if len(_sse_leases) >= settings.max_sse_conns_global:
        return "Too many SSE connections. Try again later."
    if sum(1 for u, _ in _sse_leases.values() if u == username) >= settings.max_sse_conns_per_user:
        return "Too many SSE connections from this user. Try again later."
    _sse_leases[client_id] = (username, now)
    return None


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
    client_id = uuid.uuid4().hex

    async with _sse_lock:
        refused = _acquire_lease(client_id, username, time.monotonic())
    if refused:
        raise HTTPException(status_code=429, detail=refused)

    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)
    role = user.get("role", "guest")

    async def renew_lease() -> None:
        """Keep this connection's lease alive alongside the presence heartbeat."""
        async with _sse_lock:
            if client_id in _sse_leases:
                _sse_leases[client_id] = (username, time.monotonic())

    async def event_stream():
        try:
            yield "event: connected\ndata: {}\n\n"
            bus.join(project_id, client_id, username, role)
            yield f"event: presence\ndata: {json.dumps({'type': 'presence', 'users': bus.roster(project_id)})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    bus.touch(project_id, client_id)
                    await renew_lease()
                    channel = "presence" if event.get("type") == "presence" else "change"
                    yield f"event: {channel}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    bus.touch(project_id, client_id)
                    await renew_lease()
                    yield "event: heartbeat\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bus.leave(project_id, client_id)
            bus.unsubscribe(project_id, queue)
            async with _sse_lock:
                _sse_leases.pop(client_id, None)

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


# ── Allocation matrices ───────────────────────────────────────────────────────
#
# Three matrices, one mechanism. Each is a view of a link already declared in
# services/link_registry.py whose target is ``requirements``: requirements are
# always the rows, and the collection *holding* the link supplies the columns.
#
#   components          component.satisfies              "is satisfied by"
#   verification        verification_case.verified_...   "is verified by"
#   risks               risk.linked_requirements         "is threatened by"
#
# Writing these as three endpoints would have meant three copies of the same
# filtering, counting and toggling — and the registry already knows which field
# holds each relationship, so there is nothing left for a bespoke handler to
# add. Adding a fourth axis (specifications, change requests, decisions…) is a
# row in AXES.


def _link_for(holder: str, field: str):
    return next(ln for ln in LINKS
                if ln.holder == holder and ln.field == field and ln.target == "requirements")


@dataclass(frozen=True)
class MatrixAxis:
    """One matrix: which link it shows, and what to call it.

    Two shapes of axis exist, and they differ in every direction:

    * **Link axes** (components, verification, risks) read a link declared in
      ``link_registry``. The link is held by the *column* entity, which is a
      record in the ``holder`` collection, and points at requirement **ids**.
      A cell write goes to the holder.

    * **The baselines axis** inverts all three. Its columns are definitions in
      project metadata rather than records in a collection, the membership is
      held by the *requirement* in ``req_field``, and it stores baseline
      **names** rather than ids. ``link_registry`` deliberately excludes it —
      "a baseline is a label rather than a record that can dangle" — so there
      is no ``Link`` to read and ``link`` is None.

    ``req_field`` is what distinguishes them. Anything branching on axis shape
    tests that, not the key.
    """
    key: str
    holder: str
    field: str
    #: Reads as "<requirement> <verb> <column>", for the UI's own wording.
    verb: str
    column_label: str
    #: Set only on requirement-held axes. Names the field on the *requirement*
    #: holding the membership, whose entries are column **names**, not ids.
    req_field: str | None = None

    @property
    def link(self):
        """The registry link this axis shows, or None on a requirement-held axis."""
        if self.req_field is not None:
            return None
        return _link_for(self.holder, self.field)


AXES: dict[str, MatrixAxis] = {
    "components": MatrixAxis("components", "components", "satisfies",
                             "is satisfied by", "Components"),
    "verification": MatrixAxis("verification", "verification_cases", "verified_requirements",
                               "is verified by", "Verification Cases"),
    "risks": MatrixAxis("risks", "risks", "linked_requirements",
                        "is threatened by", "Risks"),
    "baselines": MatrixAxis("baselines", "baselines", "", "is baselined in",
                            "Baselines", req_field="baselines"),
}


class AllocationRequest(BaseModel):
    req_id: str
    #: Preferred identifier for the row entity; ``req_id`` remains the alias so
    #: existing callers of every matrix are unaffected.
    row_id: str | None = None
    row_kind: str = "requirements"
    #: The column entity. ``component_id`` is the original spelling and still
    #: works, so existing callers of the components matrix are unaffected.
    target_id: str | None = None
    component_id: str | None = None
    axis: str = "components"
    allocated: bool = True

    def resolved_target(self) -> str:
        target = self.target_id or self.component_id
        if not target:
            raise HTTPException(status_code=422, detail="target_id is required")
        return target

    def resolved_row(self) -> str:
        return self.row_id or self.req_id


def _axis_or_404(axis: str) -> MatrixAxis:
    found = AXES.get(axis)
    if found is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown matrix axis: {axis} (use {', '.join(AXES)})")
    return found


def _column_items(store, axis: MatrixAxis) -> list[dict]:
    return store.list_items(axis.holder)


def _column_name(item: dict) -> str:
    # Risks and change requests carry `title`; the rest carry `name`.
    return item.get("name") or item.get("title") or ""


@router.get("/projects/{project_id}/allocation-matrix")
def allocation_matrix(project_id: str, axis: str = Query("components"),
                      rows: str = Query("requirements"),
                      search: str = Query(""), filter_type: str = Query(""),
                      _rate: None = Depends(rate_limit(20, 60))):
    """Requirements against components, verification cases, risks, or baselines."""
    ax = _axis_or_404(axis)
    store = get_store(project_id)

    if rows not in ("requirements", "components"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown rows value: {rows} (use requirements or components)")
    if rows == "components" and ax.req_field is None:
        raise HTTPException(
            status_code=400,
            detail=f"rows=components is only valid with axis=baselines, not {ax.key}")

    if rows == "components":
        row_entities: list[dict] = store.list_components()
    else:
        row_entities = store.list_requirements()

    if ax.req_field is not None:
        # Baselines axis: columns from metadata definitions, not frozen snapshots.
        meta = store.read_meta()
        defs = normalize_baseline_defs(meta.get("baselines", []))
        defined_names = {d["name"] for d in defs}
        cols = [{"id": d["name"], "name": d["name"], "kind": d["symbol"],
                 "due_date": d["due_date"], "order": d["order"]} for d in defs]

        # Orphan baselines: names on entities with no definition.
        orphan_names: set[str] = set()
        for entity in row_entities:
            for bl in (entity.get(ax.req_field) or []):
                if bl and bl not in defined_names:
                    orphan_names.add(bl)
        for name in sorted(orphan_names):
            cols.append({"id": name, "name": name, "kind": "",
                         "due_date": "", "order": 0})
    else:
        cols = _column_items(store, ax)

    if filter_type:
        row_entities = [e for e in row_entities if e.get("type") == filter_type]
    if search:
        q = search.lower()
        row_entities = [e for e in row_entities
                        if q in e["id"].lower() or q in e.get("name", "").lower()]
        cols = [c for c in cols if q in c["id"].lower() or q in _column_name(c).lower()]

    linked: dict[str, set[str]] = {}
    if ax.req_field is not None:
        # Membership is held by the row entity, not the column.
        for entity in row_entities:
            for bl in (entity.get(ax.req_field) or []):
                if bl:
                    linked.setdefault(entity["id"], set()).add(bl)
    else:
        for c in cols:
            for rid in (c.get(ax.field) or []):
                if rid:
                    linked.setdefault(rid, set()).add(c["id"])

    rows_out = []
    for entity in row_entities:
        hits = linked.get(entity["id"], set())
        row: dict[str, object] = {
            "row_id": entity["id"],
            "row_name": entity.get("name", ""),
            "row_status": entity.get("status", "") if rows == "requirements" else "",
            "row_type": entity.get("type", ""),
            "cells": {c["id"]: c["id"] in hits for c in cols},
        }
        if rows == "requirements":
            row.update({
                "req_id": entity["id"],
                "req_name": entity.get("name", ""),
                "req_status": entity.get("status", ""),
                "req_type": entity.get("type", ""),
                "allocated_to": entity.get("allocated_to", ""),
            })
        rows_out.append(row)

    columns = [{
        "id": c["id"],
        "name": _column_name(c),
        # Whatever secondary label the column entity has: a component's type, a
        # verification case's method, a risk's severity, a baseline's symbol.
        "kind": c.get("type") or c.get("method") or c.get("severity") or c.get("kind") or "",
        # The sequence is what makes the baselines matrix readable left to right,
        # so the columns carry their position and deadline.
        **({"due_date": c.get("due_date", ""), "order": c.get("order", 0)}
           if ax.req_field is not None else {}),
        # Kept so the components matrix's original response shape still parses
        # for anyone reading comp_id/comp_name.
        **({"comp_id": c["id"], "comp_name": _column_name(c), "comp_type": c.get("type", "")}
           if ax.key == "components" else {}),
    } for c in cols]

    covered = sum(1 for r in rows_out if any(r["cells"].values()))
    total_reqs = len(store.list_requirements())
    return {
        "axis": ax.key,
        "verb": ax.verb,
        "column_label": ax.column_label,
        "row_kind": rows,
        "rows": rows_out,
        "columns": columns,
        "total_requirements": total_reqs,
        "total_rows": len(rows_out),
        "total_columns": len(columns),
        "total_components": len(columns),   # legacy name, components axis
        "allocated": covered,
        "unallocated": len(rows_out) - covered,
        "allocation_pct": round(covered / len(rows_out) * 100, 1) if rows_out else 0,
    }


@router.post("/projects/{project_id}/allocation")
def set_allocation(project_id: str, data: AllocationRequest, user: dict = Depends(require_maintain)):
    """Toggle one cell of any of the allocation matrices.

    The write goes to the *holder* of the link — the component, the
    verification case, the risk — because that is the side the model stores.
    Only ``component.satisfies`` has a persisted mirror to keep in step
    (``requirement.allocated_to``); the others are recomputed on read, so
    writing anything back to the requirement would create a second copy that
    could disagree with the first.

    The baselines axis is the exception: its membership is held by the row
    entity in ``req_field``, and it stores baseline **names**, not ids.
    With ``row_kind="components"`` the row entity is a component rather than
    a requirement.
    """
    ax = _axis_or_404(data.axis)
    target_id = data.resolved_target()
    store = get_store(project_id)

    if data.row_kind not in ("requirements", "components"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown row_kind: {data.row_kind} (use requirements or components)")
    if data.row_kind == "components" and data.axis != "baselines":
        raise HTTPException(
            status_code=400,
            detail=f"row_kind=components is only valid with axis=baselines, not {data.axis}")

    entity_id = data.resolved_row()

    if ax.req_field is not None:
        # Baselines axis: write to the row entity's baselines field. The column
        # is checked against the metadata definitions rather than the `baselines`
        # collection, which holds only the snapshots of baselines that have
        # been frozen — an unfrozen baseline is still a legitimate column.
        defs = normalize_baseline_defs(store.read_meta().get("baselines", []))
        if target_id not in {d["name"] for d in defs}:
            raise HTTPException(status_code=404, detail="Baseline not found")

        if data.row_kind == "components":
            path = store._item_path("components", entity_id)
            # Hold the item lock across the read-modify-write so a concurrent
            # allocation edit to the same component cannot clobber this one.
            with file_lock(path):
                comp = store.get_item("components", entity_id)
                if not comp:
                    raise HTTPException(status_code=404, detail="Component not found")

                blist = list(comp.get(ax.req_field) or [])

                if data.allocated:
                    if target_id not in blist:
                        blist.append(target_id)
                else:
                    blist = [b for b in blist if b != target_id]

                store._update_item_unlocked("components", entity_id, {ax.req_field: blist})

            return {"req_id": data.req_id, "row_id": entity_id,
                    "row_kind": "components",
                    "axis": ax.key, "target_id": target_id,
                    "component_id": target_id,
                    "allocated": data.allocated, "allocated_to": ""}

        # Row kind is "requirements" (requirement-held axis, as before).
        path = store._item_path("requirements", entity_id)
        with file_lock(path):
            req = store.get_requirement(entity_id)
            if not req:
                raise HTTPException(status_code=404, detail="Requirement not found")

            blist = list(req.get(ax.req_field) or [])

            if data.allocated:
                if target_id not in blist:
                    blist.append(target_id)
            else:
                blist = [b for b in blist if b != target_id]

            # `entity_id`, not `data.req_id` — the read above used the resolved row,
            # so writing the raw alias would read one record and update another
            # whenever a caller sends `row_id` and `req_id` that differ.
            store._update_item_unlocked("requirements", entity_id, {ax.req_field: blist})

        return {"req_id": data.req_id, "row_id": entity_id,
                "row_kind": "requirements",
                "axis": ax.key, "target_id": target_id,
                "component_id": target_id,
                "allocated": data.allocated, "allocated_to": ""}

    # Link axes: the row is always a requirement, and the write goes to the
    # holder (the column entity).
    #
    # `entity_id` throughout, so `row_id` is the preferred identifier on every
    # axis rather than only on the baselines one — two axes disagreeing about
    # which field names the row is exactly the sort of split that survives
    # tests and bites a caller later.

    req = store.get_requirement(entity_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    holder = store.get_item(ax.holder, target_id)
    if not holder:
        raise HTTPException(
            status_code=404,
            detail=f"{COLLECTION_LABELS.get(ax.holder, ax.holder).capitalize()} not found")

    current = [x for x in (holder.get(ax.field) or []) if x]
    if data.allocated:
        if entity_id not in current:
            current.append(entity_id)
    else:
        current = [r for r in current if r != entity_id]
    store.update_item(ax.holder, target_id, {ax.field: current})

    allocated_to = ""
    if ax.link.inverse_stored and ax.link.derived_inverse:
        # Recomputed from every holder, not cleared: deallocating one component
        # used to blank the field while another still satisfied the requirement.
        owners = [
            _column_name(c) or c["id"]
            for c in store.list_items(ax.holder)
            if entity_id in (c.get(ax.field) or [])
        ]
        allocated_to = ", ".join(sorted(owners))
        store.update_requirement(entity_id, {ax.link.derived_inverse: allocated_to})

    return {"req_id": data.req_id, "row_id": entity_id,
            "row_kind": "requirements",
            "axis": ax.key, "target_id": target_id,
            # Original spelling, so callers of the components matrix still parse.
            "component_id": target_id,
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
def sample_test_result(project_id: str):
    # `project_id` is unused — the sample is the same for every project — but it
    # has to be declared, or the generated OpenAPI schema describes a path with
    # a template variable it never defines, which no client generator (and no
    # schema-driven test) can satisfy.
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
