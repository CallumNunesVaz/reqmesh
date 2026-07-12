import bcrypt
import jwt
import secrets
import time
import os
from pathlib import Path

TOKEN_TTL = 86400 * 7  # 7 days

USERS_FILE = Path.home() / ".reqmesh" / "users.yaml"
SECRET_FILE = Path.home() / ".reqmesh" / "secret"

_secret_cache: str | None = None


def get_secret() -> str:
    """Signing secret: RT_SECRET env var, else a random key persisted locally."""
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.environ.get("RT_SECRET")
    if env:
        _secret_cache = env
        return env
    if SECRET_FILE.exists():
        _secret_cache = SECRET_FILE.read_text().strip()
        if _secret_cache:
            return _secret_cache
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _secret_cache = secrets.token_hex(32)
    SECRET_FILE.write_text(_secret_cache)
    SECRET_FILE.chmod(0o600)
    return _secret_cache

from ruamel.yaml import YAML
_yaml = YAML()
_yaml.indent(mapping=2, sequence=4, offset=2)


def load_users() -> dict:
    if not USERS_FILE.exists():
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        default = {
            "admin": {
                "username": "admin",
                "password_hash": hash_password(os.environ.get("RT_ADMIN_PASSWORD", "admin")).decode(),
                "role": "admin",
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        }
        _yaml.dump(default, USERS_FILE)
        return default
    with open(USERS_FILE) as f:
        return _yaml.load(f) or {}


def save_users(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        _yaml.dump(users, f)


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    return jwt.encode(payload, get_secret(), algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def authenticate(username: str, password: str) -> dict | None:
    users = load_users()
    user = users.get(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {"username": username, "role": user.get("role", "viewer"), "token": create_token(username, user.get("role", "viewer"))}


def register_user(username: str, password: str, role: str = "editor") -> dict | None:
    users = load_users()
    if username in users:
        return None
    users[username] = {
        "username": username,
        "password_hash": hash_password(password).decode(),
        "role": role,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_users(users)
    return {"username": username, "role": role, "token": create_token(username, role)}


def get_user_from_token(token: str) -> dict | None:
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    users = load_users()
    user = users.get(username)
    if not user:
        return None
    return {"username": username, "role": user.get("role", "viewer")}


GUEST_USER = {"username": "guest", "role": "viewer"}
