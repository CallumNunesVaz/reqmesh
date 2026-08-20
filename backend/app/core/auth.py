import copy
import bcrypt
import hashlib
import ipaddress
import jwt
import secrets
import time
import os
import logging
from pathlib import Path

from app.core.paths import state_dir

audit_logger = logging.getLogger("audit")

TOKEN_TTL = 86400 * 7  # 7 days
RESET_TOKEN_TTL = 3600  # 1 hour
VERIFY_TOKEN_TTL = 86400  # 24 hours

# Where the account database and signing secret live.
#
# This is deliberately overridable and not simply ``Path.home()``. In the Docker
# deployment the container runs as uid 999 with HOME=/app, the root filesystem is
# read-only, and the compose file covers /app/.reqmesh with a tmpfs owned by
# root — so the default resolved to a directory the app could not write, and
# login failed with PermissionError on users.yaml. Even had it been writable,
# tmpfs is memory-backed: every account and password change would have been
# discarded on restart while the project data beside it persisted.
#
# RT_STATE_DIR points this at the same durable volume as the project data.
_STATE_DIR = state_dir()

USERS_FILE = _STATE_DIR / "users.yaml"
SECRET_FILE = _STATE_DIR / "secret"
RESET_TOKENS_FILE = _STATE_DIR / "reset_tokens.yaml"
VERIFY_TOKENS_FILE = _STATE_DIR / "verify_tokens.yaml"

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
    fd = os.open(str(SECRET_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, _secret_cache.encode())
    finally:
        os.close(fd)
    return _secret_cache

from ruamel.yaml import YAML
import threading
from app.core.filelock import file_lock
_yaml = YAML()
_yaml.indent(mapping=2, sequence=4, offset=2)
# See yaml_store._yaml_lock: a shared ruamel instance is not thread-safe, and
# concurrent use corrupts it for the rest of the process.
_yaml_lock = threading.Lock()


def users_lock():
    """Guard a ``load_users() → mutate → save_users()`` cycle.

    Without it those cycles interleave: two admins creating accounts each write
    back their own snapshot and one account silently never existed, and — worse
    — a login racing ``delete_user`` writes the whole dict back including the
    deleted entry, **resurrecting the account** with a token already issued.

    Deliberately a bare lock rather than a save-on-exit transaction, so every
    existing early-return that skips the save keeps doing exactly that.
    """
    from app.core.filelock import file_lock
    return file_lock(USERS_FILE)


# --- users.yaml read cache ---
# `load_users()` is called from request threads in a threadpool, and it used to
# open and round-trip-parse the whole account file on every authenticated
# request — linear in the number of accounts before any application work began.
# Cache the parse keyed by (mtime_ns, size) of USERS_FILE, the same signature
# `yaml_store._dir_signature` uses: a stale key forces a re-read rather than a
# stale answer, so an external edit to users.yaml is picked up without a restart
# (mtime_ns is sub-nanosecond-granularity on modern filesystems and covers the
# single-worker case; `save_users` invalidates explicitly for coarse ones).
_users_cache: dict | None = None
_users_cache_key: tuple | None = None
_users_cache_lock = threading.Lock()


def _users_file_signature() -> tuple | None:
    """``(st_mtime_ns, st_size)`` of USERS_FILE, or None if it cannot be stat'd."""
    try:
        st = USERS_FILE.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def invalidate_users_cache() -> None:
    """Drop the cached parse of users.yaml.

    Called by ``save_users`` after every write, and available to tests that
    rewrite the file out-of-band. Deliberately a *separate* lock from
    ``users_lock``: save_users runs inside a ``users_lock()`` block, so reusing
    it here would deadlock.
    """
    global _users_cache, _users_cache_key
    with _users_cache_lock:
        _users_cache = None
        _users_cache_key = None


def load_users() -> dict:
    global _users_cache, _users_cache_key
    if not USERS_FILE.exists():
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        env_pw = os.environ.get("RT_ADMIN_PASSWORD", "")
        if not env_pw or env_pw == "admin":
            env_pw = secrets.token_urlsafe(16)
            from app.core.config import settings
            pw_file = Path(settings.data_root) / ".initial-admin"
            pw_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(pw_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, env_pw.encode())
                os.write(fd, b"\n")
            finally:
                os.close(fd)
            logging.getLogger("auth").warning(
                "No RT_ADMIN_PASSWORD set (or it is 'admin'). "
                "A random admin password has been written to %s. "
                "Delete this file after first login. "
                "Set RT_ADMIN_PASSWORD to override.",
                str(pw_file),
            )
        default = {
            "admin": {
                "username": "admin",
                "password_hash": hash_password(env_pw).decode(),
                "role": "admin",
                "full_name": "Administrator",
                "email": "",
                "email_verified": True,
                "password_change_required": True,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        }
        # Through save_users, not a bare dump: that is what makes the very first
        # users.yaml atomic and 0600. Dumping straight to the path left a fresh
        # install's account file at whatever the umask allowed, typically 0644.
        save_users(default)
        return default
    signature = _users_file_signature()
    with _users_cache_lock:
        if _users_cache is not None and _users_cache_key == signature:
            # Deep copy: callers run load → mutate → save under users_lock, so
            # handing out the cached object would leak one request's
            # half-finished mutation into every other request's view.
            return copy.deepcopy(_users_cache)

    with open(USERS_FILE) as f:
        # Safe loader, per-call. The read result is never written back (writes
        # go through save_users), so comments/formatting are not at risk, and
        # the safe parser is ~6.5x faster than the shared round-trip `_yaml`
        # (kept below for the write path only).
        data = YAML(typ="safe").load(f) or {}

    with _users_cache_lock:
        _users_cache = data
        _users_cache_key = signature

    return copy.deepcopy(data)


def _chmod_private(path: Path) -> None:
    """Owner-only, always.

    `mkstemp` already creates at 0600 and `os.replace` carries that mode over,
    so this is belt and braces for the happy path — but it also *repairs* a file
    an older build created under the umask, without waiting for a migration.
    Best-effort: a file on a filesystem that cannot represent the mode is not a
    reason to fail the write that just succeeded.
    """
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        logging.getLogger(__name__).warning("could not tighten permissions on %s: %s", path, exc)


def save_users(users: dict) -> None:
    import tempfile
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=USERS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            with _yaml_lock:
                _yaml.dump(users, f)
        os.replace(tmp, USERS_FILE)
        _chmod_private(USERS_FILE)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        os.unlink(tmp)
        raise
    invalidate_users_cache()


#: bcrypt work factor. OWASP's floor is 10; 12 is roughly a quarter-second per
#: hash on current hardware, which is a cost an attacker pays per guess and a
#: user pays once per login. Stated here rather than left to `gensalt()`'s
#: default so the number is a reqmesh decision, not a bcrypt-version one.
BCRYPT_ROUNDS = 12

#: Prefixes bcrypt produces. Kept as a tuple because `verify_password`
#: dispatches on it: that is the seam that lets a future algorithm be added
#: without a flag day or a forced password reset for every account.
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def verify_password(password: str, hashed: str) -> bool:
    """Check a password against a stored hash, dispatching on its format.

    Fails closed on anything unrecognised. Previously a corrupted or truncated
    hash reached bcrypt, which raises — turning a bad record in `users.yaml`
    into a 500 on the login path rather than a failed login.
    """
    if not hashed.startswith(_BCRYPT_PREFIXES):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when a stored hash is weaker than what `hash_password` produces now.

    The work factor is meant to rise as hardware gets cheaper, and OWASP's
    guidance is to re-hash at the next successful login rather than force a
    reset — the only moment the plaintext is legitimately in hand.
    """
    if not hashed.startswith(_BCRYPT_PREFIXES):
        return True
    try:
        return int(hashed.split("$")[2]) < BCRYPT_ROUNDS
    except (IndexError, ValueError):
        return True


def _token_ttl() -> int:
    try:
        from app.core.config import settings
        return int(settings.token_ttl_seconds) or TOKEN_TTL
    except Exception:
        return TOKEN_TTL


def create_token(username: str, role: str, token_version: int = 0) -> str:
    payload = {
        "sub": username,
        "role": role,
        "tv": token_version,
        "iat": int(time.time()),
        "exp": int(time.time()) + _token_ttl(),
    }
    return jwt.encode(payload, get_secret(), algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def authenticate(username: str, password: str) -> dict:
    """Attempt a login. Returns a dict with a ``status`` of ``ok``, ``invalid``,
    ``disabled``, ``locked`` (with ``until``), or ``unverified``.

    Enforces account disable, failed-login lockout, and (when configured)
    email-verification. On success the token carries the user's current
    ``token_version`` so admin password resets / force-logouts invalidate it.
    """
    with users_lock():
        from app.core.config import settings

        # bcrypt 5.0 raises on passwords > 72 bytes. Reject early so it never 500s
        # and the timing profile matches other invalid-credential paths.
        if len(password.encode()) > 72:
            audit_logger.warning("Login failed: user=%s reason=invalid_password", username)
            return {"status": "invalid"}

        users = load_users()
        user = users.get(username)
        if not user:
            hash_password(secrets.token_urlsafe(32))
            audit_logger.warning("Login failed: user=%s reason=unknown_user", username)
            return {"status": "invalid"}

        now = int(time.time())
        locked_until = int(user.get("locked_until", 0) or 0)
        if locked_until > now:
            audit_logger.warning("Login failed: user=%s reason=locked", username)
            return {"status": "locked", "until": locked_until}

        if user.get("disabled"):
            audit_logger.warning("Login failed: user=%s reason=disabled", username)
            return {"status": "disabled"}

        if not verify_password(password, user["password_hash"]):
            attempts = int(user.get("failed_attempts", 0)) + 1
            max_attempts = int(settings.lockout_max_attempts or 0)
            if max_attempts > 0 and attempts >= max_attempts:
                user["locked_until"] = now + int(settings.lockout_window_minutes or 0) * 60
                user["failed_attempts"] = 0
            else:
                user["failed_attempts"] = attempts
            save_users(users)
            audit_logger.warning("Login failed: user=%s reason=invalid_password", username)
            return {"status": "invalid"}

        if (settings.require_email_verification and not user.get("email_verified")
                and user.get("role") != "admin"):
            audit_logger.warning("Login failed: user=%s reason=unverified_email", username)
            return {"status": "unverified"}

        user["failed_attempts"] = 0
        user["locked_until"] = 0
        user["last_active"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        # A successful login is the only moment the plaintext is legitimately in
        # hand, so it is where a hash written under an older work factor gets
        # upgraded. Free: this branch already holds the lock and already saves.
        if needs_rehash(user["password_hash"]):
            user["password_hash"] = hash_password(password).decode()
            audit_logger.info("Rehashed password for user=%s at the current work factor", username)
        save_users(users)
        role = user.get("role", "guest")
        tv = int(user.get("token_version", 0))
        audit_logger.info("Login successful: user=%s role=%s", username, role)
        needs_pw_change = bool(user.get("password_change_required", False))

        # Burn the bootstrap credential once the account it belongs to has been
        # used. Scoped to that account deliberately: deleting it on *any*
        # successful login means a self-registered user logging in first
        # destroys the password before the operator has read it, locking them
        # out of the admin account with no reset path unless SMTP is set up.
        if username == "admin" and not needs_pw_change:
            from app.core.config import settings
            admin_file = Path(settings.data_root) / ".initial-admin"
            try:
                admin_file.unlink(missing_ok=True)
            except OSError:
                pass
        return {"status": "ok", "username": username, "role": role,
                "token": create_token(username, role, tv),
                "password_change_required": needs_pw_change}


def register_user(username: str, password: str, role: str = "contributor") -> dict | None:
    with users_lock():
        if len(password.encode()) > 72:
            return None
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
        audit_logger.info("Account created: user=%s role=%s", username, role)
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
    return {"username": username, "role": user.get("role", "guest"),
            "full_name": user.get("full_name", ""),
            "email_verified": user.get("email_verified", False)}


# --- User administration (admin-only management) ---

# "contributor" = standard read/write user; "maintainer" = elevated read/write
# with project-level privileges; "admin" = administrator. "guest" is the
# read-only role that unauthenticated users get.
ALLOWED_ROLES = ("guest", "contributor", "maintainer", "admin")


def public_users() -> list[dict]:
    """All users without their password hashes, sorted by username."""
    users = load_users()
    now = int(time.time())
    out = []
    for name, u in users.items():
        locked_until = int(u.get("locked_until", 0) or 0)
        out.append({
            "username": name, "role": u.get("role", "guest"),
            "full_name": u.get("full_name", ""),
            "email": u.get("email", ""), "email_verified": u.get("email_verified", False),
            "last_active": u.get("last_active", ""),
            "joined": u.get("created", ""),
            "created": u.get("created", ""),
            "disabled": bool(u.get("disabled", False)),
            "locked": locked_until > now,
            "locked_until": locked_until if locked_until > now else 0,
            "invited": bool(u.get("invited", False)),
        })
    return sorted(out, key=lambda x: x["username"].lower())


def create_invited_user(username: str, role: str = "contributor", email: str = "",
                        full_name: str = "") -> str | None:
    """Create an account with a random password that must be set via an invite
    link. Returns a set-password token, or None if the username is taken."""
    with users_lock():
        users = load_users()
        if username in users:
            return None
        users[username] = {
            "username": username,
            "password_hash": hash_password(secrets.token_urlsafe(24)).decode(),
            "role": role,
            "full_name": full_name,
            "email": email,
            "email_verified": False,
            "token_version": 0,
            "invited": True,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        save_users(users)
        audit_logger.info("Account created (invited): user=%s role=%s", username, role)
        return create_reset_token(username)


def count_admins(users: dict) -> int:
    return sum(1 for u in users.values() if u.get("role") == "admin")


def set_user_role(username: str, role: str) -> bool:
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        users[username]["role"] = role
        save_users(users)
        return True


def set_user_disabled(username: str, disabled: bool) -> bool:
    """Enable/disable an account. A disabled account cannot log in; disabling
    also revokes existing sessions by bumping the token version."""
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        users[username]["disabled"] = bool(disabled)
        if disabled:
            users[username]["token_version"] = users[username].get("token_version", 0) + 1
        save_users(users)
        return True


def unlock_user(username: str) -> bool:
    """Clear a failed-login lockout."""
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        users[username]["locked_until"] = 0
        users[username]["failed_attempts"] = 0
        save_users(users)
        return True


def bump_token_version(username: str) -> bool:
    """Invalidate every existing session for a user (force sign-out everywhere)."""
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        users[username]["token_version"] = users[username].get("token_version", 0) + 1
        save_users(users)
        return True


def set_user_password(username: str, password: str) -> bool:
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        users[username]["password_hash"] = hash_password(password).decode()
        users[username]["token_version"] = users[username].get("token_version", 0) + 1
        # Setting a password completes an invite and clears any lockout.
        users[username]["invited"] = False
        users[username]["locked_until"] = 0
        users[username]["failed_attempts"] = 0
        users[username]["password_change_required"] = False
        save_users(users)
        return True


def delete_user(username: str) -> bool:
    with users_lock():
        users = load_users()
        if username not in users:
            return False
        del users[username]
        save_users(users)
        return True


GUEST_USER = {"username": "guest", "role": "guest"}


# ═══════════════════════════════════════════════════════════════════════════════
# CSRF tokens + auth cookie helpers
# ═══════════════════════════════════════════════════════════════════════════════
# Stateless double-submit: the token is a random value echoed in a JS-readable
# cookie and compared against the X-CSRF-Token header (see main.csrf_middleware).
# Nothing is stored server-side, so this holds across workers and restarts.


def create_csrf_token(username: str) -> str:
    """Generate a CSRF token for *username*.

    Verification is the stateless double-submit check in
    ``main.csrf_middleware``: the value is echoed in a JS-readable cookie and
    compared against the ``X-CSRF-Token`` header. A cross-origin attacker can
    make the browser send the cookie but cannot read it to set the header, and
    cannot set the header at all without a CORS preflight the server refuses.

    That means the token only needs to be unguessable, not server-verifiable —
    so there is no per-user server-side store to keep, which is what lets this
    work across multiple workers and survive a restart.
    """
    return secrets.token_urlsafe(32)


def _cookie_domain() -> str | None:
    """Return the cookie domain, or None for a host-only cookie.

    None is returned for IP literals. RFC 6265's Domain attribute is defined for
    domain names, and pinning it to one address breaks every other address the
    same host answers on: a server with two addresses on one NIC handed out
    ``Domain=192.168.0.164`` while the operator browsed to ``192.168.0.163``, so
    login succeeded and every request after it returned 401 — the cookie was
    set and then never sent back. Omitting Domain makes the cookie host-only,
    which is what a single deployment wants and works whichever address or
    hostname was used to reach it.
    """
    from app.core.config import settings
    base = settings.base_url
    if not base or "://" not in base:
        return None

    authority = base.split("://", 1)[1].split("/", 1)[0]
    # A bracketed IPv6 literal must be unwrapped before the port is stripped —
    # splitting on ":" first turns "[2001:db8::1]" into "[2001".
    if authority.startswith("["):
        host = authority[1:].split("]", 1)[0]
    else:
        host = authority.split(":", 1)[0]

    # This is a string comparison to decide whether to return a host-only
    # cookie, not a bind address — bandit matches the literal "0.0.0.0".
    if host in ("localhost", "0.0.0.0", ""):  # nosec B104
        return None
    try:
        ipaddress.ip_address(host)
        return None                # an IP literal — host-only cookie
    except ValueError:
        return host


def set_auth_cookies(response, username: str, token: str) -> str:
    """Set auth cookies on a FastAPI/Starlette *response*.

    Returns the CSRF token that the caller should also return in the response
    body so the frontend can store it in-memory for WebSocket/cross-tab use.
    """
    from app.core.config import settings

    ttl = _token_ttl()
    secure = settings.cookie_secure
    domain = _cookie_domain()
    same_site = "strict" if secure else "lax"

    response.set_cookie(
        key="token",
        value=token,
        max_age=ttl,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/api",
        domain=domain,
    )

    csrf_token = create_csrf_token(username)
    response.set_cookie(
        key="csrftoken",
        value=csrf_token,
        max_age=ttl,
        httponly=False,
        secure=secure,
        samesite=same_site,
        path="/api",
        domain=domain,
    )

    return csrf_token


def clear_auth_cookies(response) -> None:
    """Remove auth cookies (logout)."""
    domain = _cookie_domain()
    response.delete_cookie("token", path="/api", domain=domain)
    response.delete_cookie("csrftoken", path="/api", domain=domain)


# ═══════════════════════════════════════════════════════════════════════════════
# Password reset tokens
# ═══════════════════════════════════════════════════════════════════════════════


def _load_token_store(path: Path) -> dict:
    if not path.exists():
        return {}
    # The `_yaml` instance is shared across the users file and both token files,
    # and ruamel keeps parser/emitter state on it — so a token load racing a
    # users dump corrupts it for both. Hold `_yaml_lock` here exactly as
    # load_users/save_users do; the per-file lock does not cover the shared
    # instance because it is keyed on the file, not the parser.
    with open(path) as f:
        with _yaml_lock:
            return _yaml.load(f) or {}


def _save_token_store(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            with _yaml_lock:
                _yaml.dump(data, f)
        os.replace(tmp, path)
        _chmod_private(path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        os.unlink(tmp)
        raise


def _token_key(token: str) -> str:
    """The stored form of a reset or verification token.

    The token itself is a bearer credential: whoever holds it can set a
    password without knowing the old one. Storing it verbatim meant anyone who
    could read ``reset_tokens.yaml`` — a stray backup, a misdirected volume
    mount — could take over any account with a live token. So the file holds
    only a digest, and the raw token exists solely in the email.

    Plain SHA-256 rather than bcrypt: the token is ``secrets.token_urlsafe(32)``,
    256 bits from a CSPRNG, so there is no guessing to slow down. A KDF here
    would only cost the server on every reset.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(username: str) -> str | None:
    users = load_users()
    if username not in users:
        return None
    token = secrets.token_urlsafe(32)
    now = time.time()
    # Guard the token file's read-modify-write. Inner to users_lock by
    # convention: this is reached from create_invited_user while it holds
    # users_lock, so the order is always users → token-file, never the reverse.
    # Inverting it would deadlock against consume_reset_token.
    with file_lock(RESET_TOKENS_FILE):
        tokens = _load_token_store(RESET_TOKENS_FILE)
        tokens[_token_key(token)] = {"username": username,
                                     "expires": int(time.time()) + RESET_TOKEN_TTL}
        tokens = {k: v for k, v in tokens.items() if v.get("expires", 0) > now}
        _save_token_store(RESET_TOKENS_FILE, tokens)
    return token


def consume_reset_token(token: str, new_password: str) -> bool:
    # Validate and burn the token under the token-file lock, then release it
    # *before* calling set_user_password (which takes users_lock). Holding the
    # token lock across that call would invert the users → token-file order and
    # deadlock against create_invited_user. The token is single-use, so burning
    # it before the password write is set is acceptable.
    key = _token_key(token)
    with file_lock(RESET_TOKENS_FILE):
        tokens = _load_token_store(RESET_TOKENS_FILE)
        entry = tokens.get(key)
        if not entry:
            return False
        expired = entry.get("expires", 0) < time.time()
        del tokens[key]
        _save_token_store(RESET_TOKENS_FILE, tokens)
    if expired:
        return False
    username = entry["username"]
    return set_user_password(username, new_password)


# ═══════════════════════════════════════════════════════════════════════════════
# Email verification
# ═══════════════════════════════════════════════════════════════════════════════


def create_verify_token(username: str) -> str | None:
    users = load_users()
    if username not in users:
        return None
    token = secrets.token_urlsafe(32)
    now = time.time()
    with file_lock(VERIFY_TOKENS_FILE):
        tokens = _load_token_store(VERIFY_TOKENS_FILE)
        tokens[_token_key(token)] = {"username": username,
                                     "expires": int(time.time()) + VERIFY_TOKEN_TTL}
        tokens = {k: v for k, v in tokens.items() if v.get("expires", 0) > now}
        _save_token_store(VERIFY_TOKENS_FILE, tokens)
    return token


def verify_email(token: str) -> str | None:
    # users_lock is the outer lock; the verify-token file lock nests inside it,
    # preserving the users → token-file order used everywhere else.
    key = _token_key(token)
    with users_lock():
        with file_lock(VERIFY_TOKENS_FILE):
            tokens = _load_token_store(VERIFY_TOKENS_FILE)
            entry = tokens.get(key)
            if not entry:
                return None
            if entry.get("expires", 0) < time.time():
                del tokens[key]
                _save_token_store(VERIFY_TOKENS_FILE, tokens)
                return None
            username = entry["username"]
            del tokens[key]
            _save_token_store(VERIFY_TOKENS_FILE, tokens)
        users = load_users()
        if username in users:
            users[username]["email_verified"] = True
            save_users(users)
            return username
        return None
