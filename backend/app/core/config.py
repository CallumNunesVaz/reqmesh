from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: str = str(Path.home() / ".reqmesh" / "projects")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Commit project changes automatically when the project dir is a git repo.
    git_autocommit: bool = True
    # Seed the Cessna 172 example project when the data root has no projects.
    seed_demo: bool = True
    # When set to a built frontend directory (e.g. frontend/dist), the backend
    # also serves the SPA from the same origin as the API. Used by the desktop
    # (Electron) build so it loads a single origin; empty in the web/server
    # deployment, where Vite serves the UI separately.
    static_dir: str = ""
    code_root: str = ""

    model_config = {"env_prefix": "RT_", "env_file": ".env"}


settings = Settings()
