"""Runtime, admin-editable application settings layered over the env defaults.

The :class:`~app.core.config.Settings` object is populated from ``RT_*`` env vars
at startup. This module adds a persistent override file so an administrator can
change a curated set of settings from the UI without editing ``.env`` and
restarting — the overrides are applied onto the live ``settings`` object.

Env always wins for hard-pinned values: if ``RT_<KEY>`` is present in the
environment, that key is *env-locked* — its stored override is ignored and the
UI shows it read-only. This lets ops pin values in production while leaving the
rest UI-configurable.
"""

from __future__ import annotations

import os
from pathlib import Path

from ruamel.yaml import YAML

SETTINGS_FILE = Path.home() / ".reqmesh" / "settings.yaml"

_yaml = YAML()
_yaml.indent(mapping=2, sequence=4, offset=2)

# Curated, admin-editable settings. Each entry: type, UI category, label, and
# whether the value is secret (redacted on read). Only these keys can be changed
# at runtime — everything else stays env/startup-only.
OVERRIDABLE: dict[str, dict] = {
    # Branding / instance
    "instance_name": {"type": "str", "category": "branding", "label": "Instance name",
                      "help": "Shown in the header and emails."},
    "support_email": {"type": "str", "category": "branding", "label": "Support email",
                      "help": "Contact address shown to users."},
    # Features
    "allow_self_registration": {"type": "bool", "category": "features", "label": "Allow self-registration",
                                "help": "Let visitors create their own editor accounts."},
    "require_email_verification": {"type": "bool", "category": "features", "label": "Require email verification",
                                   "help": "Block non-admin login until the email is verified."},
    "offline_mode": {"type": "bool", "category": "features", "label": "Offline mode",
                     "help": "Suppress all outbound network calls (email, update checks)."},
    "self_update_enabled": {"type": "bool", "category": "features", "label": "Enable self-update",
                            "help": "Allow admins to update the instance from the System page."},
    # Email
    "base_url": {"type": "str", "category": "email", "label": "Public base URL",
                 "help": "Used to build links in emails."},
    "smtp_host": {"type": "str", "category": "email", "label": "SMTP host"},
    "smtp_port": {"type": "int", "category": "email", "label": "SMTP port"},
    "smtp_username": {"type": "str", "category": "email", "label": "SMTP username"},
    "smtp_password": {"type": "str", "category": "email", "label": "SMTP password", "secret": True},
    "smtp_from": {"type": "str", "category": "email", "label": "From address"},
    "smtp_use_tls": {"type": "bool", "category": "email", "label": "Use STARTTLS"},
    # Security
    "token_ttl_seconds": {"type": "int", "category": "security", "label": "Session length (seconds)"},
    "lockout_max_attempts": {"type": "int", "category": "security", "label": "Failed logins before lockout",
                             "help": "0 disables lockout."},
    "lockout_window_minutes": {"type": "int", "category": "security", "label": "Lockout duration (minutes)"},
    # Limits
    "max_upload_size_mb": {"type": "int", "category": "limits", "label": "Max upload size (MB)"},
    # Updates
    "github_repo": {"type": "str", "category": "updates", "label": "Update source repo (owner/name)"},
    "github_token": {"type": "str", "category": "updates", "label": "GitHub token", "secret": True},
    # Teams
    "teams": {"type": "list", "category": "teams", "label": "Teams",
              "help": "Organisational units that can be assigned to requirements. One per line."},
    # Reporting
    "report_company_name": {"type": "str", "category": "reporting", "label": "Company name",
                            "help": "Shown on the report cover page and page headers."},
    "report_department": {"type": "str", "category": "reporting", "label": "Department name",
                          "help": "Shown below the company name on the cover page."},
    "report_document_title": {"type": "str", "category": "reporting", "label": "Default document title",
                              "help": "Overrides 'Requirements Specification Report' when set."},
    "report_logo_url": {"type": "str", "category": "reporting", "label": "Company logo (URL or data: URI)",
                        "help": "Paste a URL or upload a PNG below."},
    "report_show_git_commit": {"type": "bool", "category": "reporting", "label": "Show git commit on each page",
                               "help": "Includes the short commit SHA in the page footer."},
}

_SECRET_MASK = "********"


def env_var(key: str) -> str:
    return "RT_" + key.upper()


def is_env_locked(key: str) -> bool:
    """True when the value is pinned via an environment variable."""
    return env_var(key) in os.environ


def _coerce(key: str, value):
    typ = OVERRIDABLE[key]["type"]
    if typ == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if typ == "int":
        return int(value)
    if typ == "list":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [v.strip() for v in value.replace("\r\n", "\n").split("\n") if v.strip()]
        return []
    return "" if value is None else str(value)


def load_overrides() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE) as f:
        return _yaml.load(f) or {}


def save_overrides(data: dict) -> None:
    import tempfile
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=SETTINGS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            _yaml.dump(data, f)
        os.replace(tmp, SETTINGS_FILE)
        try:
            os.chmod(SETTINGS_FILE, 0o600)  # may hold secrets
        except OSError:
            pass
    except BaseException:
        os.unlink(tmp)
        raise


def apply_overrides(settings=None) -> None:
    """Apply stored overrides onto the live settings object (env-locked keys skip)."""
    if settings is None:
        from app.core.config import settings as settings_obj
        settings = settings_obj
    overrides = load_overrides()
    for key, value in overrides.items():
        if key not in OVERRIDABLE or is_env_locked(key):
            continue
        try:
            coerced = _coerce(key, value)
            setattr(settings, key, coerced)
        except (ValueError, TypeError):
            continue


def set_overrides(patch: dict) -> dict:
    """Validate, persist, and apply a patch of overrides. Env-locked keys are
    ignored. Returns the effective (redacted) settings view."""
    from app.core.config import settings
    overrides = load_overrides()
    for key, value in patch.items():
        if key not in OVERRIDABLE:
            continue
        if is_env_locked(key):
            continue
        coerced = _coerce(key, value)
        # A blank secret means "leave unchanged".
        if OVERRIDABLE[key].get("secret") and coerced in ("", _SECRET_MASK):
            continue
        overrides[key] = coerced
        setattr(settings, key, coerced)
    save_overrides(overrides)
    return effective_settings()


def effective_settings() -> dict:
    """Current values for every overridable key, grouped by category, with
    secrets redacted and env-locked keys flagged."""
    from app.core.config import settings
    items: list[dict] = []
    for key, meta in OVERRIDABLE.items():
        raw = getattr(settings, key, None)
        secret = meta.get("secret", False)
        value = raw
        if meta["type"] == "list":
            value = raw if isinstance(raw, list) else []
        if secret:
            value = _SECRET_MASK if raw else ""
        items.append({
            "key": key,
            "value": value,
            "type": meta["type"],
            "category": meta["category"],
            "label": meta["label"],
            "help": meta.get("help", ""),
            "secret": secret,
            "env_locked": is_env_locked(key),
            "has_value": bool(raw) if secret else None,
        })
    return {"settings": items}
