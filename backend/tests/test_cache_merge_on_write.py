"""Merge a written/deleted file into the collection cache, not drop it.

``_write_yaml`` and ``delete_item`` used to call ``invalidate_cache(path)``,
dropping the whole cached collection so the next list read re-parsed every file
in the directory. This suite pins the replacement behaviour: when the parent
directory is already cached, a single-item write or delete updates the cached
entry in place — re-reading only that one file through the same parse + validate
steps as a cold fill — and recomputes the directory signature so the next
``list_items`` still reads from cache.
"""

from pathlib import Path

from app.services import yaml_store
from app.services.yaml_store import YamlStore


def _reset() -> None:
    yaml_store.invalidate_cache()


def _write_file(root: Path, collection: str, req_id: str) -> None:
    """Write one minimal item straight to disk (not the round-trip loader)."""
    d = root / collection
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{req_id}.yaml").write_text(
        f"id: {req_id}\nname: {req_id}\ndescription: \"\"\n",
    )


def _spy_parses(monkeypatch, store: YamlStore):
    """Count ``_parse_fast`` calls made after installation."""
    real = YamlStore._parse_fast
    counter = {"n": 0}

    def spy(self, path):
        counter["n"] += 1
        return real(self, path)

    monkeypatch.setattr(YamlStore, "_parse_fast", spy)
    return counter


def test_write_merge_avoids_full_reparse(tmp_path: Path, monkeypatch):
    """A write after a warm read re-parses only the written file, not the
    directory — the return-content check alone would pass against the old
    drop-everything behaviour."""
    _reset()
    store = YamlStore(tmp_path)
    for i in range(10):
        _write_file(tmp_path, "requirements", f"REQ-{i:02d}")
    store.list_items("requirements")  # warm the cache

    counter = _spy_parses(monkeypatch, store)
    store.write_item("requirements", "REQ-03",
                     {"id": "REQ-03", "name": "updated", "description": ""})
    assert counter["n"] == 1, "write must re-parse only the written file"

    items = store.list_items("requirements")
    assert counter["n"] == 1, "list_items must be a cache hit, not a re-parse"
    assert {i["id"]: i for i in items}["REQ-03"]["name"] == "updated"


def test_delete_merge_avoids_full_reparse(tmp_path: Path, monkeypatch):
    """A delete after a warm read drops the id without re-parsing the directory."""
    _reset()
    store = YamlStore(tmp_path)
    for i in range(10):
        _write_file(tmp_path, "requirements", f"REQ-{i:02d}")
    store.list_items("requirements")

    counter = _spy_parses(monkeypatch, store)
    assert store.delete_item("requirements", "REQ-05")
    assert counter["n"] == 0, "delete must not re-parse anything"

    ids = [i["id"] for i in store.list_items("requirements")]
    assert counter["n"] == 0, "list_items must be a cache hit"
    assert "REQ-05" not in ids


def test_new_item_inserted_in_filename_order(tmp_path: Path):
    """A newly created item lands in filename-sorted order among its neighbours."""
    _reset()
    store = YamlStore(tmp_path)
    for rid in ("REQ-01", "REQ-02", "REQ-04", "REQ-05"):
        _write_file(tmp_path, "requirements", rid)
    store.list_items("requirements")

    store.write_item("requirements", "REQ-03",
                     {"id": "REQ-03", "name": "REQ-03", "description": ""})

    ids = [i["id"] for i in store.list_items("requirements")]
    assert ids == ["REQ-01", "REQ-02", "REQ-03", "REQ-04", "REQ-05"]


def test_merge_applies_load_sanitiser(tmp_path: Path):
    """The merged item still goes through ``validate_on_load``: an HTML payload
    written straight to the store is sanitised on the way out of ``list_items``.
    This is the regression the naive merge fails."""
    _reset()
    store = YamlStore(tmp_path)
    _write_file(tmp_path, "requirements", "REQ-01")
    store.list_items("requirements")

    dirty = "<p>ok</p><img src=x onerror=alert(1)><script>bad()</script>"
    store.write_item("requirements", "REQ-01",
                     {"id": "REQ-01", "name": "REQ-01", "description": dirty})

    desc = store.list_items("requirements")[0]["description"]
    assert "<script" not in desc
    assert "onerror" not in desc
    assert "<p>ok</p>" in desc


def test_unsafe_id_withheld_after_merge(tmp_path: Path):
    """A file whose id ``validate_on_load`` rejects never appears in the cache."""
    _reset()
    store = YamlStore(tmp_path)
    _write_file(tmp_path, "requirements", "REQ-01")
    store.list_items("requirements")

    store.write_item("requirements", "REQ-EVIL",
                     {"id": "a/b", "name": "evil", "description": ""})

    ids = [i["id"] for i in store.list_items("requirements")]
    assert "a/b" not in ids
    assert ids == ["REQ-01"]


def test_cold_read_matches_merged_cache(tmp_path: Path):
    """A cold fill after the merge returns exactly the merged cache's list —
    a divergence in order or content fails loudly."""
    _reset()
    store = YamlStore(tmp_path)
    for rid in ("REQ-01", "REQ-02", "REQ-03"):
        _write_file(tmp_path, "requirements", rid)
    store.list_items("requirements")

    store.write_item("requirements", "REQ-02",
                     {"id": "REQ-02", "name": "updated", "description": "d"})
    store.write_item("requirements", "REQ-04",
                     {"id": "REQ-04", "name": "REQ-04", "description": ""})
    store.delete_item("requirements", "REQ-01")

    merged = store.list_items("requirements")

    yaml_store.invalidate_cache()
    cold = store.list_items("requirements")

    assert cold == merged
