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

from app.core.filelock import file_lock

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 4
_MARKER = ".reqmesh-schema.json"


def _migrate_1_to_2(data_root: Path) -> None:
    """Comments attach to any entity, not just requirements.

    ``requirement_id`` becomes ``entity_kind`` + ``entity_id``. Idempotent: a
    comment that already has ``entity_id`` is left alone, so a re-run — or a
    project that a newer version already touched — is a no-op.

    One unreadable comment must not abort the migration and take startup with
    it, so failures are logged per file and the rest continue. A file that
    fails is left at the old shape and simply keeps working through the
    ``requirement_id`` compatibility path.
    """
    from app.services.yaml_store import YamlStore

    migrated = 0
    for project in sorted(p for p in Path(data_root).iterdir() if p.is_dir()):
        if not (project / "_meta.yaml").exists():
            continue
        comments = project / "comments"
        if not comments.exists():
            continue
        store = YamlStore(project)
        for f in sorted(comments.glob("*.yaml")):
            try:
                item = store._parse_yaml(f)
                if not item or item.get("entity_id"):
                    continue
                req_id = item.pop("requirement_id", "")
                if not req_id:
                    continue
                item["entity_kind"] = "requirements"
                item["entity_id"] = req_id
                store._write_yaml(f, item)
                migrated += 1
            except Exception as exc:
                logger.warning("Skipping comment %s during migration to 2: %s", f, exc)
    if migrated:
        logger.info("Migrated %d comment(s) to entity_kind/entity_id", migrated)


def _migrate_2_to_3(data_root: Path) -> None:
    """A component's parent must be another component.

    Components form their own hierarchy and reach requirements through
    ``satisfies``; a parent that names anything but a component is not a
    relationship the model has (see README, "Components"). Every write path
    refused such a value except ``POST /components/bulk``, which validated only
    the shape — so a requirement id could be written there and then sat on disk
    unnoticed, because ``build_flat_tree`` buckets an unresolvable parent under
    ``None`` and the component simply renders as a root.

    Repairs by clearing the parent, which makes the component top level — the
    same thing the tree was already displaying, now actually true on disk.

    The discarded value is logged per component, because clearing it destroys
    the only evidence of what was there. If a repair turns out to be wrong, the
    log is the only route back.

    Idempotent: a component whose parent resolves (or is already empty) is left
    alone, so a re-run — or a project a newer version already touched — is a
    no-op. One unreadable component must not abort the migration and take
    startup with it, so failures are logged per file and the rest continue.
    """
    from app.services.yaml_store import YamlStore

    repaired = 0
    for project in sorted(p for p in Path(data_root).iterdir() if p.is_dir()):
        if not (project / "_meta.yaml").exists():
            continue
        components = project / "components"
        if not components.exists():
            continue
        store = YamlStore(project)

        # The id set is built from the filenames rather than by parsing every
        # file, so one unparseable component cannot make every *other*
        # component's parent look dangling and trigger a project-wide wipe of
        # correct data.
        known = {f.stem for f in components.glob("*.yaml")}

        for f in sorted(components.glob("*.yaml")):
            try:
                item = store._parse_yaml(f)
                if not item:
                    continue
                parent = item.get("parent")
                if not parent or parent in known:
                    continue
                logger.warning(
                    "Repairing component %s in project %s: parent %r is not a "
                    "component; clearing it to top level",
                    item.get("id", f.stem), project.name, parent,
                )
                item["parent"] = None
                store._write_yaml(f, item)
                repaired += 1
            except Exception as exc:
                logger.warning("Skipping component %s during migration to 3: %s", f, exc)
    if repaired:
        logger.info("Repaired %d component(s) with a non-component parent", repaired)


def _migrate_3_to_4(data_root: Path) -> None:
    """Risks split their free-text ``description`` into FMECA fields.

    ``description`` becomes ``failure_mode``; ``effect`` and ``cause`` are left
    empty — there is nothing to derive them from, and inventing content would
    be worse than blank. ``description`` is deliberately **not** deleted from
    the YAML: a migration that discards data has no way back if the release is
    rolled back.

    Idempotent: a risk that already has ``failure_mode`` is left alone, so a
    re-run — or a project a newer version already touched — is a no-op. One
    unreadable risk must not abort the migration and take startup down with it,
    so failures are logged per file and the rest continue.

    Risks are not fingerprinted (``services/fingerprint.py`` fingerprints only
    requirements), so this rewrite does not change any stored review
    fingerprint and cannot flag the register as needing re-review.
    """
    from app.services.yaml_store import YamlStore

    migrated = 0
    for project in sorted(p for p in Path(data_root).iterdir() if p.is_dir()):
        if not (project / "_meta.yaml").exists():
            continue
        risks = project / "risks"
        if not risks.exists():
            continue
        store = YamlStore(project)
        for f in sorted(risks.glob("*.yaml")):
            try:
                item = store._parse_yaml(f)
                if not item or item.get("failure_mode"):
                    continue
                description = item.get("description")
                if not description or not str(description).strip():
                    continue
                item["failure_mode"] = description
                store._write_yaml(f, item)
                migrated += 1
            except Exception as exc:
                logger.warning("Skipping risk %s during migration to 4: %s", f, exc)
    if migrated:
        logger.info("Migrated %d risk(s) description -> failure_mode", migrated)


# ── Migration registry ───────────────────────────────────────────────────────
# MIGRATIONS[n] upgrades data from schema (n-1) to schema n.
MIGRATIONS: dict[int, Callable[[Path], None]] = {
    2: _migrate_1_to_2,
    3: _migrate_2_to_3,
    4: _migrate_3_to_4,
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

    # The marker's read-modify-write must be exclusive: two instances against
    # one data root otherwise both see the same recorded version and run the
    # same migrations concurrently, interleaving file rewrites. Keyed on the
    # marker path itself so every process serialises on the same lock.
    with file_lock(_marker_path(data_root)):
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
