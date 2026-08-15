"""Migration 2→3: a component parented to something that is not a component.

``POST /components/bulk`` accepted any string as a parent, so a requirement id
could reach `component.parent` and then sit there unseen — `build_flat_tree`
buckets an unresolvable parent under ``None``, so the component simply rendered
as a root. The migration makes that display true on disk.
"""
import pytest
from ruamel.yaml import YAML

from app.services.migrations import (
    CURRENT_SCHEMA_VERSION,
    _migrate_2_to_3,
    run_migrations,
)

yaml = YAML()


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    (root / "proj" / "components").mkdir(parents=True)
    (root / "proj" / "_meta.yaml").write_text("name: Proj\n")
    return root


def _component(root, cid, **fields):
    path = root / "proj" / "components" / f"{cid}.yaml"
    with path.open("w") as fh:
        yaml.dump({"id": cid, "name": cid, **fields}, fh)
    return path


def _read(path):
    with path.open() as fh:
        return yaml.load(fh)


def test_a_requirement_id_parent_is_cleared_to_top_level(data_root):
    bad = _component(data_root, "WING", parent="SYS-1")

    _migrate_2_to_3(data_root)

    assert _read(bad)["parent"] is None


def test_the_discarded_value_is_logged(data_root, caplog):
    """Clearing it destroys the only evidence of what was there, so the log is
    the sole route back if a repair turns out to be wrong."""
    _component(data_root, "WING", parent="SYS-1")

    with caplog.at_level("WARNING"):
        _migrate_2_to_3(data_root)

    assert any("SYS-1" in r.getMessage() and "WING" in r.getMessage()
               for r in caplog.records), caplog.text


def test_a_real_component_parent_is_left_alone(data_root):
    _component(data_root, "SYS")
    child = _component(data_root, "SUB", parent="SYS")

    _migrate_2_to_3(data_root)

    assert _read(child)["parent"] == "SYS"


def test_an_already_top_level_component_is_untouched(data_root):
    root = _component(data_root, "SYS", parent=None)
    before = root.read_text()

    _migrate_2_to_3(data_root)

    assert root.read_text() == before


def test_it_is_idempotent(data_root):
    bad = _component(data_root, "WING", parent="SYS-1")

    _migrate_2_to_3(data_root)
    after_first = bad.read_text()
    _migrate_2_to_3(data_root)

    assert bad.read_text() == after_first


def test_one_unreadable_component_does_not_abort_the_rest(data_root):
    (data_root / "proj" / "components" / "BROKEN.yaml").write_text("{[not: yaml\n")
    bad = _component(data_root, "WING", parent="SYS-1")

    _migrate_2_to_3(data_root)

    assert _read(bad)["parent"] is None


def test_an_unparseable_sibling_does_not_wipe_valid_parents(data_root):
    """The id set comes from filenames, not from parsing every file.

    Building it by parsing would let a single unreadable component make every
    *other* component's parent look dangling, and the repair would then clear
    correct data project-wide.
    """
    (data_root / "proj" / "components" / "SYS.yaml").write_text("{[not: yaml\n")
    child = _component(data_root, "SUB", parent="SYS")

    _migrate_2_to_3(data_root)

    assert _read(child)["parent"] == "SYS"


def test_run_migrations_reaches_the_new_version(data_root):
    bad = _component(data_root, "WING", parent="SYS-1")
    (data_root / ".reqmesh-schema.json").write_text('{"schema_version": 2}')

    result = run_migrations(data_root)

    assert result["to"] == CURRENT_SCHEMA_VERSION
    assert 3 in result["ran"]
    assert _read(bad)["parent"] is None


def test_a_project_without_components_is_skipped(data_root):
    import shutil
    shutil.rmtree(data_root / "proj" / "components")

    _migrate_2_to_3(data_root)  # must not raise
