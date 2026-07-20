"""Data-schema migrations for clean transitions between program versions.

The on-disk data format can evolve independently of the app version. A marker
file in the data root records the schema version the data conforms to; on
startup we run any migrations needed to bring it up to CURRENT_SCHEMA_VERSION.
This is what makes updating from an old program version to a new one safe: the
new code migrates existing data forward before serving it.

Adding a migration: bump CURRENT_SCHEMA_VERSION and register a function under
the new number in MIGRATIONS. Each function takes the data root and transforms
every project in place. Migrations run in ascending order, exactly once each.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1
_MARKER = ".reqmesh-schema.json"


# ── Migration registry ───────────────────────────────────────────────────────
# MIGRATIONS[n] upgrades data from schema (n-1) to schema n.
MIGRATIONS: dict[int, Callable[[Path], None]] = {
    # 2: _migrate_1_to_2,   # future migrations register here
}


def _marker_path(data_root: Path) -> Path:
    return Path(data_root) / _MARKER


def read_schema_version(data_root: Path) -> int | None:
    try:
        return int(json.loads(_marker_path(data_root).read_text())["schema_version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_schema_version(data_root: Path, version: int) -> None:
    _marker_path(data_root).write_text(json.dumps({"schema_version": version}, indent=2))


def run_migrations(data_root: Path) -> dict:
    """Bring the data root up to CURRENT_SCHEMA_VERSION. Safe to call every start.

    A data root with no marker is assumed to already match the current schema
    (fresh install, or a legacy install predating this framework) — we record
    the marker without running anything. Migrations only run to close a gap
    between a recorded older version and the current one.
    """
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    current = read_schema_version(data_root)

    if current is None:
        _write_schema_version(data_root, CURRENT_SCHEMA_VERSION)
        return {"initialized": CURRENT_SCHEMA_VERSION, "from": None, "to": CURRENT_SCHEMA_VERSION, "ran": []}

    if current >= CURRENT_SCHEMA_VERSION:
        return {"from": current, "to": current, "ran": []}

    ran: list[int] = []
    for target in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        fn = MIGRATIONS.get(target)
        if fn is not None:
            logger.info("running data migration to schema %d", target)
            fn(data_root)
        ran.append(target)
    _write_schema_version(data_root, CURRENT_SCHEMA_VERSION)
    logger.info("data migrated: schema %d -> %d", current, CURRENT_SCHEMA_VERSION)
    return {"from": current, "to": CURRENT_SCHEMA_VERSION, "ran": ran}
