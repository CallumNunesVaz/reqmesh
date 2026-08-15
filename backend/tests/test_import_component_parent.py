"""An import must not seed a component parented to a non-component.

`_normalise_component` passed `parent` through verbatim, so a file could land a
component whose parent is a requirement id — a shape the API refuses on every
other write path.
"""
from __future__ import annotations

from pathlib import Path

from app.services.importer import import_into_store
from app.services.yaml_store import YamlStore


def _store(tmp_path: Path) -> YamlStore:
    root = tmp_path / "project"
    root.mkdir()
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": "TestProject"})
    return store


def test_a_parent_naming_a_requirement_is_dropped_to_top_level(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({"id": "SYS-1", "name": "Wing Assembly"})

    summary = import_into_store(store, {
        "components": [{"id": "WING", "name": "Wing Assembly", "parent": "SYS-1"}],
    })

    assert store.get_component("WING")["parent"] is None
    assert summary["repaired_parents"] == [
        {"component": "WING", "dropped_parent": "SYS-1"}
    ]


def test_the_import_still_lands_rather_than_failing(tmp_path):
    """Refusing the whole file over one bad pointer leaves the user with
    nothing imported and no way to see what was wrong."""
    store = _store(tmp_path)

    summary = import_into_store(store, {
        "components": [
            {"id": "GOOD", "name": "Good"},
            {"id": "BAD", "name": "Bad", "parent": "NOT-A-COMPONENT"},
        ],
    })

    assert summary["components"] == 2
    assert store.get_component("GOOD") is not None
    assert store.get_component("BAD") is not None


def test_a_parent_defined_later_in_the_same_file_is_kept(tmp_path):
    """A file listing a child before its parent is ordinary, so the incoming
    set has to count — not just what is already in the store."""
    store = _store(tmp_path)

    summary = import_into_store(store, {
        "components": [
            {"id": "SUB", "name": "Sub", "parent": "SYS"},
            {"id": "SYS", "name": "Sys"},
        ],
    })

    assert store.get_component("SUB")["parent"] == "SYS"
    assert "repaired_parents" not in summary


def test_a_parent_already_in_the_store_is_kept(tmp_path):
    store = _store(tmp_path)
    store.create_component({"id": "SYS", "name": "Sys"})

    import_into_store(store, {
        "components": [{"id": "SUB", "name": "Sub", "parent": "SYS"}],
    })

    assert store.get_component("SUB")["parent"] == "SYS"


def test_a_clean_import_reports_no_repairs(tmp_path):
    store = _store(tmp_path)

    summary = import_into_store(store, {
        "components": [{"id": "SYS", "name": "Sys"}],
    })

    assert "repaired_parents" not in summary
