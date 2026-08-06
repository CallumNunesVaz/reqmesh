"""Bound the collection cache to _CACHE_MAX_ENTRIES and verify LRU eviction."""
from pathlib import Path

from app.services import yaml_store
from app.services.yaml_store import YamlStore, _collection_cache, _cache_lock, _CACHE_MAX_ENTRIES


def _make_store(tmp_path: Path, name: str) -> YamlStore:
    """Create a minimal store with one requirement so list_items has something to cache."""
    root = tmp_path / name
    store = YamlStore(root)
    store.ensure_dirs()
    store.write_meta({"name": name})
    # Write a requirement directly on disk so the cache has real content.
    req_dir = root / "requirements"
    req_file = req_dir / "R1.yaml"
    req_file.parent.mkdir(parents=True, exist_ok=True)
    req = {"id": "R1", "name": f"req-in-{name}", "description": ""}
    import app.services.yaml_store as ys
    y = ys._round_trip_yaml()
    with open(req_file, "w") as f:
        y.dump(req, f)
    return store


def test_cache_stays_at_bound(tmp_path: Path):
    """Filling more than _CACHE_MAX_ENTRIES distinct collections leaves the
    cache at the bound, not above it."""
    yaml_store.invalidate_cache()
    # Create more stores than the cache bound.
    for i in range(_CACHE_MAX_ENTRIES + 10):
        store = _make_store(tmp_path, f"proj-{i}")
        store.list_requirements()

    with _cache_lock:
        assert len(_collection_cache) <= _CACHE_MAX_ENTRIES


def test_lru_evicts_least_recently_used(tmp_path: Path):
    """Touch A, touch B, fill past the bound — B survived and A did not."""
    yaml_store.invalidate_cache()

    store_a = _make_store(tmp_path, "a")
    store_b = _make_store(tmp_path, "b")

    store_a.list_requirements()  # A is now MRU
    store_b.list_requirements()  # B is now MRU, A is LRU

    key_a = str(store_a.root / "requirements")
    key_b = str(store_b.root / "requirements")

    # Fill past the bound with fresh entries.
    for i in range(_CACHE_MAX_ENTRIES - 1):  # -1 because A and B are already in
        s = _make_store(tmp_path, f"filler-{i}")
        s.list_requirements()

    with _cache_lock:
        assert key_b in _collection_cache, "most recently used entry was evicted"
        assert key_a not in _collection_cache, "least recently used entry survived"


def test_hit_returns_correct_data_after_eviction_pressure(tmp_path: Path):
    """Read a collection, evict it, read it again — same items."""
    yaml_store.invalidate_cache()

    store = _make_store(tmp_path, "target")
    first = store.list_requirements()
    assert len(first) == 1
    assert first[0]["name"] == "req-in-target"

    # Fill past the bound to evict the target collection.
    for i in range(_CACHE_MAX_ENTRIES + 2):
        s = _make_store(tmp_path, f"evict-{i}")
        s.list_requirements()

    # Re-read — must re-parse from disk and match.
    second = store.list_requirements()
    assert len(second) == 1
    assert second[0]["id"] == first[0]["id"]
    assert second[0]["name"] == first[0]["name"]


def test_mutating_returned_list_does_not_poison_cache(tmp_path: Path):
    """Mutating a returned list does not change what the next call returns."""
    yaml_store.invalidate_cache()

    store = _make_store(tmp_path, "p")
    got = store.list_requirements()
    assert got[0]["name"] == "req-in-p"
    got[0]["name"] = "mutated"

    # Next call must return the uncorrupted data.
    again = store.list_requirements()
    assert again[0]["name"] == "req-in-p"


def test_invalidate_cache_none_clears_everything(tmp_path: Path):
    """invalidate_cache(None) drops every entry."""
    yaml_store.invalidate_cache()

    store = _make_store(tmp_path, "keep")
    store.list_requirements()
    with _cache_lock:
        assert len(_collection_cache) >= 1

    yaml_store.invalidate_cache(None)
    with _cache_lock:
        assert len(_collection_cache) == 0


def test_invalidate_cache_path_drops_parent(tmp_path: Path):
    """invalidate_cache(path) drops only that file's parent directory entry."""
    yaml_store.invalidate_cache()

    store_a = _make_store(tmp_path, "a")
    store_b = _make_store(tmp_path, "b")
    store_a.list_requirements()
    store_b.list_requirements()

    key_a = str(store_a.root / "requirements")
    key_b = str(store_b.root / "requirements")
    with _cache_lock:
        assert key_a in _collection_cache
        assert key_b in _collection_cache

    # Invalidate a specific file in store_a's requirements dir.
    yaml_store.invalidate_cache(store_a.root / "requirements" / "R1.yaml")

    with _cache_lock:
        assert key_a not in _collection_cache
        assert key_b in _collection_cache
