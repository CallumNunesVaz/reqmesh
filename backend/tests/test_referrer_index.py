"""The batched referrer index must agree with the per-call resolver.

Bulk delete builds it once instead of rescanning the corpus per id, so it has to
produce the same referrer set `find_referrers` does — including the
self-reference exclusion.
"""
from app.services.link_registry import (
    build_referrer_index,
    find_referrers,
    referrers_from_index,
)
from app.services.yaml_store import YamlStore


def _store(tmp_path) -> YamlStore:
    s = YamlStore(tmp_path / "p")
    s.ensure_dirs()
    return s


def test_index_matches_find_referrers(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "R-1", "name": "target"})
    s.create_item("specifications", {"id": "S-1", "name": "spec", "requirements": ["R-1"]})
    s.create_item("risks", {"id": "K-1", "title": "risk", "linked_requirements": ["R-1"]})

    index = build_referrer_index(s)
    assert referrers_from_index(index, "requirements", "R-1") == \
        find_referrers(s, "requirements", "R-1", include_tree=False)


def test_index_excludes_self_reference(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "R-1", "name": "self", "cascade_from": "R-1"})
    index = build_referrer_index(s)
    assert referrers_from_index(index, "requirements", "R-1") == []
    assert find_referrers(s, "requirements", "R-1", include_tree=False) == []
