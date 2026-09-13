"""A failed replace-mode import must not leave a half-imported project.

Replace mode deletes the current corpus and writes the new one item by item.
Before the snapshot, a failure partway through lost the original data with no
way back; the next successful import is the only recovery.
"""
import pytest

from app.services.yaml_store import YamlStore
from tests.conftest import make_req


def test_import_snapshot_restores_on_failure(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    store.create_requirement({"id": "R-1", "name": "keep"})

    with pytest.raises(RuntimeError):
        with store.import_snapshot(True):
            store.delete_requirement("R-1")
            store.create_requirement({"id": "R-2", "name": "half"})
            raise RuntimeError("import blew up")

    assert store.get_requirement("R-1") is not None
    assert store.get_requirement("R-2") is None


def test_import_snapshot_disabled_is_a_noop(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    store.create_requirement({"id": "R-1", "name": "keep"})
    with store.import_snapshot(False):
        store.delete_requirement("R-1")
    assert store.get_requirement("R-1") is None


def test_replace_import_rolls_back_on_failure(client, project, monkeypatch):
    from app.services import table_io

    make_req(client, project, "R-1", name="keep")

    def boom(store, *args, **kwargs):
        # Simulate a partial write followed by a failure.
        store.delete_requirement("R-1")
        store.create_requirement({"id": "R-2", "name": "half"})
        raise ValueError("mid-import failure")

    monkeypatch.setattr(table_io, "import_table", boom)

    csv = '"id","type","name"\n"R-9","functional","x"'
    res = client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "replace"},
        files={"file": ("t.csv", csv.encode(), "text/csv")},
    )
    assert res.status_code == 400, res.text

    assert client.get(f"/api/projects/{project}/requirements/R-1").status_code == 200
    assert client.get(f"/api/projects/{project}/requirements/R-2").status_code == 404
