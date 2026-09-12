"""``git_service.restore_commit`` must actually restore the tree.

``git checkout <hash> -- .`` is additive: it restores paths present in the old
commit but leaves files added afterwards in place, and the following
``git add -A`` commits them, so "restore" silently kept post-snapshot files.
There was no test, which is why the gap was invisible.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.services import git_service


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "tester")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD").strip()


def test_restore_removes_files_added_after_the_snapshot(tmp_path):
    root = tmp_path / "p"
    _init_repo(root)
    (root / "a.yaml").write_text("one")
    first = _commit(root, "a")

    (root / "b.yaml").write_text("two")
    _commit(root, "b")

    assert git_service.restore_commit(root, first, "tester") is True
    assert (root / "a.yaml").read_text() == "one"
    assert not (root / "b.yaml").exists()


def test_restore_reverts_content_changed_after_the_snapshot(tmp_path):
    root = tmp_path / "p"
    _init_repo(root)
    (root / "a.yaml").write_text("one")
    first = _commit(root, "a")
    (root / "a.yaml").write_text("changed")
    _commit(root, "change")

    assert git_service.restore_commit(root, first, "tester") is True
    assert (root / "a.yaml").read_text() == "one"


def test_restore_records_a_reversible_commit(tmp_path):
    root = tmp_path / "p"
    _init_repo(root)
    (root / "a.yaml").write_text("one")
    first = _commit(root, "a")
    (root / "b.yaml").write_text("two")
    _commit(root, "b")

    assert git_service.restore_commit(root, first, "tester") is True
    # A new commit records the restoration, so the operation is reversible.
    log = _git(root, "log", "--oneline")
    assert "restored to" in log
    # And the working tree is clean against the snapshot.
    assert _git(root, "status", "--porcelain").strip() == ""
