"""Migrations for the *state* directory — accounts, secrets, tokens.

Deliberately separate from ``services/migrations.py``, which migrates project
data and keys its marker on the data root. The two directories have independent
lifetimes: an operator can restore ``projects/`` from a backup without the state
dir, or move a state dir between a bare-metal and a Docker deployment. Sharing a
marker would mean one restore silently marks the other's migrations as done.

The directory is always passed in by the caller — never re-read from the
environment — so tests can point it at a tmp_path and the CLI can repair the same
directory the server uses.

Adding a migration: bump CURRENT_STATE_VERSION and register a function under the
new number. Each step must be idempotent and must not raise on a read-only or
partially-populated directory: failing to migrate is not a reason to refuse to
serve, and the caller logs rather than blocks.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CURRENT_STATE_VERSION = 2
_MARKER = ".reqmesh-state.json"

#: Files that must never be readable by anyone but the owner. `users.yaml` holds
#: password hashes, `secret` signs every session, and the token stores hold live
#: password-reset credentials.
_PRIVATE_FILES = ("users.yaml", "secret", "reset_tokens.yaml", "verify_tokens.yaml")


def _chmod_private(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning("could not tighten permissions on %s: %s", path, exc)


def _migrate_1_to_2(state_dir: Path) -> None:
    """Reset and verification tokens are now stored hashed.

    Entries written before that change are keyed by the raw token, and a hashed
    key is indistinguishable from a raw one by shape, so they cannot be upgraded
    in place — they are dropped instead. The tokens live for an hour (reset) and
    a day (verification), so the cost is that anyone mid-flow asks for another
    link. **Outstanding invitations must be re-sent.**

    Also repairs file modes: an installation whose `users.yaml` was created by
    the old bootstrap path took the process umask, typically 0644.
    """
    for name in ("reset_tokens.yaml", "verify_tokens.yaml"):
        path = state_dir / name
        try:
            if path.exists():
                dropped = path.read_text().count("username:")
                path.unlink()
                logger.warning(
                    "state migration: removed %s (%d plaintext token(s) invalidated; "
                    "any outstanding password-reset or invitation links must be re-sent)",
                    name, dropped,
                )
        except OSError as exc:
            logger.warning("state migration: could not remove %s: %s", path, exc)

    for name in _PRIVATE_FILES:
        _chmod_private(state_dir / name)


# ── Migration registry ───────────────────────────────────────────────────────
# MIGRATIONS[n] upgrades state from version (n-1) to version n.
MIGRATIONS: dict[int, Callable[[Path], None]] = {
    2: _migrate_1_to_2,
}


def _marker_path(state_dir: Path) -> Path:
    return Path(state_dir) / _MARKER


def read_state_version(state_dir: Path) -> int | None:
    try:
        return int(json.loads(_marker_path(state_dir).read_text())["state_version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_state_version(state_dir: Path, version: int) -> None:
    marker = _marker_path(state_dir)
    marker.write_text(json.dumps({"state_version": version}, indent=2))
    _chmod_private(marker)


def run_state_migrations(state_dir: Path) -> dict:
    """Bring the state dir up to CURRENT_STATE_VERSION. Safe to call every start.

    A directory with **no accounts yet** is a fresh install: record the marker
    and run nothing. A directory that has accounts but no marker predates this
    framework, so its migrations do run — unlike the project migrator, which
    assumes an unmarked data root is current. The asymmetry is deliberate: the
    state migrations are repairs (file modes, plaintext tokens) that a legacy
    directory genuinely needs, and every one of them is idempotent.
    """
    state_dir = Path(state_dir)
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("state dir %s is not writable, skipping migrations: %s", state_dir, exc)
        return {"migrated": False, "from": None, "to": None}

    current = read_state_version(state_dir)
    if current is None:
        current = CURRENT_STATE_VERSION if not (state_dir / "users.yaml").exists() else 1

    applied = []
    for version in sorted(MIGRATIONS):
        if version > current:
            try:
                MIGRATIONS[version](state_dir)
                applied.append(version)
            except Exception as exc:  # noqa: BLE001 - never block startup
                logger.warning("state migration to v%d failed: %s", version, exc)
                break

    try:
        _write_state_version(state_dir, CURRENT_STATE_VERSION)
    except OSError as exc:
        logger.warning("could not record state version in %s: %s", state_dir, exc)

    return {"migrated": bool(applied), "from": current, "to": CURRENT_STATE_VERSION}
