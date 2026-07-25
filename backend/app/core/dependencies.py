from __future__ import annotations

from pathlib import Path

from fastapi import Header, HTTPException
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

PERMISSION_LEVELS = {"view": 0, "propose": 1, "edit": 2, "admin": 3}


def get_project_permissions(project_id: str) -> dict:
    try:
        store = get_store(project_id)
        meta = store.read_meta()
        return meta.get("permissions") or dict(DEFAULT_PERMISSIONS)
    except Exception:
        return dict(DEFAULT_PERMISSIONS)


def _user_permission_level(user: dict, project_id: str) -> int:
    role = user.get("role", "guest")
    perms = get_project_permissions(project_id)
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


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        return GUEST_USER
    token = authorization.replace("Bearer ", "")
    user = get_user_from_token(token)
    if not user:
        return GUEST_USER
    return user


def require_edit(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="Edit permission required")
    return user


def require_maintain(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if user["role"] not in ("maintainer", "admin"):
        raise HTTPException(status_code=403, detail="Maintainer or admin permission required")
    return user


def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
    return user
