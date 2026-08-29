from __future__ import annotations

from pathlib import Path

from fastapi import Header, HTTPException, Request
from typing import Optional

from app.core.auth import get_user_from_token, GUEST_USER
from app.core.ids import safe_id
from app.services.yaml_store import YamlStore


DEFAULT_PERMISSIONS = {
    "guest": "view",
    "contributor": "propose",
    "maintainer": "edit",
    "admin": "admin",
}

PERMISSION_LEVELS = {"none": -1, "view": 0, "propose": 1, "edit": 2, "admin": 3}


#: The permission tier required to write each entity kind, whether one at a
#: time or in bulk. Split tiers are what let a propose-tier caller approve
#: their own change request through the generic PUT. Values map onto the guards
#: below: "propose" -> ``require_edit``, "edit" -> ``require_maintain``.
WRITE_TIER: dict[str, str] = {
    "change_requests": "propose",
    "risks": "propose",
    "comments": "propose",
    "decisions": "propose",
    "requirements": "edit",
    "components": "edit",
    "specifications": "edit",
    "verification_cases": "edit",
}


def get_project_permissions(project_id: str) -> dict:
    try:
        store = get_store(project_id)
        meta = store.read_meta()
        return meta.get("permissions") or dict(DEFAULT_PERMISSIONS)
    except Exception:
        return dict(DEFAULT_PERMISSIONS)


def user_permission_level(user: dict, project_id: str) -> int:
    role = user.get("role", "guest")
    # A project's permissions map can never demote a global admin.
    if role == "admin":
        return PERMISSION_LEVELS["admin"]
    perms = get_project_permissions(project_id)
    # Unknown/legacy roles (e.g. pre-migration "viewer"/"editor") aren't in the
    # map and fall through to view (0), so they can neither propose nor edit.
    perm = perms.get(role, "view")
    return PERMISSION_LEVELS.get(perm, 0)


def get_store(project_id: str) -> YamlStore:
    from app.core.config import settings

    project_root = Path(settings.data_root) / safe_id(project_id, "project id")
    if not project_root.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    if not (project_root / "_meta.yaml").exists():
        raise HTTPException(status_code=400, detail="Not a valid project (missing _meta.yaml)")
    return YamlStore(project_root)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Resolve the current user from cookie (preferred) or Authorization header.

    Always returns GUEST_USER when no valid credential is found; enforcement
    is the caller's job via the ``require_*`` guards, which reject the guest
    role. ``RT_REQUIRE_AUTH`` is applied by :func:`require_auth`, not here.
    """
    # 1. HttpOnly cookie (preferred — not readable by JS, sent automatically)
    token = request.cookies.get("token")
    if token:
        user = get_user_from_token(token)
        if user:
            return user

    # 2. Authorization: Bearer <token> header (backward compat + SSE/WS)
    if authorization and authorization.startswith("Bearer "):
        user = get_user_from_token(authorization.removeprefix("Bearer "))
        if user:
            return user

    return GUEST_USER


def require_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Require a valid session. Returns 401 when ``RT_REQUIRE_AUTH`` is set
    and no valid token is present."""
    from app.core.config import settings

    user = get_current_user(request=request, authorization=authorization)
    is_authenticated = user.get("role", "guest") != "guest"

    if settings.require_auth and not is_authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# NB: CSRF is enforced globally by ``main.csrf_middleware`` so it cannot be
# forgotten on a new route. Deliberately not also a dependency — two
# implementations of the same check drift apart.


def require_view(project_id: str, request: Request,
                 authorization: Optional[str] = Header(None)) -> dict:
    """View tier — the user's effective permission in this project must be at
    least ``view`` to read. The ``none`` tier (below ``view``) is what lets a
    project's ``permissions`` map deny reads outright; without it every role
    floors at ``view`` and this gate would be a no-op.

    Guest handling mirrors ``require_auth``: when ``RT_REQUIRE_AUTH`` is set and
    no valid session is present, the request is rejected with 401 rather than
    falling through to the permission check."""
    from app.core.config import settings

    user = get_current_user(request=request, authorization=authorization)
    is_authenticated = user.get("role", "guest") != "guest"

    if settings.require_auth and not is_authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user_permission_level(user, project_id) < PERMISSION_LEVELS["view"]:
        raise HTTPException(status_code=403, detail="View permission required")
    return user


def require_edit(project_id: str, request: Request,
                 authorization: Optional[str] = Header(None)) -> dict:
    """Propose tier — the user's effective permission in this project must be at
    least ``propose`` (change requests, risks, comments, decisions). Resolved
    per-project via the ``permissions`` map, so a project can grant/deny beyond
    the role defaults."""
    user = get_current_user(request=request, authorization=authorization)
    if user_permission_level(user, project_id) < PERMISSION_LEVELS["propose"]:
        raise HTTPException(status_code=403, detail="Propose permission required")
    return user


def require_maintain(project_id: str, request: Request,
                     authorization: Optional[str] = Header(None)) -> dict:
    """Edit tier — effective permission must be at least ``edit`` (requirements,
    components, specs, baselines, bulk ops, review, import/publish)."""
    user = get_current_user(request=request, authorization=authorization)
    if user_permission_level(user, project_id) < PERMISSION_LEVELS["edit"]:
        raise HTTPException(status_code=403, detail="Maintainer or admin permission required")
    return user


def require_maintain_global(request: Request,
                            authorization: Optional[str] = Header(None)) -> dict:
    """Maintainer tier for actions that aren't scoped to an existing project
    (currently only project creation), so there's no per-project map to consult."""
    user = get_current_user(request=request, authorization=authorization)
    if user["role"] not in ("maintainer", "admin"):
        raise HTTPException(status_code=403, detail="Maintainer or admin permission required")
    return user


def require_admin(request: Request,
                  authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(request=request, authorization=authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
    return user
