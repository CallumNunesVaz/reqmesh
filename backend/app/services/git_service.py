from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback identity so auto-commits work in containers with no git config.
_FALLBACK_NAME = "reqmesh"
_FALLBACK_EMAIL = "reqmesh@localhost"


def is_repo(project_root: Path) -> bool:
    return (Path(project_root) / ".git").exists()


# Batched push state
_push_queue: set[Path] = set()
_push_timer: threading.Timer | None = None
_push_lock = threading.Lock()


def _identity_for(project_root: Path, username: str = "") -> list[str]:
    """Build git identity args for a commit.
    
    Priority: 1) per-project meta.yaml git settings, 2) passed username,
    3) global fallback.
    """
    name = _FALLBACK_NAME
    email = _FALLBACK_EMAIL

    try:
        from app.services.yaml_store import YamlStore
        store = YamlStore(project_root)
        meta = store.read_meta()
        git_cfg = meta.get("git", {})
        if git_cfg.get("user_name"):
            name = git_cfg["user_name"]
        if git_cfg.get("user_email"):
            email = git_cfg["user_email"]
    except Exception:
        pass

    if username and name == _FALLBACK_NAME:
        name = username

    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *_identity_for(project_root), *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=30,
    )


def auto_commit(project_root: Path, message: str, username: str = "") -> bool:
    """Best-effort commit of all pending changes in a project working tree.
    
    Only acts when the project directory itself is a git repository. Returns
    True if a commit was created. Uses per-project git identity from _meta.yaml
    when configured, falling back to the acting username.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        # Build identity flags for this specific commit
        ident = _identity_for(project_root, username)
        subprocess.run(["git", *ident, "add", "-A"], cwd=str(project_root),
                       capture_output=True, text=True, timeout=30)
        result = subprocess.run(["git", *ident, "commit", "-m", message],
                               cwd=str(project_root), capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            if "nothing to commit" not in result.stdout + result.stderr:
                logger.warning("git auto-commit failed in %s: %s", project_root, result.stderr.strip())
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git auto-commit error in %s: %s", project_root, exc)
        return False


def log(project_root: Path, limit: int = 50) -> list[dict]:
    """Recent commits for a project, newest first. Empty if not a repo."""
    project_root = Path(project_root)
    if not is_repo(project_root):
        return []
    result = _git(project_root, "log", f"-{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s")
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]})
    return commits


def ensure_remote(project_root: Path, remote_url: str) -> bool:
    """Ensure a git remote named 'origin' is configured.
    
    If no remote exists, adds one. If one exists with a different URL, updates it.
    Returns True if a remote was added or updated.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        result = _git(project_root, "remote", "get-url", "origin")
        if result.returncode == 0:
            current = result.stdout.strip()
            if current == remote_url:
                return False
            _git(project_root, "remote", "set-url", "origin", remote_url)
            logger.info("git remote origin updated to %s in %s", remote_url, project_root)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        _git(project_root, "remote", "add", "origin", remote_url)
        logger.info("git remote origin set to %s in %s", remote_url, project_root)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git remote add failed in %s: %s", project_root, exc)
        return False


def _project_git_config(project_root: Path) -> dict:
    """Read git configuration from the project's _meta.yaml."""
    try:
        from app.services.yaml_store import YamlStore
        store = YamlStore(project_root)
        meta = store.read_meta()
        return meta.get("git", {})
    except Exception:
        return {}


def push_to_remote(project_root: Path, branch: str = "main") -> bool:
    """Push commits to the configured remote.
    
    Returns True if a push was attempted successfully. Logs warnings on failure
    (no exception raised — push failures are non-fatal).
    """
    from app.core.config import settings

    if settings.offline_mode:
        return False

    project_root = Path(project_root)
    if not is_repo(project_root):
        return False

    cfg = _project_git_config(project_root)
    remote_url = cfg.get("remote_url") or settings.git_remote_url
    if not remote_url:
        return False

    try:
        ensure_remote(project_root, remote_url)

        # Determine the current branch if not specified
        actual_branch = branch
        branch_result = _git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            actual_branch = branch_result.stdout.strip()

        result = _git(project_root, "push", "-u", "origin", actual_branch)
        if result.returncode != 0:
            logger.warning("git push failed in %s: %s", project_root, result.stderr.strip())
            return False

        logger.info("git push succeeded in %s (%s)", project_root, actual_branch)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git push error in %s: %s", project_root, exc)
        return False


def schedule_push(project_root: Path, interval_minutes: int | None = None) -> None:
    """Queue a project for a batched push, or push immediately.

    With a positive interval, pushes are batched — calling this repeatedly
    within the window only pushes once when the timer fires (cheap: only
    queues, safe to call from the event loop). With interval 0 the push runs
    synchronously via push_to_remote(), so call that path from a worker
    thread. When interval_minutes is None the global setting applies.
    """
    if interval_minutes is None:
        from app.core.config import settings
        interval_minutes = settings.git_push_interval_minutes
    if interval_minutes <= 0:
        push_to_remote(project_root)
        return
    with _push_lock:
        _push_queue.add(Path(project_root))
        _ensure_timer(interval_minutes)


def _ensure_timer(interval_minutes: int) -> None:
    global _push_timer
    if _push_timer is not None:
        return
    _push_timer = threading.Timer(interval_minutes * 60.0, _flush_all)
    _push_timer.daemon = True
    _push_timer.start()


def _flush_all() -> None:
    global _push_timer
    with _push_lock:
        roots = list(_push_queue)
        _push_queue.clear()
        _push_timer = None
    for root in roots:
        push_to_remote(root)


def restore_commit(project_root: Path, commit_hash: str, username: str = "") -> bool:
    """Restore the working tree to the state of a past commit.

    Does ``git checkout <hash> -- .`` then creates a new commit recording the
    restoration so the operation itself is always reversible.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        ident = _identity_for(project_root, username)
        r = subprocess.run(
            ["git", *ident, "checkout", commit_hash, "--", "."],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            logger.warning("git checkout %s failed in %s: %s", commit_hash, project_root, r.stderr.strip())
            return False
        subprocess.run(
            ["git", *ident, "add", "-A"],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        who = username or _FALLBACK_NAME
        msg = f"rt: restored to {commit_hash[:8]} ({who})"
        subprocess.run(
            ["git", *ident, "commit", "-m", msg, "--allow-empty"],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git restore error in %s: %s", project_root, exc)
        return False
