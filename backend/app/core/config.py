from __future__ import annotations

from pathlib import Path
from typing import get_args, get_origin

from pydantic import SecretStr
from pydantic_settings import BaseSettings, DotEnvSettingsSource, EnvSettingsSource


# Per-profile defaults, applied in `Settings.model_post_init` to any field the
# operator has *not* set explicitly. Anything given via env/.env always wins, so
# a profile is a starting posture rather than a straitjacket.
PROFILE_PRESETS: dict[str, dict] = {
    # Single user on localhost: anonymous read, open registration, and plain
    # HTTP assumed (Secure cookies would be dropped over http:// on a LAN address).
    "personal": {
        "require_auth": False,
        "allow_self_registration": True,
        "cookie_secure": False,
    },
    # Shared instance behind TLS: log in to read, admin creates accounts.
    "team": {
        "require_auth": True,
        "allow_self_registration": False,
        "cookie_secure": True,
    },
    # As team, plus verified email addresses and an upgrade-insecure-requests CSP.
    "hardened": {
        "require_auth": True,
        "allow_self_registration": False,
        "cookie_secure": True,
        "require_email_verification": True,
        "csp_default": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'; "
            "upgrade-insecure-requests"
        ),
    },
}

PROFILES = tuple(PROFILE_PRESETS)


class _ListEnvMixin:
    """Accept the two forms operators actually write for ``list[str]`` settings.

    pydantic-settings JSON-decodes complex fields inside the *source*, before
    any validator runs, so anything that is not valid JSON raises SettingsError
    at import and the process never starts — with a pydantic traceback that
    names the field but not the reason. Every generated deployment tripped one
    of the two cases below, so the installer could not produce a bootable
    configuration in *any* combination:

        RT_ALLOWED_HOSTS=                          (no domain — the LAN case
                                                    the wizard recommends)
        RT_ALLOWED_HOSTS=example.com,192.168.0.5   (a domain — comma-separated,
                                                    which is what the wizard
                                                    writes and what every
                                                    12-factor env var uses)

    So: blank means "not set", and falls back to the field default. Both
    consumers already read the resulting value correctly — `main.py` skips
    TrustedHostMiddleware unless `allowed_hosts` is a real restriction, and the
    wildcard guard's own error message tells operators to leave `cors_origins`
    empty for a single-origin deployment.

    A non-blank value is JSON if it looks like JSON, and a comma-separated list
    otherwise. Restricted to ``list[str]`` so dict-valued settings keep their
    JSON-only contract, where guessing would be ambiguous.
    """

    @staticmethod
    def _is_str_list(field) -> bool:
        return get_origin(field.annotation) is list and get_args(field.annotation) == (str,)

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        # `value_is_complex` alone is not the condition: for a plain env var the
        # source sets it False and decides from the *field* type, so the JSON
        # decode still fired.
        if isinstance(value, str) and (value_is_complex or self.field_is_complex(field)):
            stripped = value.strip()
            if not stripped:
                return None
            if self._is_str_list(field) and stripped[0] not in "[{\"'":
                return [part.strip() for part in stripped.split(",") if part.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


# Applied to both sources: os.environ (Docker `environment:`) and the .env file
# (systemd `EnvironmentFile=`, which is the bare-metal installer's path).
class _EmptyTolerantEnvSource(_ListEnvMixin, EnvSettingsSource):
    pass


class _EmptyTolerantDotEnvSource(_ListEnvMixin, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    # ── Deployment profile ─────────────────────────────────────────────────
    # Sets the default posture for auth, registration and cookies; see
    # PROFILE_PRESETS above for exactly what each one changes. Explicit
    # RT_* env vars always override the profile.
    #
    # personal  – localhost single user: anonymous read, self-registration on,
    #             non-Secure cookies (works over plain HTTP)
    # team      – shared + TLS: login required, self-registration off (default)
    # hardened  – team, plus mandatory email verification and a stricter CSP
    #
    # NB: there is no MFA in reqmesh yet, so no profile can require it.
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

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        """Swap in the empty-tolerant env source, for both env and .env files.

        Order is unchanged — this only replaces *how* each source reads a blank
        complex value, not which source wins.
        """
        return (
            init_settings,
            _EmptyTolerantEnvSource(settings_cls),
            _EmptyTolerantDotEnvSource(settings_cls),
            file_secret_settings,
        )

    def model_post_init(self, __context) -> None:
        """Apply the deployment profile's defaults.

        Only fields the operator left alone are touched — ``model_fields_set``
        holds everything supplied via env/.env, so an explicit
        ``RT_COOKIE_SECURE=false`` survives regardless of profile. Without this
        the profile was documentation only: it named a posture that no code
        ever applied.
        """
        preset = PROFILE_PRESETS.get(self.profile)
        if preset is None:
            import logging
            logging.getLogger("security").warning(
                "Unknown RT_PROFILE %r — falling back to 'team'. Valid: %s",
                self.profile, ", ".join(PROFILES),
            )
            preset = PROFILE_PRESETS["team"]
        explicit = self.model_fields_set
        for field, value in preset.items():
            if field not in explicit:
                # object.__setattr__ bypasses validate_assignment, which would
                # otherwise mark these as explicitly-set and defeat the check.
                object.__setattr__(self, field, value)


settings = Settings()
