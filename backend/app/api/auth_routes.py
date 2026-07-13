from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from app.core.auth import (
    ALLOWED_ROLES,
    GUEST_USER,
    authenticate,
    count_admins,
    delete_user,
    get_user_from_token,
    load_users,
    public_users,
    register_user,
    set_user_password,
    set_user_role,
)
from app.core.dependencies import get_current_user, require_admin

MIN_PASSWORD_LENGTH = 8
# Usernames become YAML keys and URL path segments, so keep them simple/safe.
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "editor"


@router.post("/auth/login")
async def login(data: LoginRequest):
    result = authenticate(data.username, data.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post("/auth/register")
async def register(data: RegisterRequest, authorization: Optional[str] = Header(None)):
    if len(data.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(data.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    # Only an authenticated admin may grant elevated roles; self-registration
    # is always an editor.
    role = "editor"
    if data.role != "editor":
        requester = None
        if authorization and authorization.startswith("Bearer "):
            requester = get_user_from_token(authorization.removeprefix("Bearer "))
        if not requester or requester.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can assign roles")
        role = data.role
    result = register_user(data.username, data.password, role)
    if not result:
        raise HTTPException(status_code=409, detail="Username already exists")
    return result


@router.post("/auth/guest")
async def login_as_guest():
    return GUEST_USER


@router.get("/auth/whoami")
async def whoami(user: dict = Depends(get_current_user)):
    return user


# ── User management (admin only) ──────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "editor"


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None


def _validate_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")


@router.get("/auth/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all accounts (without password hashes). Admins only."""
    return public_users()


@router.post("/auth/users", status_code=201)
async def create_user(data: CreateUserRequest, admin: dict = Depends(require_admin)):
    if not USERNAME_RE.match(data.username):
        raise HTTPException(status_code=400, detail="Username must be 3–32 chars: letters, digits, . _ -")
    if len(data.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    _validate_role(data.role)
    result = register_user(data.username, data.password, data.role)
    if not result:
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"username": data.username, "role": data.role}


@router.patch("/auth/users/{username}")
async def update_user(username: str, data: UpdateUserRequest, admin: dict = Depends(require_admin)):
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role is not None:
        _validate_role(data.role)
        demoting_admin = users[username].get("role") == "admin" and data.role != "admin"
        if demoting_admin and count_admins(users) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last administrator")
        set_user_role(username, data.role)

    if data.password is not None:
        if len(data.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        set_user_password(username, data.password)

    users = load_users()
    return {"username": username, "role": users[username].get("role", "viewer"), "created": users[username].get("created", "")}


@router.delete("/auth/users/{username}")
async def remove_user(username: str, admin: dict = Depends(require_admin)):
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if username == admin.get("username"):
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if users[username].get("role") == "admin" and count_admins(users) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last administrator")
    delete_user(username)
    return {"ok": True}
