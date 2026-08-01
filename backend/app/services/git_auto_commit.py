"""Git auto-commit scheduling and background flush loop.

Extracted from ``main.py`` so the application bootstrap file contains
middleware wiring, not scheduling policy. The middleware still lives in
``main.py`` (it wraps every request), but all of the scheduling logic —
schedule evaluation, commit execution, the background flush loop — is here.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Per-project serialisation: git can't handle concurrent commits on the same
# tree (they collide on .git/index.lock and one is silently dropped).
_git_locks: dict[str, asyncio.Lock] = {}

# Per-project state for schedule-aware commits — the middleware increments the
# change counter on every mutating request and evaluates the configured schedule
# (every_change, interval, changes, or both) to decide whether to fire a commit.
_git_change_counts: dict[str, int] = {}
_git_last_commit_time: dict[str, float] = {}

# Project roots for projects with uncommitted changes, so the background flusher
# can find them without walking data_root.
_git_pending_roots: dict[str, Path] = {}

_GIT_DEBOUNCE_S = 3.0
# How often the flusher re-evaluates pending work. Well under the shortest
# meaningful interval, and cheap: it does nothing when nothing is pending.
_GIT_FLUSH_POLL_S = 15.0

GIT_SCHEDULES = ("every_change", "interval", "changes", "both")


def commit_due(schedule: str, *, count: int, interval_hours: float,
               changes_threshold: int, now: float, last: float) -> bool:
    """Whether a project's pending changes should be committed now.

    Shared by the request path and the background flusher so the two cannot
    disagree about what a schedule means. An unrecognised schedule falls back to
    ``every_change`` rather than matching no branch at all — the previous
    if/elif chain had no else, so a single typo in `_meta.yaml` left
    `should_commit` False forever and silently disabled auto-commit entirely.
    """
    if schedule not in GIT_SCHEDULES:
        logger.warning(
            "Unknown git commit_schedule %r — falling back to 'every_change'. Valid: %s",
            schedule, ", ".join(GIT_SCHEDULES),
        )
        schedule = "every_change"

    if count <= 0:
        return False
    if schedule == "every_change":
        return now - last >= _GIT_DEBOUNCE_S
    time_ok = interval_hours > 0 and now - last >= interval_hours * 3600
    count_ok = changes_threshold > 0 and count >= changes_threshold
    if schedule == "interval":
        return time_ok
    if schedule == "changes":
        return count_ok
    return time_ok or count_ok


def git_schedule_for(git_cfg: dict) -> tuple[str, float, int]:
    from app.core.config import settings
    return (
        str(git_cfg.get("commit_schedule", settings.git_commit_schedule) or "every_change"),
        float(git_cfg.get("commit_interval_hours", settings.git_commit_interval_hours) or 0),
        int(git_cfg.get("commit_changes_threshold", settings.git_commit_changes_threshold) or 0),
    )


async def commit_project(project_id: str, project_root: Path, msg: str, username: str = "") -> bool:
    """Commit under the project's lock and reset its pending state."""
    from app.services.git_service import auto_commit

    lock = _git_locks.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _git_locks[project_id] = lock
    async with lock:
        committed = await asyncio.to_thread(auto_commit, project_root, msg, username=username)
        # Reset regardless of `committed`: a False return means git found
        # nothing to commit, so there is no longer anything pending either.
        # Leaving the counter set made every later request retry a full
        # `git add -A` scan that could never succeed.
        _git_last_commit_time[project_id] = time.monotonic()
        _git_change_counts[project_id] = 0
        _git_pending_roots.pop(project_id, None)
    return committed


async def flush_pending_commits(*, force: bool = False) -> list[str]:
    """Commit any project whose pending changes are now due.

    This is what makes the schedules real. Every path in the middleware is
    driven by an incoming request, so without this a suppressed commit was
    never retried: three quick edits produced one commit and left the rest
    uncommitted indefinitely, and an `interval` schedule fired only on the next
    mutation *after* the interval elapsed rather than when it elapsed.

    `force` ignores the schedule and commits everything outstanding; used at
    shutdown so stopping the server never strands a user's last edit.
    """
    from app.services.git_service import _project_git_config

    committed: list[str] = []
    for project_id, project_root in list(_git_pending_roots.items()):
        try:
            if not project_root.is_dir():
                _git_pending_roots.pop(project_id, None)
                continue
            if not force:
                try:
                    git_cfg = _project_git_config(project_root)
                except Exception:
                    git_cfg = {}
                schedule, interval_hours, threshold = git_schedule_for(git_cfg)
                if not commit_due(
                    schedule,
                    count=_git_change_counts.get(project_id, 0),
                    interval_hours=interval_hours,
                    changes_threshold=threshold,
                    now=time.monotonic(),
                    last=_git_last_commit_time.get(project_id, 0),
                ):
                    continue
            count = _git_change_counts.get(project_id, 0)
            msg = f"rt: {count} pending change{'s' if count != 1 else ''}"
            if await commit_project(project_id, project_root, msg):
                committed.append(project_id)
        except Exception:  # noqa: BLE001 - one bad project must not stall the rest
            logger.exception(
                "deferred git commit failed for %s", project_id)
    return committed


async def git_flush_loop() -> None:
    while True:
        try:
            await asyncio.sleep(_GIT_FLUSH_POLL_S)
            await flush_pending_commits()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the loop must outlive any single failure
            logger.exception("git flush loop iteration failed")


def record_change(project_id: str, project_root: Path) -> int:
    """Increment the pending-change counter and record the root for the flusher.

    Called by the middleware on every successful mutating request. Returns the
    new count so the caller can evaluate the commit schedule.
    """
    count = _git_change_counts.get(project_id, 0) + 1
    _git_change_counts[project_id] = count
    _git_pending_roots[project_id] = project_root
    return count


def change_counts() -> dict[str, int]:
    return dict(_git_change_counts)


def last_commit_times() -> dict[str, float]:
    return dict(_git_last_commit_time)


def pending_roots() -> dict[str, Path]:
    return dict(_git_pending_roots)
