from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback identity so auto-commits work in containers with no git config.
_IDENTITY = ["-c", "user.name=reqmesh", "-c", "user.email=reqmesh@localhost"]


def is_repo(project_root: Path) -> bool:
    return (Path(project_root) / ".git").exists()


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=30,
    )


def auto_commit(project_root: Path, message: str) -> bool:
    """Best-effort commit of all pending changes in a project working tree.

    Only acts when the project directory itself is a git repository. Returns
    True if a commit was created.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        _git(project_root, "add", "-A")
        result = _git(project_root, "commit", "-m", message)
        if result.returncode != 0:
            # "nothing to commit" is normal; anything else is worth a log line.
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


def push_to_remote(project_root: Path, branch: str = "main") -> bool:
    """Push commits to the configured remote.
    
    Returns True if a push was attempted successfully. Logs warnings on failure
    (no exception raised — push failures are non-fatal).
    """
    from app.core.config import settings

    if settings.offline_mode:
        return False

    project_root = Path(project_root)
    if not is_repo(project_root) or not settings.git_remote_url:
        return False

    try:
        ensure_remote(project_root, settings.git_remote_url)

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
