"""Admin-only system endpoints: version/update checking and supervised update.

All routes require the admin role. The actual container swap is performed by the
updater sidecar (see app.services.updater); these endpoints check for updates,
trigger a supervised update, and report its progress.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import require_admin
from app.services import updater

router = APIRouter(prefix="/system", tags=["system"])


class UpdateRequest(BaseModel):
    target_version: str | None = None


class TestEmailRequest(BaseModel):
    to: str


# ── Application settings (runtime, admin-editable) ────────────────────────────

@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    """Effective values for every admin-editable setting (secrets redacted)."""
    from app.core.settings_store import effective_settings
    return effective_settings()


@router.patch("/settings")
async def patch_settings(patch: dict, admin: dict = Depends(require_admin)):
    """Update runtime settings. Env-locked and blank-secret keys are ignored."""
    from app.core.settings_store import set_overrides
    return set_overrides(patch)


@router.post("/settings/test-email")
async def test_email(body: TestEmailRequest, admin: dict = Depends(require_admin)):
    """Send a test email using the current SMTP settings and report the result."""
    from app.services.email_service import send_test_email
    return await asyncio.to_thread(send_test_email, body.to)


@router.get("/public-config")
async def public_config():
    """Non-sensitive instance info for the login/registration UI (no auth)."""
    from app.core.config import settings
    return {
        "instance_name": settings.instance_name,
        "support_email": settings.support_email,
        "allow_self_registration": settings.allow_self_registration,
        "require_email_verification": settings.require_email_verification,
    }


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


@router.post("/update/upload")
async def upload_update(
    file: UploadFile = File(...),
    target_version: str = Form(""),
    admin: dict = Depends(require_admin),
):
    """Update from an uploaded Docker image archive (offline / air-gapped).

    The archive (e.g. reqmesh-vX.Y.Z-image.tar.gz from a release) is streamed to
    the control volume; the sidecar then `docker load`s it and recreates the app.
    """
    if not updater.file_update_supported():
        raise HTTPException(
            status_code=409,
            detail="File-based update requires a Docker deployment with the updater sidecar.",
        )

    dest = updater.staged_image_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    limit = settings.max_update_upload_mb * 1024 * 1024

    def _stream_to_disk() -> int:
        written = 0
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError("too_large")
                out.write(chunk)
        return written

    try:
        size = await asyncio.to_thread(_stream_to_disk)
    except ValueError:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_update_upload_mb} MB limit.")

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await asyncio.to_thread(
            updater.request_file_update, target_version.strip(), admin.get("username", "admin")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {**result, "archive_bytes": size}


@router.post("/update/dismiss")
async def dismiss_update(admin: dict = Depends(require_admin)):
    """Clear a completed/failed update's control files (and any staged archive)."""
    updater.clear_update_state()
    return {"ok": True}
