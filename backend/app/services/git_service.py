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
