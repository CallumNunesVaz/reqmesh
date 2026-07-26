from __future__ import annotations

import re
import logging
import time as _time

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from pydantic import BaseModel
from typing import Optional

from app.core.rate_limit import rate_limit

audit_logger = logging.getLogger("audit")

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
    save_users,
    set_user_password,
    set_user_role,
    set_user_disabled,
    unlock_user,
    bump_token_version,
    create_invited_user,
    create_reset_token,
    consume_reset_token,
    create_verify_token,
    verify_email,
    set_auth_cookies,
    clear_auth_cookies,
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
    role: str = "contributor"


@router.post("/auth/login")
async def login(data: LoginRequest, response: Response, _rate: None = Depends(rate_limit(5, 60))):
    result = authenticate(data.username, data.password)
    status = result.get("status")

    # Uniform error response for all failure paths — same status code,
    # same message, comparable timing. Prevents user enumeration.
    if status != "ok":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Set HttpOnly cookie with the JWT and non-HttpOnly cookie for CSRF.
    csrf_token = set_auth_cookies(response, result["username"], result["token"])

    return {
        "username": result["username"],
        "role": result["role"],
        "csrf_token": csrf_token,
        "password_change_required": result.get("password_change_required", False),
    }


@router.post("/auth/register")
async def register(data: RegisterRequest, response: Response,
                   request: Request,
                   authorization: Optional[str] = Header(None),
                   _rate: None = Depends(rate_limit(3, 300))):
    if not USERNAME_RE.match(data.username):
        raise HTTPException(status_code=400, detail="Username must be 3–32 chars: letters, digits, . _ -")
    if len(data.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    _validate_password(data.password)
    from app.core.config import settings
    requester = None
    if authorization and authorization.startswith("Bearer "):
        requester = get_user_from_token(authorization.removeprefix("Bearer "))
    # Also check cookie for authenticated admin
    if not requester:
        token = request.cookies.get("token")
        if token:
            requester = get_user_from_token(token)
    is_admin = bool(requester and requester.get("role") == "admin")
    # Self-registration can be turned off; admins can always create accounts.
    if not settings.allow_self_registration and not is_admin:
        raise HTTPException(status_code=403,
                           detail="Self-registration is disabled. Ask an administrator for an account.")
    # Only an authenticated admin may grant elevated roles; self-registration
    # is always a contributor.
    role = "contributor"
    if data.role != "contributor":
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can assign roles")
        role = data.role
    result = register_user(data.username, data.password, role)
    if not result:
        # Same error whether username exists or password > 72 bytes
        raise HTTPException(status_code=409, detail="Username already exists")

    csrf_token = set_auth_cookies(response, result["username"], result["token"])
    return {
        "username": result["username"],
        "role": result["role"],
        "csrf_token": csrf_token,
        "password_change_required": False,
    }


@router.post("/auth/guest")
async def login_as_guest(response: Response):
    from app.core.config import settings
    if settings.require_auth:
        raise HTTPException(status_code=401,
                           detail="Authentication required. Guest access is disabled.")
    from app.core.auth import create_token
    token = create_token("guest", "guest", 0)
    csrf_token = set_auth_cookies(response, "guest", token)
    return {"username": "guest", "role": "guest", "csrf_token": csrf_token}


@router.get("/auth/whoami")
async def whoami(request: Request, user: dict = Depends(get_current_user),
                 authorization: Optional[str] = Header(None)):
    from app.core.auth import create_token as _create_token
    users = load_users()
    u = users.get(user.get("username", ""), {})

    # Return a short-lived JWT for WebSocket connections (in-memory use only).
    ws_token = ""
    if user.get("role", "guest") != "guest":
        tv = int(u.get("token_version", 0))
        ws_token = _create_token(user["username"], user.get("role", "guest"), tv)

    return {
        "username": user.get("username", "guest"),
        "role": user.get("role", "guest"),
        "full_name": u.get("full_name", ""),
        "email": u.get("email", ""),
        "email_verified": u.get("email_verified", False),
        "last_active": u.get("last_active", ""),
        "joined": u.get("created", ""),
        "token": ws_token,
        "password_change_required": bool(u.get("password_change_required", False)),
    }


@router.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


@router.patch("/auth/profile")
async def update_profile(data: ProfileUpdateRequest, user: dict = Depends(get_current_user), _rate: None = Depends(rate_limit(3, 300))):
    username = user.get("username", "")
    if username in ("guest", ""):
        raise HTTPException(status_code=403, detail="Guests cannot update a profile")
    from app.core.auth import users_lock
    with users_lock():
        users = load_users()
        record = users.get(username)
        if record is None:
            raise HTTPException(status_code=404, detail="User not found")
        if data.full_name is not None:
            record["full_name"] = data.full_name.strip()
        if data.email is not None:
            email = data.email.strip()
            if email and "@" not in email:
                raise HTTPException(status_code=400, detail="Invalid email address")
            if email != record.get("email", ""):
                # A new address has not been verified yet.
                record["email_verified"] = False
            record["email"] = email
        if data.password is not None:
            _validate_password(data.password)
            record["password_hash"] = hash_password(data.password).decode()
            record["token_version"] = record.get("token_version", 0) + 1
        save_users(users)
    return {"ok": True}


@router.post("/auth/logout-everywhere")
async def logout_everywhere(user: dict = Depends(get_current_user)):
    """Invalidate all of the caller's own sessions across devices."""
    username = user.get("username", "")
    if username in ("guest", ""):
        raise HTTPException(status_code=403, detail="Guests have no sessions")
    bump_token_version(username)
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
    # Always return the same response to prevent username enumeration
    from app.core.config import settings
    users = load_users()
    email = users.get(data.username, {}).get("email", "")
    if token is not None and email:
        from app.services.email_service import send_password_reset
        send_password_reset(email, token, settings.base_url)
    return {"detail": "If an account with that username exists, a reset link has been sent."}


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
    # Uniform response regardless of token validity to prevent enumeration
    if not username:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
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
    role: str = "contributor"
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
    audit_logger.info("Account created by admin: user=%s role=%s by=%s",
                       data.username, data.role, admin.get("username", ""))
    if data.email.strip() or data.full_name.strip():
        from app.core.auth import load_users, save_users, users_lock
        with users_lock():
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
        old_role = users[username].get("role", "guest")
        demoting_admin = users[username].get("role") == "admin" and data.role != "admin"
        if demoting_admin and count_admins(users) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last administrator")
        set_user_role(username, data.role)
        audit_logger.info("Role changed: user=%s old=%s new=%s by=%s",
                          username, old_role, data.role, admin.get("username", ""))

    if data.password is not None:
        _validate_password(data.password)
        set_user_password(username, data.password)

    if data.email is not None or data.full_name is not None:
        from app.core.auth import save_users, users_lock
        with users_lock():
            users = load_users()
            if data.email is not None:
                users[username]["email"] = data.email.strip()
            if data.full_name is not None:
                users[username]["full_name"] = data.full_name.strip()
            save_users(users)

    users = load_users()
    return {"username": username, "role": users[username].get("role", "guest"),
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
    audit_logger.info("Account deleted: user=%s by=%s", username, admin.get("username", ""))
    return {"ok": True}


# ── Account status: disable / unlock / force sign-out ─────────────────────────

class DisableRequest(BaseModel):
    disabled: bool


@router.post("/auth/users/{username}/disable")
async def disable_user(username: str, data: DisableRequest, admin: dict = Depends(require_admin)):
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if data.disabled and username == admin.get("username"):
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if data.disabled and users[username].get("role") == "admin" and count_admins(users) <= 1:
        raise HTTPException(status_code=400, detail="Cannot disable the last administrator")
    set_user_disabled(username, data.disabled)
    audit_logger.info("Account %s: user=%s by=%s",
                      "disabled" if data.disabled else "enabled",
                      username, admin.get("username", ""))
    return {"ok": True, "disabled": data.disabled}


@router.post("/auth/users/{username}/unlock")
async def unlock_account(username: str, admin: dict = Depends(require_admin)):
    if not unlock_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.post("/auth/users/{username}/logout")
async def force_logout(username: str, admin: dict = Depends(require_admin)):
    """Revoke every active session for a user (force sign-out everywhere)."""
    if not bump_token_version(username):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ── Invitations ───────────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    username: str
    email: str = ""
    role: str = "contributor"
    full_name: str = ""


def _invite_link(token: str) -> str:
    from app.core.config import settings
    return f"{settings.base_url.rstrip('/')}/reset-password?token={token}"


@router.post("/auth/users/invite", status_code=201)
async def invite_user(data: InviteRequest, admin: dict = Depends(require_admin)):
    """Create an account and email a set-password link. When SMTP is not
    configured the link is returned so the admin can share it manually."""
    if not USERNAME_RE.match(data.username):
        raise HTTPException(status_code=400, detail="Username must be 3–32 chars: letters, digits, . _ -")
    _validate_role(data.role)
    email = data.email.strip()
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    token = create_invited_user(data.username, data.role, email, data.full_name.strip())
    if token is None:
        raise HTTPException(status_code=409, detail="Username already exists")

    link = _invite_link(token)
    from app.services.email_service import _send_email, _is_configured
    emailed = False
    if email and _is_configured():
        _send_email(email, "You've been invited to reqmesh",
            f"<p>An administrator created a reqmesh account for you (<strong>{data.username}</strong>).</p>"
            f"<p><a href=\"{link}\">Click here to set your password</a></p>"
            f"<p>This link expires in 1 hour.</p>")
        emailed = True
    # Only reveal the link to the admin when it could not be emailed.
    return {"username": data.username, "role": data.role, "emailed": emailed,
            "invite_link": None if emailed else link}


# ── Bulk operations ───────────────────────────────────────────────────────────

class BulkUserRequest(BaseModel):
    usernames: list[str]
    action: str  # disable | enable | delete | set_role
    role: Optional[str] = None


@router.post("/auth/users/bulk")
async def bulk_user_action(data: BulkUserRequest, admin: dict = Depends(require_admin)):
    valid = {"disable", "enable", "delete", "set_role"}
    if data.action not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown action: {data.action}")
    if data.action == "set_role":
        _validate_role(data.role or "")
    users = load_users()
    me = admin.get("username")
    applied, skipped = [], []
    for username in data.usernames:
        if username not in users:
            skipped.append(username)
            continue
        is_last_admin = users[username].get("role") == "admin" and count_admins(users) <= 1
        if data.action == "delete":
            if username == me or is_last_admin:
                skipped.append(username)
                continue
            delete_user(username)
            audit_logger.info("Account deleted: user=%s by=%s", username, me)
        elif data.action == "disable":
            if username == me or is_last_admin:
                skipped.append(username)
                continue
            set_user_disabled(username, True)
            audit_logger.info("Account disabled: user=%s by=%s", username, me)
        elif data.action == "enable":
            set_user_disabled(username, False)
            audit_logger.info("Account enabled: user=%s by=%s", username, me)
        elif data.action == "set_role":
            if is_last_admin and data.role != "admin":
                skipped.append(username)
                continue
            old_role = users[username].get("role", "guest")
            set_user_role(username, data.role or "contributor")
            audit_logger.info("Role changed: user=%s old=%s new=%s by=%s",
                              username, old_role, data.role or "contributor", me)
        applied.append(username)
        users = load_users()  # refresh admin count after a mutation
    return {"applied": applied, "skipped": skipped}


# ── CSV import / export ───────────────────────────────────────────────────────

@router.get("/auth/users/export")
async def export_users_csv(admin: dict = Depends(require_admin)):
    import csv
    import io
    from fastapi.responses import Response

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["username", "full_name", "email", "role", "disabled", "email_verified", "created", "last_active"])
    for u in public_users():
        writer.writerow([u["username"], u["full_name"], u["email"], u["role"],
                         u["disabled"], u["email_verified"], u["created"], u["last_active"]])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=reqmesh-users.csv"})


class ImportUsersRequest(BaseModel):
    csv: str


@router.post("/auth/users/import")
async def import_users_csv(data: ImportUsersRequest, admin: dict = Depends(require_admin)):
    """Create accounts from CSV rows (username, full_name, email, role). Each new
    user is invited (set-password link); existing usernames are skipped."""
    import csv
    import io

    reader = csv.DictReader(io.StringIO(data.csv))
    created, skipped, invites = [], [], []
    for row in reader:
        username = (row.get("username") or "").strip()
        if not username or not USERNAME_RE.match(username):
            skipped.append(username or "(blank)")
            continue
        role = (row.get("role") or "contributor").strip()
        if role not in ALLOWED_ROLES:
            role = "contributor"
        email = (row.get("email") or "").strip()
        token = create_invited_user(username, role, email, (row.get("full_name") or "").strip())
        if token is None:
            skipped.append(username)
            continue
        created.append(username)
        from app.services.email_service import _send_email, _is_configured
        if email and _is_configured():
            _send_email(email, "You've been invited to reqmesh",
                f"<p>An administrator created a reqmesh account for you (<strong>{username}</strong>).</p>"
                f"<p><a href=\"{_invite_link(token)}\">Click here to set your password</a></p>")
        else:
            invites.append({"username": username, "invite_link": _invite_link(token)})
    return {"created": created, "skipped": skipped, "invites": invites}
