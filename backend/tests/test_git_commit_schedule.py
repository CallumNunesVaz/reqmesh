"""Auto-commit scheduling: every pending change must eventually reach git.

The schedules are evaluated on incoming requests, so before the flusher existed
a suppressed commit was never retried — three quick edits produced one commit
and left the rest in the working tree indefinitely, which for a tool that
advertises "auto-committed to git on every change" is silent data loss.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.core.config import settings
from app.core.dependencies import (require_admin, require_edit,
                                   require_maintain, require_maintain_global)
from app.main import app, _commit_due, flush_pending_commits


def _git_log(root: Path) -> list[str]:
    out = subprocess.run(["git", "log", "--oneline"], cwd=root,
                         capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


def _dirty(root: Path) -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                         capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


@pytest.fixture()
def git_project(tmp_path, monkeypatch):
    """A real git repo served by the app, with auto-commit on."""
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "require_auth", False)
    monkeypatch.setattr(settings, "git_autocommit", True)
    monkeypatch.setattr(settings, "git_commit_schedule", "every_change")
    admin = {"username": "tester", "role": "admin"}
    for dep in (require_edit, require_maintain, require_maintain_global, require_admin):
        app.dependency_overrides[dep] = lambda: admin

    main_mod._git_change_counts.clear()
    main_mod._git_last_commit_time.clear()
    main_mod._git_pending_roots.clear()
    main_mod._git_locks.clear()

    client = TestClient(app)
    client.post("/api/projects", json={"id": "p", "name": "P"})
    root = Path(settings.data_root) / "p"
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    yield client, root
    app.dependency_overrides.clear()


def _make(client, n: int) -> None:
    for i in range(n):
        r = client.post("/api/projects/p/requirements",
                        json={"id": f"SYST{i:04d}", "title": f"r{i}"})
        assert r.status_code == 201, r.text


# ── The defect ───────────────────────────────────────────────────────────────

def test_rapid_edits_are_all_committed_by_the_flusher(git_project, monkeypatch):
    """Edits suppressed by the debounce must still reach git.

    Previously they sat in the working tree until an unrelated later mutation
    happened to fall outside the window — or forever, if the user stopped.
    """
    client, root = git_project
    _make(client, 3)

    # The debounce deliberately leaves the tail uncommitted for now...
    assert _dirty(root), "expected the debounce to suppress at least one commit"

    # ...but the flusher must pick it up once the window has passed.
    monkeypatch.setattr(main_mod, "_GIT_DEBOUNCE_S", 0.0)
    asyncio.run(flush_pending_commits())

    assert _dirty(root) == [], f"still uncommitted: {_dirty(root)}"
    assert len(_git_log(root)) >= 2


def test_shutdown_commits_outstanding_changes(tmp_path, monkeypatch):
    """Stopping the server must not be the reason an edit never reached git."""
    monkeypatch.setattr(settings, "data_root", str(tmp_path / "projects"))
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "require_auth", False)
    monkeypatch.setattr(settings, "git_autocommit", True)
    monkeypatch.setattr(settings, "git_commit_schedule", "every_change")
    admin = {"username": "tester", "role": "admin"}
    for dep in (require_edit, require_maintain, require_maintain_global, require_admin):
        app.dependency_overrides[dep] = lambda: admin
    main_mod._git_change_counts.clear()
    main_mod._git_last_commit_time.clear()
    main_mod._git_pending_roots.clear()

    # `with` runs lifespan startup and shutdown.
    with TestClient(app) as client:
        client.post("/api/projects", json={"id": "p", "name": "P"})
        root = Path(settings.data_root) / "p"
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        _make(client, 3)
        assert _dirty(root), "fixture precondition: something is pending"

    assert _dirty(root) == [], f"shutdown left work uncommitted: {_dirty(root)}"
    app.dependency_overrides.clear()


def test_flusher_is_a_noop_when_nothing_is_pending(git_project):
    client, root = git_project
    _make(client, 1)
    asyncio.run(flush_pending_commits(force=True))
    before = _git_log(root)
    asyncio.run(flush_pending_commits(force=True))
    assert _git_log(root) == before, "empty flush created a commit"


# ── The schedule predicate ───────────────────────────────────────────────────

def test_nothing_pending_is_never_due():
    assert _commit_due("every_change", count=0, interval_hours=0,
                       changes_threshold=0, now=1e6, last=0) is False


def test_every_change_waits_for_the_debounce_then_fires():
    assert _commit_due("every_change", count=1, interval_hours=0,
                       changes_threshold=0, now=1.0, last=0.0) is False
    assert _commit_due("every_change", count=1, interval_hours=0,
                       changes_threshold=0, now=99.0, last=0.0) is True


def test_interval_schedule():
    hour = 3600.0
    assert _commit_due("interval", count=5, interval_hours=6,
                       changes_threshold=0, now=5 * hour, last=0.0) is False
    assert _commit_due("interval", count=5, interval_hours=6,
                       changes_threshold=0, now=7 * hour, last=0.0) is True
    # An unset interval must not mean "every request".
    assert _commit_due("interval", count=5, interval_hours=0,
                       changes_threshold=0, now=1e9, last=0.0) is False


def test_changes_schedule():
    assert _commit_due("changes", count=9, interval_hours=0,
                       changes_threshold=10, now=1e9, last=0.0) is False
    assert _commit_due("changes", count=10, interval_hours=0,
                       changes_threshold=10, now=1e9, last=0.0) is True
    assert _commit_due("changes", count=999, interval_hours=0,
                       changes_threshold=0, now=1e9, last=0.0) is False


def test_both_schedule_fires_on_either_trigger():
    hour = 3600.0
    assert _commit_due("both", count=3, interval_hours=6, changes_threshold=10,
                       now=hour, last=0.0) is False
    assert _commit_due("both", count=10, interval_hours=6, changes_threshold=10,
                       now=hour, last=0.0) is True          # count only
    assert _commit_due("both", count=3, interval_hours=6, changes_threshold=10,
                       now=7 * hour, last=0.0) is True      # time only


@pytest.mark.parametrize("bogus", ["daily", "", "EVERY_CHANGE", "on_demand"])
def test_unknown_schedule_falls_back_instead_of_disabling_commits(bogus):
    """The if/elif chain had no else, so a typo silently stopped all commits."""
    assert _commit_due(bogus, count=1, interval_hours=0,
                       changes_threshold=0, now=99.0, last=0.0) is True


def test_unknown_schedule_warns(caplog):
    with caplog.at_level("WARNING"):
        _commit_due("nonsense", count=1, interval_hours=0,
                    changes_threshold=0, now=99.0, last=0.0)
    assert any("commit_schedule" in r.getMessage() for r in caplog.records)
