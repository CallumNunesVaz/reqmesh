"""Schema migration 1 → 2: comments gain entity_kind/entity_id.

This is the first migration this project has ever run, so these tests exercise
the *framework* as much as the transform — the registry, the version marker and
the re-run behaviour have never executed before.
"""
import json

import pytest
from ruamel.yaml import YAML

from app.services.migrations import (
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    _migrate_1_to_2,
    read_schema_version,
    run_migrations,
)


def _yaml():
    return YAML()


def _project(root, name="p1"):
    proj = root / name
    (proj / "comments").mkdir(parents=True)
    (proj / "_meta.yaml").write_text("name: P1\n")
    return proj


def _write(path, data):
    with open(path, "w") as f:
        _yaml().dump(data, f)


def _read(path):
    with open(path) as f:
        return _yaml().load(f)


def test_registry_is_wired(tmp_path):
    """A migration that is written but not registered silently never runs."""
    assert MIGRATIONS.get(2) is _migrate_1_to_2
    assert CURRENT_SCHEMA_VERSION >= 2


def test_legacy_comment_is_rewritten(tmp_path):
    proj = _project(tmp_path)
    _write(proj / "comments" / "C1.yaml",
           {"id": "C1", "requirement_id": "R-1", "text": "hello"})

    _migrate_1_to_2(tmp_path)

    got = _read(proj / "comments" / "C1.yaml")
    assert got["entity_kind"] == "requirements"
    assert got["entity_id"] == "R-1"
    assert "requirement_id" not in got
    assert got["text"] == "hello", "unrelated fields must survive"


def test_migration_is_idempotent(tmp_path):
    """Re-running must not touch an already-migrated comment.

    A migration that is not idempotent corrupts data the second time a container
    restarts before the marker is written.
    """
    proj = _project(tmp_path)
    _write(proj / "comments" / "C1.yaml",
           {"id": "C1", "requirement_id": "R-1", "text": "hello"})

    _migrate_1_to_2(tmp_path)
    first = _read(proj / "comments" / "C1.yaml")
    _migrate_1_to_2(tmp_path)
    second = _read(proj / "comments" / "C1.yaml")

    assert dict(first) == dict(second)


def test_already_migrated_comment_is_left_alone(tmp_path):
    proj = _project(tmp_path)
    _write(proj / "comments" / "C1.yaml",
           {"id": "C1", "entity_kind": "risks", "entity_id": "RSK-1"})

    _migrate_1_to_2(tmp_path)

    got = _read(proj / "comments" / "C1.yaml")
    assert got["entity_kind"] == "risks", "must not be re-pointed at requirements"
    assert got["entity_id"] == "RSK-1"


def test_one_unreadable_file_does_not_abort_the_rest(tmp_path):
    """Startup runs migrations, so an unparseable file must not take the app down."""
    proj = _project(tmp_path)
    (proj / "comments" / "broken.yaml").write_text("{{{ not yaml")
    _write(proj / "comments" / "C2.yaml",
           {"id": "C2", "requirement_id": "R-2"})

    _migrate_1_to_2(tmp_path)

    assert _read(proj / "comments" / "C2.yaml")["entity_id"] == "R-2"


def test_a_directory_that_is_not_a_project_is_skipped(tmp_path):
    """Only directories with _meta.yaml are projects."""
    stray = tmp_path / "not-a-project" / "comments"
    stray.mkdir(parents=True)
    _write(stray / "C1.yaml", {"id": "C1", "requirement_id": "R-1"})

    _migrate_1_to_2(tmp_path)

    assert "requirement_id" in _read(stray / "C1.yaml")


def test_run_migrations_advances_a_recorded_version_1(tmp_path):
    """The path every existing deployment takes: marker at 1, migrate to 2."""
    proj = _project(tmp_path)
    _write(proj / "comments" / "C1.yaml",
           {"id": "C1", "requirement_id": "R-1"})
    (tmp_path / ".reqmesh-schema.json").write_text(json.dumps({"schema_version": 1}))

    result = run_migrations(tmp_path)

    assert 2 in result["ran"]
    assert read_schema_version(tmp_path) == CURRENT_SCHEMA_VERSION
    assert _read(proj / "comments" / "C1.yaml")["entity_id"] == "R-1"


def test_an_unmarked_data_root_is_stamped_without_migrating(tmp_path):
    """Documented behaviour, asserted so it stays deliberate.

    No marker means "fresh install", so nothing runs. A data root that predates
    the framework therefore keeps its legacy comments — which is exactly why
    `load_guard._validate_comment` coerces them on read as well.
    """
    proj = _project(tmp_path)
    _write(proj / "comments" / "C1.yaml",
           {"id": "C1", "requirement_id": "R-1"})

    result = run_migrations(tmp_path)

    assert result["ran"] == []
    assert read_schema_version(tmp_path) == CURRENT_SCHEMA_VERSION
    assert "requirement_id" in _read(proj / "comments" / "C1.yaml")


def test_the_read_guard_covers_what_the_migration_missed(tmp_path):
    """The belt-and-braces half of the above, so the pair is tested together."""
    from app.services.load_guard import validate_on_load

    item = validate_on_load("comments", {"id": "C1", "requirement_id": "R-9"})

    assert item["entity_kind"] == "requirements"
    assert item["entity_id"] == "R-9"
    assert "requirement_id" not in item
