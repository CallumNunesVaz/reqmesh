from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional

from app.core.auth import authenticate, register_user, get_user_from_token, GUEST_USER

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
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
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
async def whoami(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return GUEST_USER
    token = authorization.replace("Bearer ", "")
    user = get_user_from_token(token)
    if not user:
        return GUEST_USER
    return user
