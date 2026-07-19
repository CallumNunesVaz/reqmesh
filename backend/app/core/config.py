from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_root: str = str(Path.home() / ".reqmesh" / "projects")
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Commit project changes automatically when the project dir is a git repo.
    git_autocommit: bool = True
    # Push auto-commits to a configured remote after each change.
    git_remote_url: str = ""
    git_push_on_commit: bool = False
    git_push_interval_minutes: int = 0  # 0 = immediate (when push_on_commit is true)
    # Seed the Cessna 172 example project when the data root has no projects.
    seed_demo: bool = True
    # When set to a built frontend directory (e.g. frontend/dist), the backend
    # also serves the SPA from the same origin as the API. Used by the desktop
    # (Electron) build so it loads a single origin; empty in the web/server
    # deployment, where Vite serves the UI separately.
    static_dir: str = ""
    code_root: str = ""
    # Run without making any outbound network calls (no git push, no SMTP, no
    # external resources loaded from CDNs).
    offline_mode: bool = False
    # Public URL of this instance, used for generating links in emails.
    base_url: str = "http://localhost:8000"
    # SMTP configuration for email notifications.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "reqmesh@localhost"
    smtp_use_tls: bool = True
    # Rate limiting: max requests per window for auth endpoints.
    rate_limit_auth: str = "5/minute"
    # Max upload size in megabytes.
    max_upload_size_mb: int = 50
    # Auth
    token_ttl_seconds: int = 604800
    allow_self_registration: bool = True
    require_email_verification: bool = False
    # Logging
    log_level: str = "INFO"
    debug: bool = False
    # Production safeguards
    allowed_hosts: list[str] = ["*"]

    model_config = {"env_prefix": "RT_", "env_file": ".env"}


settings = Settings()
