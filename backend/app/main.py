import asyncio
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.ids import safe_id
from app.core.version import get_version, get_build_info
from app.api.router import router
from app.api.extra_routes import router as extra_router
from app.api.auth_routes import router as auth_router
from app.api.component_routes import router as component_router
from app.api.system_routes import router as system_router
from app.api.bulk_routes import router as bulk_router
from app.api.analysis_routes import router as analysis_router
from app.api.publish_routes import router as publish_router
from app.api.collab_routes import router as collab_router

# Apply a staged bare-metal bundle update, if one is pending, before the app is
# built or serves any request. On success this swaps in the new code and
# re-execs (never returning); with nothing staged it's a cheap no-op.
try:
    from app.services.bundle_update import apply_pending_update
    apply_pending_update()
except Exception:  # noqa: BLE001 - a failed apply must never block startup
    logging.getLogger(__name__).exception("bundle update apply check failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply admin-saved runtime setting overrides onto the live config first, so
    # everything downstream (email, features, limits) sees the effective values.
    try:
        from app.core.settings_store import apply_overrides
        apply_overrides(settings)
    except Exception:
        logging.getLogger(__name__).exception("failed to apply runtime settings overrides")
    security_log = logging.getLogger("security")
    if settings.profile == "personal" and settings.host not in ("127.0.0.1", "localhost"):
        security_log.warning("Personal profile with non-loopback host '%s' — network exposure risk", settings.host)
    if not settings.require_auth:
        security_log.warning("Anonymous access is enabled")
    if settings.allow_self_registration and settings.profile != "personal":
        security_log.warning("Self-registration enabled on non-personal profile '%s'", settings.profile)
    if settings.profile == "hardened" and not settings.cookie_secure:
        security_log.warning("Hardened profile with insecure cookies (cookie_secure=False)")
    if not settings.rate_limit_enabled:
        security_log.warning(
            "Rate limiting is DISABLED — login brute-force and export flooding are unthrottled. "
            "This is intended only for the end-to-end test suite.")
    if settings.require_auth and settings.rate_limit_enabled:
        # X-Forwarded-For is only honoured from a trusted peer, but the default
        # trusts every RFC1918 range. Any host in those ranges that can reach the
        # app port directly (not only via the intended proxy) can then spoof its
        # client IP and mint a fresh login rate-limit bucket per request. Pin the
        # trust list to the proxy's exact address.
        from app.core.rate_limit import _trusted_proxies
        non_loopback = [str(n) for n in _trusted_proxies() if not n.is_loopback]
        if non_loopback:
            security_log.warning(
                "X-Forwarded-For is trusted from non-loopback range(s) %s "
                "(RT_PROXY_TRUSTED_CIDR). A host in those ranges reaching the app "
                "port directly can spoof its client IP and evade per-IP login "
                "rate limiting. Narrow this to your reverse proxy's exact address.",
                ", ".join(non_loopback))
    root = Path(settings.data_root)
    root.mkdir(parents=True, exist_ok=True)

    # The state dir holds password hashes and the signing secret. If it sits
    # inside the data root, a project directory contains users.yaml — and
    # git auto-commit runs `git add -A` in project directories, so the hashes
    # would be committed and pushed to whatever remote the project has.
    # Unrecoverable once pushed, so refuse to start rather than warn.
    #
    # Only this direction is wrong. The default bare-metal layout is the
    # *inverse* — data_root = <state_dir>/projects — which is safe, because a
    # repo is only ever a single project directory. A symmetric "must be
    # disjoint" check would refuse every default install.
    from app.core import auth as _auth
    state_dir = _auth.USERS_FILE.parent.resolve()
    data_root = root.resolve()
    if state_dir == data_root or data_root in state_dir.parents:
        raise RuntimeError(
            f"RT_STATE_DIR ({state_dir}) is inside RT_DATA_ROOT ({data_root}). "
            "Accounts and the signing secret would live in a project directory, "
            "where git auto-commit would commit and push password hashes. "
            "Point RT_STATE_DIR somewhere outside the data root."
        )

    # Repair and migrate the state dir before anything reads accounts from it.
    try:
        from app.services.state_migrations import run_state_migrations
        state_summary = run_state_migrations(state_dir)
        if state_summary.get("migrated"):
            logging.getLogger(__name__).info("applied state migrations: %s", state_summary)
    except Exception:
        logging.getLogger(__name__).exception("state migration failed")

    # Bring existing data forward to the current schema before serving — this is
    # what makes updating from an older program version clean.
    try:
        from app.services.migrations import run_migrations
        summary = run_migrations(root)
        if summary.get("ran"):
            logging.getLogger(__name__).info("applied data migrations: %s", summary)
    except Exception:
        logging.getLogger(__name__).exception("data migration failed")
    if settings.seed_demo and not any((d / "_meta.yaml").exists() for d in root.iterdir() if d.is_dir()):
        try:
            from app.services.demo_seed import seed_demo_project
            seed_demo_project(root)
        except Exception:
            logging.getLogger(__name__).exception("Failed to seed demo project")

    flusher = asyncio.create_task(_git_flush_loop())
    try:
        yield
    finally:
        flusher.cancel()
        try:
            await flusher
        except asyncio.CancelledError:
            pass
        # Commit whatever is still outstanding. A clean shutdown must not be
        # the reason an edit never reached git history.
        try:
            await flush_pending_commits(force=True)
        except Exception:  # noqa: BLE001 - never block shutdown
            logging.getLogger(__name__).exception("final git flush failed")


app = FastAPI(
    title="reqmesh",
    version=get_version(),
    description="A git-native requirements management tool with traceability, verification tracking, parametrics, and real-time collaboration.",
    lifespan=lifespan,
    contact={"name": "reqmesh", "url": "https://github.com/CallumNunesVaz/reqmesh"},
    license_info={"name": "GPL-3.0-or-later", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
    openapi_tags=[
        {"name": "auth", "description": "Authentication — login, register, guest access, user management"},
        {"name": "projects", "description": "Project CRUD and lifecycle"},
        {"name": "requirements", "description": "Requirements — the core entity"},
    ],
)

app.add_middleware(GZipMiddleware, minimum_size=512)
# Fail-fast on a dangerous CORS configuration. Sessions are cookie-based, so
# credentials are always sent; a wildcard origin would tell the browser to
# accept authenticated cross-origin requests from anywhere. Starlette silently
# degrades the wildcard to an origin echo in this combination, which is *worse*
# than the spec-mandated refusal — every origin gets reflected back. Refuse to
# start rather than serve it.
if "*" in settings.cors_origins:
    raise RuntimeError(
        "RT_CORS_ORIGINS contains '*', but reqmesh always sends credentials "
        "(cookie sessions), so a wildcard origin would allow authenticated "
        "requests from any site. Set RT_CORS_ORIGINS to an explicit allowlist, "
        "or leave it empty for a single-origin deployment."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.allowed_hosts and settings.allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

class BodySizeLimitMiddleware:
    """Cap JSON request bodies as they arrive, not from ``Content-Length``.

    Counting the bytes of every ``http.request`` message as they stream in keeps
    the limit honest for a chunked body that declares no length at all. The cap
    is read from ``settings.max_json_body_mb`` on every request, so a runtime
    override (or a test flipping the setting) takes effect without a restart.
    Non-HTTP scopes (WebSocket) and non-JSON content types pass through
    untouched.
    """

    def __init__(self, app, *, max_bytes: int) -> None:
        # The cap is re-read from settings on every request (see __call__), so
        # ``max_bytes`` is deliberately not stored: a runtime override must take
        # effect without rebuilding the middleware stack.
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if "application/json" not in headers.get("content-type", ""):
            await self.app(scope, receive, send)
            return

        max_bytes = settings.max_json_body_mb * 1024 * 1024
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._refuse(scope, send, 400, "Invalid Content-Length")
                return
            if declared > max_bytes:
                await self._refuse(scope, send, 413, "Request body too large")
                return

        received = 0
        refused = False

        async def limited_receive():
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    await self._refuse(scope, send, 413, "Request body too large")
                    refused = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            # Once the 413 has been sent the response is committed; the
            # downstream app will still try to answer (FastAPI turns the
            # disconnect into its own error response), so drop anything that
            # arrives after the refusal.
            if refused:
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if refused:
                return
            raise

    @staticmethod
    async def _refuse(scope, send, status_code: int, detail: str) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, None, send)


# Endpoints reachable without a session — the ones used to *obtain* one, plus
# build metadata for probes. Everything else under /api is gated when
# RT_REQUIRE_AUTH is on.
_PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/guest",
    "/api/auth/whoami",          # answers "guest" rather than 401, so the SPA can boot
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
    "/api/version",
})


@app.middleware("http")
async def require_auth_middleware(request: Request, call_next):
    """Enforce ``RT_REQUIRE_AUTH`` across the API.

    Previously this setting only refused *guest logins*, so every read endpoint
    stayed anonymous and "no anonymous read" was never true. Applied as
    middleware rather than a per-route dependency because there are ~148 routes
    and none of the ~90 GETs carried a guard — one that has to be remembered on
    each new route is one that eventually isn't.
    """
    if not settings.require_auth or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/") or path in _PUBLIC_API_PATHS:
        return await call_next(request)

    from app.core.dependencies import get_current_user
    user = get_current_user(request=request,
                            authorization=request.headers.get("Authorization"))
    if user.get("role", "guest") == "guest":
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    return await call_next(request)


# Auth routes that don't require CSRF (they create the token):
_CSRF_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/guest",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
})


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)
    if request.url.path in _CSRF_EXEMPT_PATHS:
        return await call_next(request)

    # Key the check off the *session* cookie, not the CSRF cookie. Keying off
    # the CSRF cookie meant a request carrying a valid session cookie but no
    # csrftoken cookie skipped the check entirely and was still authenticated.
    # A request that isn't cookie-authenticated (bearer token, or anonymous)
    # can't be forged cross-origin, so it needs no CSRF check.
    if not request.cookies.get("token"):
        return await call_next(request)

    csrf_cookie = request.cookies.get("csrftoken")
    csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})

    return await call_next(request)


_PROJECT_PATH_RE = re.compile(r"^/api/projects/([^/]+)(/.*)?$")

from app.services.git_auto_commit import (  # noqa: E402 - module-level machinery
    commit_due as _commit_due,
    git_schedule_for as _git_schedule_for,
    commit_project as _commit_project,
    flush_pending_commits,
    git_flush_loop as _git_flush_loop,
    record_change as _record_git_change,
    last_commit_times,
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)
    logging.getLogger("http").info(
        "%s %s → %s (%dms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    csp = settings.csp_default or "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
    response.headers.setdefault("Content-Security-Policy", csp)
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000")
    return response


@app.middleware("http")
async def git_autocommit_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        m = _PROJECT_PATH_RE.match(request.url.path)
        if m:
            # `request.url.path` has ALREADY been percent-decoded by the ASGI
            # server, so decoding again here turns "%252e%252e%252f" into "../"
            # and escapes the data root. Nothing else guards this path: a
            # trailing-slash 307 satisfies the `status_code < 400` check above
            # without any route handler, auth dependency or `safe_id` running.
            # Validate the segment; never decode it a second time.
            try:
                project_id = safe_id(m.group(1), "project id")
            except HTTPException:
                return response

            data_root = Path(settings.data_root).resolve()
            project_root = data_root / project_id
            # Defence in depth: refuse anything that resolves outside the root
            # (e.g. a symlinked project directory).
            try:
                if not project_root.resolve().is_relative_to(data_root):
                    return response
            except OSError:
                return response

            # Only used to build the commit message; strip anything that could
            # break out of a single-line message.
            action = re.sub(r"[^\w./ -]", "", (m.group(2) or "").strip("/"))[:80] or "project"

            if settings.git_autocommit and project_root.is_dir():
                # Per-project git settings from _meta.yaml override global config
                try:
                    from app.services.git_service import _project_git_config
                    git_cfg = _project_git_config(project_root)
                except Exception:
                    git_cfg = {}
                auto_commit_enabled = git_cfg.get("auto_commit", settings.git_autocommit)
                if auto_commit_enabled:
                    schedule, interval_hours, changes_threshold = _git_schedule_for(git_cfg)

                    username = ""
                    auth = request.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        try:
                            from app.core.auth import get_user_from_token
                            user = get_user_from_token(auth.removeprefix("Bearer "))
                            username = user.get("username", "") if user else ""
                        except Exception:
                            pass

                    from app.services.git_service import push_to_remote, schedule_push
                    msg = f"rt: {request.method.lower()} {action}"
                    if username:
                        msg += f" ({username})"

                    # Record the change as pending *before* deciding, so that a
                    # commit suppressed by the debounce is still guaranteed to
                    # happen — flush_pending_commits picks it up on the next
                    # poll, and at shutdown. Without that the change simply sat
                    # in the working tree until some unrelated later mutation.
                    count = _record_git_change(project_id, project_root)

                    committed = False
                    if _commit_due(
                        schedule,
                        count=count,
                        interval_hours=interval_hours,
                        changes_threshold=changes_threshold,
                        now=time.monotonic(),
                        last=last_commit_times().get(project_id, 0),
                    ):
                        committed = await _commit_project(
                            project_id, project_root, msg, username=username)
                    push_on_commit = git_cfg.get("push_on_commit", settings.git_push_on_commit)
                    push_interval = git_cfg.get("push_interval_minutes", settings.git_push_interval_minutes)
                    remote_url = git_cfg.get("remote_url") or settings.git_remote_url
                    if committed and remote_url:
                        if push_interval > 0:
                            # Batched: only queues + arms a timer, safe inline.
                            schedule_push(project_root, push_interval)
                        elif push_on_commit:
                            await asyncio.to_thread(push_to_remote, project_root)

            from app.services.event_bus import get_event_bus
            get_event_bus().publish(project_id, {
                "type": "mutation",
                "method": request.method,
                "path": request.url.path,
            })
    return response


# Registered last (and therefore outermost) so the body cap fires before auth:
# an oversized unauthenticated request is refused without ever reading its
# credentials or routing it. The decorator middlewares above are registered
# earlier and run inside this one.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=0)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None) or {},
        )
    logging.getLogger(__name__).exception("Unhandled exception: %s %s", request.method, request.url.path)
    detail = str(exc) if settings.debug else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")
app.include_router(component_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(extra_router, prefix="/api")
app.include_router(bulk_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(publish_router, prefix="/api")
app.include_router(collab_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": get_version(), "profile": settings.profile}


@app.get("/version")
async def version():
    """Build metadata for this instance — version, git sha, build time, channel."""
    return get_build_info()


def _mount_spa() -> None:
    if not settings.static_dir:
        return
    static_root = Path(settings.static_dir).resolve()
    index_file = static_root / "index.html"
    if not index_file.is_file():
        logging.getLogger(__name__).warning(
            "RT_STATIC_DIR=%s has no index.html; not serving SPA", settings.static_dir
        )
        return

    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path:
            candidate = (static_root / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(static_root):
                if candidate.name.startswith("."):
                    return JSONResponse(status_code=404, content={"detail": "Not found"})
                if full_path.endswith((".js", ".css", ".woff2", ".woff", ".ttf", ".svg", ".png")):
                    return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})
                return FileResponse(candidate)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})


_mount_spa()
