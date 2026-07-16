import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import router
from app.api.extra_routes import router as extra_router
from app.api.auth_routes import router as auth_router
from app.api.component_routes import router as component_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = Path(settings.data_root)
    root.mkdir(parents=True, exist_ok=True)
    # First launch (no projects yet): seed the Cessna 172 example so the UI
    # opens with something to explore. Disable with RT_SEED_DEMO=false.
    if settings.seed_demo and not any((d / "_meta.yaml").exists() for d in root.iterdir() if d.is_dir()):
        try:
            from app.services.demo_seed import seed_demo_project
            seed_demo_project(root)
        except Exception:
            logging.getLogger(__name__).exception("Failed to seed demo project")
    yield


app = FastAPI(
    title="reqmesh",
    version="0.4.0",
    description="A git-native requirements management tool",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PROJECT_PATH_RE = re.compile(r"^/api/projects/([^/]+)(/.*)?$")


@app.middleware("http")
async def git_autocommit_middleware(request: Request, call_next):
    """After any successful mutation, auto-commit (if enabled) and publish SSE events."""
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        m = _PROJECT_PATH_RE.match(request.url.path)
        if m:
            project_id = unquote(m.group(1))
            project_root = Path(settings.data_root) / project_id
            action = unquote(m.group(2) or "").strip("/") or "project"

            if settings.git_autocommit and project_root.is_dir():
                from app.services.git_service import auto_commit
                await asyncio.to_thread(auto_commit, project_root, f"rt: {request.method.lower()} {action}")

            from app.services.event_bus import get_event_bus
            get_event_bus().publish(project_id, {
                "type": "mutation",
                "method": request.method,
                "path": request.url.path,
            })
    return response


app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")
app.include_router(component_router, prefix="/api")
app.include_router(extra_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Static SPA (desktop build) ────────────────────────────────────────────────
# Registered AFTER the API routers and /health so those always win — Starlette
# matches routes in registration order, so the catch-all below only handles
# paths the API didn't claim. No-op unless RT_STATIC_DIR points at a build.
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
        # Serve a real build asset when the path maps to one; otherwise fall
        # back to index.html so client-side (react-router) routes resolve.
        if full_path:
            candidate = (static_root / full_path).resolve()
            # Guard against path traversal escaping the build directory.
            if candidate.is_file() and candidate.is_relative_to(static_root):
                return FileResponse(candidate)
        return FileResponse(index_file)


_mount_spa()
