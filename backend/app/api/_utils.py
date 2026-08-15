"""Shared helpers used by multiple API route modules.

Extracted from ``extra_routes.py`` so the split route files don't need
cross-imports from each other.
"""
from __future__ import annotations


from fastapi import HTTPException, Request, UploadFile


def check_precondition(request: Request, current: dict) -> None:
    """409 if the record moved since the client loaded it.

    Opt-in: no If-Match means no check, so existing partial-update callers are
    unaffected. ``modified`` is the version token because yaml_store already
    stamps it on every write — introducing a separate counter would give two
    sources of truth for the same question.
    """
    if_match = request.headers.get("If-Match")
    if if_match is None:
        return
    stored_modified = current.get("modified", "")
    if if_match != stored_modified:
        entity_id = current.get("id", "item")
        raise HTTPException(
            status_code=409,
            detail=f"{entity_id} was changed at {stored_modified}. "
                   f"Reload to see their version before saving yours.",
        )


def sorted_by_modified(items: list[dict], key: str = "modified") -> list[dict]:
    return sorted(items, key=lambda x: x.get(key, ""), reverse=True)


def read_upload_capped(file: UploadFile, limit_mb: int) -> bytes:
    """Read an uploaded file into memory, aborting with 413 once it exceeds the
    configured limit so a large upload can't exhaust memory."""
    limit = max(1, limit_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(4 * 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {limit_mb} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def enforce_naming(store, kind: str, new_id: str) -> None:
    """422 if *new_id* does not fit the project's naming scheme for *kind*.

    Enforcement is additional to ``safe_id``, never a replacement: a route still
    runs ``safe_id`` first, and this layers the permissive ``matches_scheme``
    check (see ``services.naming``) on top. It lives in the route layer rather
    than the store because the import paths and the demo seeder write through
    ``store.create_*`` directly and must stay exempt — see the task spec's
    Enforcement section.

    A project can opt out entirely with ``naming: {enforce: false}`` in its
    ``_meta.yaml``; that is the escape hatch for projects migrated from another
    tool whose legacy ids predate the standard. Absent means on.
    """
    from app.services.naming import enforce_enabled, matches_scheme

    meta = store.read_meta()
    if not enforce_enabled(meta):
        return
    reason = matches_scheme(new_id, meta, kind)
    if reason:
        raise HTTPException(status_code=422, detail=reason)


def paginate(items: list[dict], offset: int | None = None,
             limit: int | None = None, default_limit: int = 500,
             max_limit: int = 2000) -> dict:
    """Apply offset/limit pagination to a list, returning a typed page.

    Always returns the ``{items, total, offset, limit}`` envelope, whether or
    not the caller asked for a page. When both *offset* and *limit* are
    ``None``, ``items`` is everything capped at *max_limit* and ``offset``/``limit``
    report what was actually returned. Used by every list endpoint in the API.
    """
    if offset is None and limit is None:
        off, lim = 0, max_limit
    else:
        off = offset or 0
        lim = limit or default_limit
    total = len(items)
    return {"items": items[off:off + lim], "total": total, "offset": off, "limit": lim}

