import bcrypt
import jwt
import secrets
import time
import os
from pathlib import Path

TOKEN_TTL = 86400 * 7  # 7 days
RESET_TOKEN_TTL = 3600  # 1 hour
VERIFY_TOKEN_TTL = 86400  # 24 hours

USERS_FILE = Path.home() / ".reqmesh" / "users.yaml"
SECRET_FILE = Path.home() / ".reqmesh" / "secret"
RESET_TOKENS_FILE = Path.home() / ".reqmesh" / "reset_tokens.yaml"
VERIFY_TOKENS_FILE = Path.home() / ".reqmesh" / "verify_tokens.yaml"

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
        env_pw = os.environ.get("RT_ADMIN_PASSWORD", "")
        if not env_pw or env_pw == "admin":
            import logging
            env_pw = secrets.token_urlsafe(16)
            logging.getLogger("auth").warning(
                "No RT_ADMIN_PASSWORD set (or it is 'admin'). "
                "A random admin password was generated: %s. "
                "Set RT_ADMIN_PASSWORD to override.",
                env_pw,
            )
        default = {
            "admin": {
                "username": "admin",
                "password_hash": hash_password(env_pw).decode(),
                "role": "admin",
                "full_name": "Administrator",
                "email": "",
                "email_verified": True,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        }
        _yaml.dump(default, USERS_FILE)
        return default
    with open(USERS_FILE) as f:
        return _yaml.load(f) or {}


def save_users(users: dict) -> None:
    import tempfile
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=USERS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            _yaml.dump(users, f)
        os.replace(tmp, USERS_FILE)
    except BaseException:
        os.unlink(tmp)
        raise


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(username: str, role: str, token_version: int = 0) -> str:
    payload = {
        "sub": username,
        "role": role,
        "tv": token_version,
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
    user["last_active"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_users(users)
    return {"username": username, "role": user.get("role", "viewer"), "token": create_token(username, user.get("role", "viewer"))}


def register_user(username: str, password: str, role: str = "editor") -> dict | None:
    users = load_users()
    if username in users:
        return None
    users[username] = {
        "username": username,
        "password_hash": hash_password(password).decode(),
        "role": role,
        "full_name": "",
        "email": "",
        "email_verified": False,
        "token_version": 0,
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
    token_version = payload.get("tv", 0)
    stored_version = user.get("token_version", 0)
    if token_version != stored_version:
        return None
    return {"username": username, "role": user.get("role", "viewer"),
            "full_name": user.get("full_name", ""),
            "email_verified": user.get("email_verified", False)}


# --- User administration (admin-only management) ---

# "editor" = standard read/write user; "admin" = administrator. "viewer" is the
# read-only role that unauthenticated guests get and is kept for compatibility.
ALLOWED_ROLES = ("viewer", "editor", "admin")


def public_users() -> list[dict]:
    """All users without their password hashes, sorted by username."""
    users = load_users()
    out = [
        {"username": name, "role": u.get("role", "viewer"), "full_name": u.get("full_name", ""),
         "email": u.get("email", ""), "email_verified": u.get("email_verified", False),
         "last_active": u.get("last_active", ""),
         "joined": u.get("created", ""),
         "created": u.get("created", "")}
        for name, u in users.items()
    ]
    return sorted(out, key=lambda x: x["username"].lower())


def count_admins(users: dict) -> int:
    return sum(1 for u in users.values() if u.get("role") == "admin")


def set_user_role(username: str, role: str) -> bool:
    users = load_users()
    if username not in users:
        return False
    users[username]["role"] = role
    save_users(users)
    return True


def set_user_password(username: str, password: str) -> bool:
    users = load_users()
    if username not in users:
        return False
    users[username]["password_hash"] = hash_password(password).decode()
    users[username]["token_version"] = users[username].get("token_version", 0) + 1
    save_users(users)
    return True


def delete_user(username: str) -> bool:
    users = load_users()
    if username not in users:
        return False
    del users[username]
    save_users(users)
    return True


GUEST_USER = {"username": "guest", "role": "viewer"}


# ═══════════════════════════════════════════════════════════════════════════════
# Password reset tokens
# ═══════════════════════════════════════════════════════════════════════════════


def _load_token_store(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return _yaml.load(f) or {}


def _save_token_store(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            _yaml.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def create_reset_token(username: str) -> str | None:
    users = load_users()
    if username not in users:
        return None
    token = secrets.token_urlsafe(32)
    tokens = _load_token_store(RESET_TOKENS_FILE)
    tokens[token] = {"username": username, "expires": int(time.time()) + RESET_TOKEN_TTL}
    now = time.time()
    tokens = {k: v for k, v in tokens.items() if v.get("expires", 0) > now}
    _save_token_store(RESET_TOKENS_FILE, tokens)
    return token


def consume_reset_token(token: str, new_password: str) -> bool:
    tokens = _load_token_store(RESET_TOKENS_FILE)
    entry = tokens.get(token)
    if not entry:
        return False
    if entry.get("expires", 0) < time.time():
        del tokens[token]
        _save_token_store(RESET_TOKENS_FILE, tokens)
        return False
    username = entry["username"]
    del tokens[token]
    _save_token_store(RESET_TOKENS_FILE, tokens)
    return set_user_password(username, new_password)


# ═══════════════════════════════════════════════════════════════════════════════
# Email verification
# ═══════════════════════════════════════════════════════════════════════════════


def create_verify_token(username: str) -> str | None:
    users = load_users()
    if username not in users:
        return None
    token = secrets.token_urlsafe(32)
    tokens = _load_token_store(VERIFY_TOKENS_FILE)
    tokens[token] = {"username": username, "expires": int(time.time()) + VERIFY_TOKEN_TTL}
    now = time.time()
    tokens = {k: v for k, v in tokens.items() if v.get("expires", 0) > now}
    _save_token_store(VERIFY_TOKENS_FILE, tokens)
    return token


def verify_email(token: str) -> str | None:
    tokens = _load_token_store(VERIFY_TOKENS_FILE)
    entry = tokens.get(token)
    if not entry:
        return None
    if entry.get("expires", 0) < time.time():
        del tokens[token]
        _save_token_store(VERIFY_TOKENS_FILE, tokens)
        return None
    username = entry["username"]
    del tokens[token]
    _save_token_store(VERIFY_TOKENS_FILE, tokens)
    users = load_users()
    if username in users:
        users[username]["email_verified"] = True
        save_users(users)
        return username
    return None
