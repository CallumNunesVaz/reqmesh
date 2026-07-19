from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional

from app.core.rate_limit import rate_limit

from app.core.auth import (
    ALLOWED_ROLES,
    GUEST_USER,
    authenticate,
    count_admins,
    delete_user,
    get_user_from_token,
    hash_password,
    load_users,
    public_users,
    register_user,
    set_user_password,
    set_user_role,
    create_reset_token,
    consume_reset_token,
    create_verify_token,
    verify_email,
)
from app.core.dependencies import get_current_user, require_admin

MIN_PASSWORD_LENGTH = 12
PASSWORD_RE = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};:\"\\|,.<>\/?]).{12,}$')

def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not PASSWORD_RE.match(password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter, one lowercase letter, one digit, and one special character")

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
async def login(data: LoginRequest, _rate: None = Depends(rate_limit(5, 60))):
    result = authenticate(data.username, data.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post("/auth/register")
async def register(data: RegisterRequest, authorization: Optional[str] = Header(None), _rate: None = Depends(rate_limit(3, 300))):
    if not USERNAME_RE.match(data.username):
        raise HTTPException(status_code=400, detail="Username must be 3–32 chars: letters, digits, . _ -")
    if len(data.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    _validate_password(data.password)
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
    users = load_users()
    u = users.get(user.get("username", ""), {})
    return {
        "username": user.get("username", "guest"),
        "role": user.get("role", "viewer"),
        "full_name": u.get("full_name", ""),
        "email": u.get("email", ""),
        "email_verified": u.get("email_verified", False),
        "last_active": u.get("last_active", ""),
        "joined": u.get("created", ""),
    }


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


@router.patch("/auth/profile")
async def update_profile(data: ProfileUpdateRequest, user: dict = Depends(get_current_user), _rate: None = Depends(rate_limit(3, 300))):
    username = user.get("username", "")
    if username in ("guest", ""):
        raise HTTPException(status_code=403, detail="Guests cannot update a profile")
    users = load_users()
    if data.full_name is not None:
        users[username]["full_name"] = data.full_name.strip()
    if data.email is not None:
        users[username]["email"] = data.email.strip()
    if data.password is not None:
        _validate_password(data.password)
        users[username]["password_hash"] = hash_password(data.password).decode()
        users[username]["token_version"] = users[username].get("token_version", 0) + 1
    from app.core.auth import save_users
    save_users(users)
    return {"ok": True}


# ── Password reset ────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, _rate: None = Depends(rate_limit(3, 300))):
    token = create_reset_token(data.username)
    if token is None:
        return {"ok": True}
    from app.core.config import settings
    from app.services.email_service import _send_email, _is_configured
    if _is_configured():
        users = load_users()
        email = users.get(data.username, {}).get("email", "")
        if email:
            reset_url = f"{settings.base_url.rstrip('/')}/reset-password?token={token}"
            _send_email(email, "Password reset request",
                f"<p>A password reset was requested for your reqmesh account.</p>"
                f"<p><a href=\"{reset_url}\">Click here to reset your password</a></p>"
                f"<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>")
    return {"ok": True}


@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordRequest, _rate: None = Depends(rate_limit(3, 300))):
    _validate_password(data.password)
    if not consume_reset_token(data.token, data.password):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    return {"ok": True}


# ── Email verification ────────────────────────────────────────────────────────

class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/auth/verify-email")
async def verify_email_endpoint(data: VerifyEmailRequest, _rate: None = Depends(rate_limit(5, 300))):
    username = verify_email(data.token)
    if not username:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    return {"ok": True, "username": username}


@router.post("/auth/resend-verification")
async def resend_verification(user: dict = Depends(get_current_user), _rate: None = Depends(rate_limit(1, 120))):
    from app.core.config import settings
    from app.services.email_service import _send_email, _is_configured
    username = user.get("username", "")
    users = load_users()
    u = users.get(username, {})
    if u.get("email_verified", False):
        return {"ok": True, "already_verified": True}
    email = u.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="No email address on file")
    token = create_verify_token(username)
    if token and _is_configured():
        verify_url = f"{settings.base_url.rstrip('/')}/verify-email?token={token}"
        _send_email(email, "Verify your email address",
            f"<p>Please verify your reqmesh account email.</p>"
            f"<p><a href=\"{verify_url}\">Click here to verify</a></p>"
            f"<p>This link expires in 24 hours.</p>")
    return {"ok": True}


# ── User management (admin only) ──────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "editor"
    email: str = ""
    full_name: str = ""


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None


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
    _validate_password(data.password)
    _validate_role(data.role)
    result = register_user(data.username, data.password, data.role)
    if not result:
        raise HTTPException(status_code=409, detail="Username already exists")
    if data.email.strip() or data.full_name.strip():
        from app.core.auth import load_users, save_users
        users = load_users()
        if data.email.strip():
            users[data.username]["email"] = data.email.strip()
        if data.full_name.strip():
            users[data.username]["full_name"] = data.full_name.strip()
        save_users(users)
    return {"username": data.username, "role": data.role, "full_name": data.full_name.strip()}


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
        _validate_password(data.password)
        set_user_password(username, data.password)

    if data.email is not None or data.full_name is not None:
        users = load_users()
        if data.email is not None:
            users[username]["email"] = data.email.strip()
        if data.full_name is not None:
            users[username]["full_name"] = data.full_name.strip()
        from app.core.auth import save_users
        save_users(users)

    users = load_users()
    return {"username": username, "role": users[username].get("role", "viewer"),
            "email": users[username].get("email", ""),
            "full_name": users[username].get("full_name", ""),
            "created": users[username].get("created", "")}


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
