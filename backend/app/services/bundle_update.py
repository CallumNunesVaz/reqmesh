"""Bare-metal (non-Docker) self-update from an uploaded release bundle.

Docker deployments update through the privileged sidecar (see ``updater.py``). A
bare-metal install — a Python venv + uvicorn under systemd (``Restart=always``,
running out of an extracted release bundle) — has no sidecar, so it updates from
an uploaded ``reqmesh-vX.Y.Z.tar.gz`` bundle instead:

  1. The admin uploads the bundle. We stream it to disk, extract + validate it,
     snapshot every project's data (git tags), and *stage* the new tree under
     ``<install>/.updates/staged``. The running app is untouched — staging is
     non-disruptive.
  2. A ``pending.json`` marker records the staged update.
  3. On the next process start — the admin clicks *Restart*, or systemd restarts
     the unit — ``apply_pending_update`` runs before the app serves: it swaps the
     staged ``backend`` and ``frontend/dist`` into place (keeping a rollback
     copy), records the outcome, and re-execs so the new code is loaded.

Everything happens inside the install directory the service already owns; no
Docker socket and no privileged helper are involved.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.version import get_build_info, get_version
from app.services import updater

logger = logging.getLogger(__name__)

STAGED = "staged"      # bundle validated + staged, awaiting a restart to apply
COMPLETED = "completed"
FAILED = "failed"

_UPDATES_DIR = ".updates"
_INCOMING = "incoming.tar.gz"
_STAGED = "staged"
_PENDING = "pending.json"
_RESULT = "last-result.json"


# ── Install-root discovery ───────────────────────────────────────────────────

def install_root() -> Optional[Path]:
    """The extracted-bundle root: the directory holding both ``backend/app`` and
    ``frontend/dist``. Returns None when the layout isn't a bundle install."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "app").is_dir() and (parent / "frontend" / "dist").is_dir():
            return parent
    return None


def _updates_dir(root: Path) -> Path:
    return root / _UPDATES_DIR


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".rw-probe"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def bundle_update_supported() -> bool:
    """True when this is a writable bare-metal *release* install (not Docker,
    not a source checkout) that can update itself from an uploaded bundle."""
    if updater.is_running_in_docker():
        return False
    if not settings.self_update_enabled:
        return False
    # A bare source checkout reports channel "dev"; only real release bundles
    # carry a manifest.json and should offer in-place bundle updates.
    if get_build_info().get("channel") != "release":
        return False
    root = install_root()
    return bool(root and _writable(root / "backend") and _writable(root / "frontend"))


def can_restart() -> bool:
    """The app can restart itself in place (re-exec). Sidecar-driven Docker
    deployments manage their own lifecycle, so restart is a bare-metal affair."""
    return not updater.is_running_in_docker() and settings.self_update_enabled


# ── Status ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def pending_marker() -> Optional[dict]:
    root = install_root()
    if not root:
        return None
    marker = _updates_dir(root) / _PENDING
    return _read_json(marker) if marker.exists() else None


def bundle_status() -> Optional[dict]:
    """Bare-metal update state derived from the on-disk markers, or None when no
    bundle update has been staged/applied (so callers fall back to Docker state)."""
    root = install_root()
    if not root:
        return None
    current = get_version()
    pending = pending_marker()
    if pending:
        return {
            "state": STAGED,
            "current": current,
            "target_version": pending.get("target_version"),
            "message": f"Update to v{pending.get('target_version')} is staged — restart to apply.",
            "updated_at": pending.get("staged_at", _now_iso()),
            "backup": pending.get("backup"),
        }
    result = _read_json(_updates_dir(root) / _RESULT)
    if result:
        result.setdefault("current", current)
        return result
    return None


# ── Staging an uploaded bundle ───────────────────────────────────────────────

def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract without letting any member escape ``dest`` (path traversal)."""
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if dest not in target.parents and target != dest:
            raise RuntimeError(f"unsafe path in archive: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"archive contains a link, refused: {member.name}")
    # Python 3.12+ gained a data filter; pass it when available, else the checks
    # above already vetted every member.
    try:
        tar.extractall(dest, filter="data")  # type: ignore[arg-type]
    except TypeError:
        tar.extractall(dest)


def stage_from_archive(archive: Path, requested_by: str) -> dict:
    """Validate + stage an uploaded bundle tarball and record a pending update.

    Raises RuntimeError on any validation failure (with the archive removed).
    """
    root = install_root()
    if not bundle_update_supported() or not root:
        raise RuntimeError("Bundle-based update is not available in this deployment.")

    updates = _updates_dir(root)
    updates.mkdir(parents=True, exist_ok=True)
    extract_tmp = Path(tempfile.mkdtemp(prefix="reqmesh-extract-", dir=updates))
    try:
        try:
            with tarfile.open(archive, "r:*") as tar:
                _safe_extract(tar, extract_tmp)
        except (tarfile.TarError, OSError) as exc:
            raise RuntimeError(f"Could not read the bundle archive: {exc}")

        # A release bundle contains a single top-level reqmesh-vX.Y.Z/ directory.
        entries = [p for p in extract_tmp.iterdir() if p.is_dir()]
        if len(entries) != 1:
            raise RuntimeError("Unrecognized bundle layout (expected a single top-level folder).")
        src = entries[0]

        manifest = _read_json(src / "manifest.json")
        if not manifest or not manifest.get("version"):
            raise RuntimeError("Bundle is missing a valid manifest.json.")
        if not (src / "backend" / "app").is_dir() or not (src / "frontend" / "dist").is_dir():
            raise RuntimeError("Bundle is missing backend/ or frontend/dist — not a reqmesh release bundle.")

        target = str(manifest["version"])
        current = get_version()
        if not updater.is_newer(target, current):
            raise RuntimeError(f"Bundle v{target} is not newer than the running version v{current}.")

        # Snapshot project data before anything is staged, exactly as the online
        # and Docker paths do — a bad data migration stays rollback-able.
        backup = updater.create_backup(current)

        staged = updates / _STAGED
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        os.replace(src, staged)

        _write_json_atomic(updates / _PENDING, {
            "target_version": target,
            "from_version": current,
            "requested_by": requested_by,
            "staged_at": _now_iso(),
            "git_sha": manifest.get("git_sha", ""),
            "backup": backup,
        })
        # A freshly staged update supersedes any earlier completed/failed result.
        (updates / _RESULT).unlink(missing_ok=True)
        logger.info("bundle update staged: %s -> %s by %s", current, target, requested_by)
        return {"state": STAGED, "target_version": target, "backup": backup}
    finally:
        shutil.rmtree(extract_tmp, ignore_errors=True)
        archive.unlink(missing_ok=True)


# ── Applying a staged bundle (at process start) ──────────────────────────────

def _swap_dir(new: Path, live: Path, rollback: Path) -> None:
    """Move ``live`` aside into ``rollback`` and move ``new`` into its place."""
    rollback.parent.mkdir(parents=True, exist_ok=True)
    if live.exists():
        os.replace(live, rollback)
    os.replace(new, live)


def apply_pending_update() -> None:
    """If a bundle update is staged, swap it in and re-exec into the new code.

    Called at import time, before the app serves. Never raises — a failed apply
    is recorded and the old version keeps running so a bad bundle can't brick the
    instance. On success this re-execs and does not return.
    """
    root = install_root()
    if not root:
        return
    updates = _updates_dir(root)
    marker_path = updates / _PENDING
    if not marker_path.exists():
        return

    marker = _read_json(marker_path) or {}
    target = marker.get("target_version", "")
    current = get_version()
    backend_live = root / "backend"
    frontend_live = root / "frontend" / "dist"
    staged = updates / _STAGED
    rollback = updates / f"rollback-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    def _record(state: str, message: str) -> None:
        _write_json_atomic(updates / _RESULT, {
            "state": state, "target_version": target, "from_version": current,
            "message": message, "updated_at": _now_iso(),
        })

    if not (staged / "backend" / "app").is_dir() or not (staged / "frontend" / "dist").is_dir():
        logger.error("staged bundle at %s is incomplete; discarding", staged)
        _record(FAILED, "Staged update was incomplete and has been discarded.")
        marker_path.unlink(missing_ok=True)
        shutil.rmtree(staged, ignore_errors=True)
        return

    logger.info("applying staged bundle update %s -> %s", current, target)
    rollback.mkdir(parents=True, exist_ok=True)
    swapped: list[tuple[Path, Path]] = []  # (live, saved) for restore on failure
    meta_saved: list[tuple[Path, Path]] = []  # root metadata backed up before overwrite

    def _rollback() -> None:
        for live, saved in reversed(swapped):
            try:
                if live.exists():
                    shutil.rmtree(live, ignore_errors=True)
                if saved.exists():
                    os.replace(saved, live)
            except OSError:
                logger.exception("rollback of %s failed", live)
        for live, saved in meta_saved:  # restore old manifest.json / VERSION
            try:
                if saved.exists():
                    shutil.copy2(saved, live)
            except OSError:
                logger.exception("rollback of %s failed", live)

    try:
        _swap_dir(staged / "frontend" / "dist", frontend_live, rollback / "frontend-dist")
        swapped.append((frontend_live, rollback / "frontend-dist"))
        _swap_dir(staged / "backend", backend_live, rollback / "backend")
        swapped.append((backend_live, rollback / "backend"))
        # Root-level metadata so version.py reports the new build. Back up the old
        # copy first so a later rollback restores the reported version too.
        for name in ("manifest.json", "VERSION"):
            if (staged / name).exists():
                if (root / name).exists():
                    shutil.copy2(root / name, rollback / name)
                    meta_saved.append((root / name, rollback / name))
                shutil.copy2(staged / name, root / name)
    except OSError as exc:
        logger.exception("bundle swap failed; rolling back")
        _rollback()
        _record(FAILED, f"Update could not be applied and was rolled back: {exc}")
        marker_path.unlink(missing_ok=True)
        return

    # If the new version changed Python dependencies, sync the venv before we
    # re-exec — booting new code against stale deps would crash-loop. Failure
    # (e.g. air-gapped with no wheels) rolls the swap back instead of bricking.
    old_reqs = rollback / "backend" / "requirements.txt"
    new_reqs = backend_live / "requirements.txt"
    if new_reqs.exists() and _read_text(new_reqs) != _read_text(old_reqs):
        logger.info("requirements.txt changed; syncing dependencies")
        if not _sync_dependencies(new_reqs):
            _rollback()
            _record(FAILED, "New version needs updated dependencies that could not be "
                            "installed (offline?). The update was rolled back.")
            marker_path.unlink(missing_ok=True)
            return

    # Success: clear the marker (so the successor process doesn't re-apply),
    # record the outcome, and re-exec. Leave the rollback copy on disk for
    # recovery; a later successful update or dismissal can prune old ones.
    shutil.rmtree(staged, ignore_errors=True)
    _record(COMPLETED, f"Updated to v{target}.")
    marker_path.unlink(missing_ok=True)
    logger.info("bundle update applied; re-executing into v%s", target)
    # cwd currently points at the *old* backend inode (moved into rollback); move
    # to the new backend dir so uvicorn's import machinery loads the new code.
    try:
        os.chdir(backend_live)
    except OSError:
        pass
    reexec()


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text()
    except OSError:
        return None


def _sync_dependencies(requirements: Path) -> bool:
    """Install the new version's Python deps into the running venv. Best-effort:
    returns False (rather than raising) so the caller can roll back cleanly."""
    import subprocess

    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(requirements)]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("dependency sync failed to run: %s", exc)
        return False
    if result.returncode != 0:
        logger.error("dependency sync failed:\n%s", result.stderr.decode(errors="replace")[-2000:])
        return False
    return True


def reexec() -> None:
    """Replace the current process with a fresh copy of itself (same argv)."""
    argv = list(getattr(sys, "orig_argv", None) or [sys.executable, *sys.argv])
    logger.info("re-executing process: %s", " ".join(argv))
    try:
        os.execv(argv[0], argv)
    except OSError:
        os.execv(sys.executable, [sys.executable, *sys.argv])


def schedule_restart(delay: float = 0.7) -> None:
    """Re-exec the process shortly, after the HTTP response has been flushed."""
    import threading
    threading.Timer(delay, reexec).start()


def clear_bundle_state() -> None:
    """Remove staged/pending/result markers and any staged tree (dismiss)."""
    root = install_root()
    if not root:
        return
    updates = _updates_dir(root)
    for name in (_PENDING, _RESULT, _INCOMING):
        (updates / name).unlink(missing_ok=True)
    shutil.rmtree(updates / _STAGED, ignore_errors=True)
    # Prune rollback snapshots older than a day to reclaim space.
    cutoff = time.time() - 86400
    for child in updates.glob("rollback-*"):
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def incoming_path() -> Path:
    """Where an uploaded bundle archive is streamed before staging."""
    root = install_root()
    if not root:
        raise RuntimeError("Not a bundle install.")
    updates = _updates_dir(root)
    updates.mkdir(parents=True, exist_ok=True)
    return updates / _INCOMING
