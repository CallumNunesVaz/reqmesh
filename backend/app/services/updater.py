"""Self-update support: check GitHub for newer releases and drive a supervised,
Docker-based update of the running instance.

Security model: the app process never touches the Docker socket. To update, it
verifies an update is available, snapshots project data (git tags), then writes
an *update request* into a control directory shared with a small `updater`
sidecar (see docker-compose.prod.yml). The sidecar — which alone holds the
socket — pulls the new image and recreates the app container. The app reports
progress by reading the sidecar's status file and its own running version.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.version import get_version

logger = logging.getLogger(__name__)

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")

# States surfaced to the admin UI.
IDLE = "idle"
PREPARING = "preparing"      # app is backing up / staging
REQUESTED = "requested"      # control request written, awaiting the sidecar
IN_PROGRESS = "in_progress"  # sidecar is pulling / recreating
COMPLETED = "completed"
FAILED = "failed"
UNSUPPORTED = "unsupported"

_REQUEST_FILE = "update-request.json"
_STATUS_FILE = "update-status.json"
_TARGET_FILE = "update-target"  # plain version string; the sidecar's trigger

# Cached GitHub check: (timestamp, payload)
_check_cache: tuple[float, dict] | None = None


# ── Version comparison ───────────────────────────────────────────────────────

def parse_semver(v: str) -> Optional[tuple[int, int, int]]:
    m = _SEMVER_RE.match(v.strip()) if v else None
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def compare_versions(a: str, b: str) -> int:
    """-1 if a<b, 0 if equal (or unparseable), 1 if a>b (release-precision only)."""
    pa, pb = parse_semver(a), parse_semver(b)
    if pa is None or pb is None:
        return 0
    return (pa > pb) - (pa < pb)


def is_newer(candidate: str, current: str) -> bool:
    return compare_versions(candidate, current) > 0


# ── GitHub release lookup ────────────────────────────────────────────────────

def _github_latest_release() -> dict:
    """Fetch the latest published release from GitHub. Raises on network/API error."""
    url = f"https://api.github.com/repos/{settings.github_repo}/releases/latest"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "reqmesh-updater",
    })
    if settings.github_token:
        req.add_header("Authorization", f"Bearer {settings.github_token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_for_update(force: bool = False) -> dict:
    """Compare the running version against the latest GitHub release.

    Cached for update_check_ttl_seconds. In offline mode, reports the current
    version with checking disabled rather than making a network call.
    """
    global _check_cache
    current = get_version()

    if settings.offline_mode:
        return {
            "current": current, "latest": None, "update_available": False,
            "offline": True, "checked_at": _now_iso(), "error": None,
            "notes": "", "html_url": "", "published_at": "",
        }

    now = time.time()
    if not force and _check_cache is not None and now - _check_cache[0] < settings.update_check_ttl_seconds:
        return _check_cache[1]

    result = {
        "current": current, "latest": None, "update_available": False,
        "offline": False, "checked_at": _now_iso(), "error": None,
        "notes": "", "html_url": "", "published_at": "",
    }
    try:
        rel = _github_latest_release()
        latest = (rel.get("tag_name") or "").lstrip("v")
        result["latest"] = latest
        result["update_available"] = bool(latest) and is_newer(latest, current)
        result["notes"] = rel.get("body") or ""
        result["html_url"] = rel.get("html_url") or ""
        result["published_at"] = rel.get("published_at") or ""
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            result["error"] = "No published releases found for the repository."
        else:
            result["error"] = f"GitHub API error ({exc.code})."
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result["error"] = f"Update check failed: {exc}"

    _check_cache = (now, result)
    return result


# ── Runtime detection ────────────────────────────────────────────────────────

def is_running_in_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        return "docker" in Path("/proc/1/cgroup").read_text()
    except OSError:
        return False


def _control_dir() -> Path:
    return Path(settings.update_control_dir)


def control_dir_writable() -> bool:
    d = _control_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".rw-probe"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def self_update_supported() -> bool:
    """A supervised in-app update is possible only under Docker with a writable
    control directory (the updater sidecar), self-update enabled, and online."""
    return (
        settings.self_update_enabled
        and not settings.offline_mode
        and is_running_in_docker()
        and control_dir_writable()
    )


def runtime_info() -> dict:
    docker = is_running_in_docker()
    return {
        "version": get_version(),
        "docker": docker,
        "offline": settings.offline_mode,
        "self_update_enabled": settings.self_update_enabled,
        "control_dir_writable": control_dir_writable() if (docker and settings.self_update_enabled) else False,
        "self_update_supported": self_update_supported(),
        "github_repo": settings.github_repo,
    }


# ── Data backup (git tags per project) ───────────────────────────────────────

def create_backup(from_version: str) -> dict:
    """Snapshot each project's git repo with an annotated pre-update tag.

    Cheap and precise: project data lives in git repos, so a tag is a restorable
    point-in-time marker. Data also persists on its own volume across the
    container swap; the tags exist to roll back a bad data migration.
    """
    from app.services.git_service import is_repo, _git

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tag = f"pre-update-{from_version}-{stamp}"
    data_root = Path(settings.data_root)
    tagged: list[str] = []
    if data_root.is_dir():
        for project in sorted(p for p in data_root.iterdir() if p.is_dir()):
            if not is_repo(project):
                continue
            try:
                res = _git(project, "tag", "-a", tag, "-m", f"reqmesh backup before update from {from_version}")
                if res.returncode == 0:
                    tagged.append(project.name)
            except Exception as exc:  # noqa: BLE001 - backup is best-effort
                logger.warning("backup tag failed for %s: %s", project.name, exc)
    return {"tag": tag, "projects": tagged, "created_at": _now_iso()}


# ── Update request / status protocol ─────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def request_update(target_version: str, requested_by: str) -> dict:
    """Back up data and write an update request for the sidecar to act on."""
    if not self_update_supported():
        raise RuntimeError("Self-update is not supported in this deployment.")

    current = get_version()
    if not is_newer(target_version, current):
        raise RuntimeError(f"{target_version} is not newer than the running version {current}.")

    backup = create_backup(current)

    image = f"ghcr.io/{settings.github_repo.lower()}:{target_version}"
    request = {
        "target_version": target_version,
        "image": image,
        "from_version": current,
        "requested_by": requested_by,
        "requested_at": _now_iso(),
        "backup": backup,
    }
    control = _control_dir()
    # Seed a status the UI can read immediately; the sidecar overwrites it.
    _write_json_atomic(control / _STATUS_FILE, {
        "state": REQUESTED, "target_version": target_version,
        "message": "Update requested; waiting for the updater.", "updated_at": _now_iso(),
    })
    _write_json_atomic(control / _REQUEST_FILE, request)
    # Plain trigger the shell sidecar reads without parsing JSON. Written last so
    # the sidecar never sees a target before the request/status are in place.
    (control / _TARGET_FILE).write_text(target_version + "\n")
    logger.info("update requested: %s -> %s by %s", current, target_version, requested_by)
    return {"state": REQUESTED, "target_version": target_version, "backup": backup}


def get_update_status() -> dict:
    """Current update state, combining the sidecar's status file with the fact
    that a completed update manifests as the running version having changed."""
    current = get_version()
    if not self_update_supported():
        return {"state": UNSUPPORTED, "current": current, "target_version": None,
                "message": "Self-update is not available in this deployment.", "updated_at": _now_iso()}

    control = _control_dir()
    status_path = control / _STATUS_FILE
    if not status_path.exists():
        return {"state": IDLE, "current": current, "target_version": None,
                "message": "", "updated_at": _now_iso()}

    try:
        status = json.loads(status_path.read_text())
    except (OSError, ValueError):
        return {"state": IDLE, "current": current, "target_version": None,
                "message": "", "updated_at": _now_iso()}

    target = status.get("target_version")
    # If we're already running the target, the swap succeeded regardless of what
    # the (now-replaced) sidecar last wrote.
    if target and compare_versions(current, target) >= 0 and status.get("state") not in (FAILED,):
        status["state"] = COMPLETED
        status["message"] = f"Updated to {current}."
    status["current"] = current
    return status


def clear_update_state() -> None:
    """Reset the control files (e.g. to dismiss a completed/failed update)."""
    control = _control_dir()
    for name in (_REQUEST_FILE, _STATUS_FILE, _TARGET_FILE):
        try:
            (control / name).unlink()
        except OSError:
            pass
