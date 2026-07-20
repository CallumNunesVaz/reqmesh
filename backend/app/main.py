import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.version import get_version, get_build_info
from app.api.router import router
from app.api.extra_routes import router as extra_router
from app.api.auth_routes import router as auth_router
from app.api.component_routes import router as component_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = Path(settings.data_root)
    root.mkdir(parents=True, exist_ok=True)
    if settings.seed_demo and not any((d / "_meta.yaml").exists() for d in root.iterdir() if d.is_dir()):
        try:
            from app.services.demo_seed import seed_demo_project
            seed_demo_project(root)
        except Exception:
            logging.getLogger(__name__).exception("Failed to seed demo project")
    yield


app = FastAPI(
    title="reqmesh",
    version=get_version(),
    description="A git-native requirements management tool with traceability, verification tracking, parametrics, and real-time collaboration.",
    lifespan=lifespan,
    contact={"name": "reqmesh", "url": "https://github.com/CallumNunesVaz/reqmesh"},
    license_info={"name": "GNU GPL-2.0", "url": "https://www.gnu.org/licenses/gpl-2.0.html"},
    openapi_tags=[
        {"name": "auth", "description": "Authentication — login, register, guest access, user management"},
        {"name": "projects", "description": "Project CRUD and lifecycle"},
        {"name": "requirements", "description": "Requirements — the core entity"},
    ],
)

app.add_middleware(GZipMiddleware, minimum_size=512)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PROJECT_PATH_RE = re.compile(r"^/api/projects/([^/]+)(/.*)?$")


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
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000")
    return response


@app.middleware("http")
async def git_autocommit_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        m = _PROJECT_PATH_RE.match(request.url.path)
        if m:
            project_id = unquote(m.group(1))
            project_root = Path(settings.data_root) / project_id
            action = unquote(m.group(2) or "").strip("/") or "project"

            if settings.git_autocommit and project_root.is_dir():
                # Per-project git settings from _meta.yaml override global config
                try:
                    from app.services.git_service import _project_git_config
                    git_cfg = _project_git_config(project_root)
                except Exception:
                    git_cfg = {}
                auto_commit_enabled = git_cfg.get("auto_commit", settings.git_autocommit)
                if auto_commit_enabled:
                    username = ""
                    auth = request.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        try:
                            from app.core.auth import get_user_from_token
                            user = get_user_from_token(auth.removeprefix("Bearer "))
                            username = user.get("username", "") if user else ""
                        except Exception:
                            pass

                    from app.services.git_service import auto_commit, push_to_remote, schedule_push
                    msg = f"rt: {request.method.lower()} {action}"
                    if username:
                        msg += f" ({username})"
                    committed = await asyncio.to_thread(
                        auto_commit, project_root, msg, username=username
                    )
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
app.include_router(extra_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": get_version()}


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
