"""Admin-only system endpoints: version/update checking and supervised update.

All routes require the admin role. The actual container swap is performed by the
updater sidecar (see app.services.updater); these endpoints check for updates,
trigger a supervised update, and report its progress.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import require_admin
from app.services import updater

router = APIRouter(prefix="/system", tags=["system"])


class UpdateRequest(BaseModel):
    target_version: str | None = None


@router.get("/info")
async def system_info(admin: dict = Depends(require_admin)):
    """Runtime facts the admin UI uses to decide what update UX to show."""
    return updater.runtime_info()


@router.get("/update/check")
async def check_update(force: bool = False, admin: dict = Depends(require_admin)):
    """Latest GitHub release vs the running version. Cached; force to bypass."""
    return await asyncio.to_thread(updater.check_for_update, force)


@router.get("/update/status")
async def update_status(admin: dict = Depends(require_admin)):
    return updater.get_update_status()


@router.post("/update")
async def start_update(body: UpdateRequest, admin: dict = Depends(require_admin)):
    """Back up data and signal the updater to move to the target version.

    Uses the latest available release when target_version is omitted.
    """
    if not updater.self_update_supported():
        raise HTTPException(
            status_code=409,
            detail="Self-update is not available in this deployment. Update manually (see docs).",
        )

    target = body.target_version
    if not target:
        check = await asyncio.to_thread(updater.check_for_update, True)
        if check.get("error"):
            raise HTTPException(status_code=502, detail=check["error"])
        if not check.get("update_available"):
            raise HTTPException(status_code=409, detail="Already running the latest version.")
        target = check["latest"]

    try:
        result = await asyncio.to_thread(
            updater.request_update, target, admin.get("username", "admin")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


@router.post("/update/dismiss")
async def dismiss_update(admin: dict = Depends(require_admin)):
    """Clear a completed/failed update's control files."""
    updater.clear_update_state()
    return {"ok": True}
