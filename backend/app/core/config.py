from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Deployment profile ─────────────────────────────────────────────────
    # personal  – single-user localhost, anonymous read, self-registration on
    # team      – authenticated, TLS assumed, self-registration off (default)
    # hardened  – MFA mandatory, no self-registration, no anonymous read,
    #             strict CSP, audit-everything
    profile: str = "team"

    data_root: str = str(Path.home() / ".reqmesh" / "projects")
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # If set, reject requests whose Host header doesn't match.
    allowed_hosts: list[str] = ["*"]

    # ── Authentication ────────────────────────────────────────────────────
    # When true, every endpoint requires a valid session (no guest access).
    # Defaults to true in "team" and "hardened" profiles.
    require_auth: bool = True
    # Allow new accounts to be created from the login page.
    # Defaults to false in "team" and "hardened" profiles.
    allow_self_registration: bool = False
    require_email_verification: bool = False
    # Self-registration email-domain allowlist (empty = any domain when enabled).
    registration_domain_allowlist: list[str] = []
    # JWT lifetime, in seconds (default 7 days).
    token_ttl_seconds: int = 604800
    # Set Secure flag on auth cookies. Defaults to true in "team" and "hardened".
    cookie_secure: bool = True
    # Account lockout: lock for this many minutes after too many failed logins.
    lockout_max_attempts: int = 5
    lockout_window_minutes: int = 15
    # Per-account progressive lockout (exponential backoff on repeated locks).
    lockout_progressive: bool = True

    # ── CSRF protection ───────────────────────────────────────────────────
    # The value used to sign CSRF tokens (auto-generated at startup if empty).
    csrf_secret: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────
    rate_limit_auth: str = "5/minute"
    rate_limit_analysis: str = "20/minute"
    rate_limit_publish: str = "5/minute"
    # Maximum concurrent SSE connections per user.
    max_sse_conns_per_user: int = 5
    max_sse_conns_global: int = 100

    # ── Proxy / forwarded headers ─────────────────────────────────────────
    # Comma-separated list of trusted proxy CIDRs whose X-Forwarded-For header
    # is used to derive the real client IP for rate limiting.
    proxy_trusted_cidr: str = "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    # ── Request limits ────────────────────────────────────────────────────
    max_upload_size_mb: int = 50
    max_json_body_mb: int = 10

    # ── Content-Security-Policy ───────────────────────────────────────────
    # CSP directive overrides (empty = use profile-appropriate defaults).
    csp_default: str = ""

    # ── Git ───────────────────────────────────────────────────────────────
    git_autocommit: bool = True
    git_remote_url: str = ""
    git_push_on_commit: bool = False
    git_push_interval_minutes: int = 0

    # ── Misc ──────────────────────────────────────────────────────────────
    seed_demo: bool = True
    static_dir: str = ""
    code_root: str = ""
    offline_mode: bool = False
    base_url: str = "http://localhost:8000"
    instance_name: str = "reqmesh"
    support_email: str = ""

    # ── SMTP ──────────────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "reqmesh@localhost"
    smtp_use_tls: bool = True

    # ── Branding ──────────────────────────────────────────────────────────
    report_company_name: str = ""
    report_department: str = ""
    report_document_title: str = ""
    report_logo_url: str = ""
    report_show_git_commit: bool = False
    report_document_number: str = ""
    report_revision: str = ""
    report_classification: str = ""
    report_status: str = ""
    report_prepared_by: str = ""
    report_reviewed_by: str = ""
    report_approved_by: str = ""
    report_distribution: list[str] = []

    # ── Self-update ───────────────────────────────────────────────────────
    github_repo: str = "CallumNunesVaz/reqmesh"
    github_token: str = ""
    self_update_enabled: bool = True
    update_control_dir: str = "/control"
    update_check_ttl_seconds: int = 3600
    max_update_upload_mb: int = 2048

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    debug: bool = False

    # ── Teams ─────────────────────────────────────────────────────────────
    teams: list[str] = ["Systems Engineering"]

    # validate_assignment ensures runtime overrides (settings_store) that assign a
    # plain str to smtp_password are re-coerced back into a SecretStr, so the field
    # is always masked regardless of how it was set.
    model_config = {"env_prefix": "RT_", "env_file": ".env", "validate_assignment": True}


settings = Settings()
