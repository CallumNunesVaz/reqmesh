"""The collection cache bound: it is honoured, LRU still evicts the right
entry, an invalid bound is rejected, and a benchmark showing that a working set
which fits the bound is never re-parsed.

The benchmark is marked ``bench``, not ``contract`` — ``contract`` means the
OpenAPI property suite and is its own CI gate, so a performance measurement
filed there would fail that job for reasons unrelated to the API contract. Run
it explicitly with ``pytest tests/test_collection_cache.py -m bench -s``.
"""
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import yaml_store
from app.services.yaml_store import YamlStore, _cache_lock, _collection_cache


def _write_collection(root: Path, name: str, n_items: int = 1) -> None:
    """Write a collection directory of ``n_items`` minimal items under *root*.

    Direct file writes (not the round-trip loader) so building many projects is
    cheap; the read path under test is ``list_items``.
    """
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n_items):
        (d / f"{name}-{i}.yaml").write_text(
            f"id: {name}-{i}\nname: {name} {i}\ndescription: \"\"\n",
        )


@pytest.fixture()
def bounded(monkeypatch):
    """Set the cache bound low so these tests stay fast, and reset the cache."""
    monkeypatch.setattr(settings, "collection_cache_max_entries", 4)
    yaml_store.invalidate_cache()
    return 4


def test_bound_is_honoured(bounded, tmp_path: Path):
    """Inserting bound + 10 distinct collections leaves exactly ``bound``."""
    store = YamlStore(tmp_path)
    for i in range(bounded + 10):
        name = f"c{i}"
        _write_collection(tmp_path, name)
        store.list_items(name)

    with _cache_lock:
        assert len(_collection_cache) == bounded


def test_lru_evicts_least_recently_used(bounded, tmp_path: Path):
    """Read A, insert past the bound: A survives, the older untouched entry does not."""
    store = YamlStore(tmp_path)
    for name in ("a", "b", "c", "d"):
        _write_collection(tmp_path, name)

    # Fill to the bound in order a, b, c, d (d is MRU, a is LRU).
    for name in ("a", "b", "c", "d"):
        store.list_items(name)

    # Re-read A so it becomes the most recently used, leaving b the LRU.
    store.list_items("a")

    # One more insert pushes past the bound; b must go, a must stay.
    _write_collection(tmp_path, "e")
    store.list_items("e")

    key_a = str(tmp_path / "a")
    key_b = str(tmp_path / "b")
    with _cache_lock:
        assert key_a in _collection_cache, "most recently used entry was evicted"
        assert key_b not in _collection_cache, "least recently used entry survived"


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_invalid_configured_bound_rejected(bad):
    """A bound < 1 must fail at settings load, not produce a self-evicting cache."""
    with pytest.raises(ValidationError):
        Settings(collection_cache_max_entries=bad)


@pytest.mark.bench
def test_benchmark_cache_hit_rate_across_project_counts(tmp_path: Path, monkeypatch):
    """Measure hit rate and wall time for a sweep across N projects.

    A realistic access pattern: walk every project, listing each of its
    collection directories, twice. The first pass is cold; every later read of
    a still-cached directory must be a hit. With ~10 directories per project
    and the default bound, 32 projects (352 directories) fit without evicting
    anything the pattern is about to revisit — so no directory is ever parsed
    twice.
    """
    bound = settings.collection_cache_max_entries
    collections = yaml_store.COLLECTIONS
    results = []

    # Only sweep sizes whose working set fits the bound — past that the cache
    # is *supposed* to evict, so re-parsing there is correct behaviour, not a
    # regression. Deriving this from the bound keeps the test honest if the
    # default changes again.
    _fitting = [n for n in (4, 8, 16, 32) if n * len(collections) <= bound]
    assert _fitting, "bound too small for even the smallest sweep size"
    for n_projects in _fitting:
        stores = []
        for p in range(n_projects):
            root = tmp_path / f"proj-{p}"
            for coll in collections:
                _write_collection(root, coll, 3)
            stores.append(YamlStore(root))

        yaml_store.invalidate_cache()

        calls = 0
        misses = 0
        orig = YamlStore._read_collection

        def _counting_read(self, d, _orig=orig):
            nonlocal misses
            misses += 1
            return _orig(self, d)

        monkeypatch.setattr(YamlStore, "_read_collection", _counting_read)

        t0 = time.perf_counter()
        for _ in range(2):
            for store in stores:
                for coll in collections:
                    store.list_items(coll)
                    calls += 1
        wall = time.perf_counter() - t0

        monkeypatch.undo()

        dirs = n_projects * len(collections)
        hits = calls - misses
        results.append((n_projects, dirs, calls, hits, misses, wall))

    print("\nCollection cache benchmark (bound=%d):" % bound)
    print("  projects  dirs  reads  hits  hit%  time(s)")
    for n_projects, dirs, calls, hits, _misses, wall in results:
        print("  %8d  %4d  %5d  %4d  %5.1f  %.3f"
              % (n_projects, dirs, calls, hits, 100.0 * hits / calls, wall))

    # The bound must cover every directory the largest case touches: if a
    # directory were evicted before the second pass, it would be re-parsed and
    # ``misses`` would exceed ``dirs``. Equal means each was parsed exactly once.
    for n_projects, dirs, _calls, _hits, misses, _wall in results:
        assert misses == dirs, (
            "with bound=%d, %d projects re-parsed %d/%d directories (cache too small)"
            % (bound, n_projects, misses - dirs, dirs),
        )
