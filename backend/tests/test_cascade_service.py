"""Cascade propagation and cycle detection, extracted from the API router.

These pin the behaviour the router used to inline: transitive propagation of only
the changed fields, and a parent-cycle guard that takes the id→parent map rather
than the store.
"""
import pytest

from app.services.cascade import break_link, create_copies, propagate
from app.services.reparent import assert_no_parent_cycle
from app.services.yaml_store import YamlStore


def _store(tmp_path) -> YamlStore:
    s = YamlStore(tmp_path / "p")
    s.ensure_dirs()
    return s


def test_propagate_walks_transitively(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "SRC", "name": "old"})
    s.create_requirement({"id": "C1", "name": "child", "cascade_from": "SRC"})
    s.create_requirement({"id": "C2", "name": "grand", "cascade_from": "C1"})

    assert propagate(s, "SRC", {"name": "new"}, "tester") is True
    assert s.get_requirement("C1")["name"] == "new"
    assert s.get_requirement("C2")["name"] == "new"


def test_propagate_without_a_propagated_field_is_a_noop(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "SRC", "name": "old"})
    s.create_requirement({"id": "C1", "name": "child", "cascade_from": "SRC"})
    assert propagate(s, "SRC", {"reviewed": "x"}, "tester") is False


def test_create_copies_under_child_groups(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "SRC", "name": "source", "description": "d"})
    s.create_requirement({"id": "G1", "name": "group", "parent": "SRC"})

    created = create_copies(s, "SRC", "tester")
    assert len(created) == 1
    copy = s.get_requirement(created[0])
    assert copy["parent"] == "G1"
    assert copy["cascade_from"] == "SRC"
    assert copy["name"] == "source"


def test_break_link_clears_only_cascade_from(tmp_path):
    s = _store(tmp_path)
    s.create_requirement({"id": "SRC", "name": "source"})
    s.create_requirement({"id": "C1", "name": "child", "cascade_from": "SRC"})
    s.update_requirement("C1", {"priority": "high"})

    assert break_link(s, "C1") == "SRC"
    c1 = s.get_requirement("C1")
    assert c1["cascade_from"] is None
    assert c1["priority"] == "high"
    assert c1["name"] == "child"


def test_cycle_guard_rejects_self_and_loops():
    with pytest.raises(ValueError):
        assert_no_parent_cycle({"A": "B", "B": None}, "A", "A")
    with pytest.raises(ValueError):
        assert_no_parent_cycle({"A": "B", "B": "A"}, "A", "B")


def test_cycle_guard_allows_a_valid_move():
    assert_no_parent_cycle({"A": None, "B": "C", "C": None}, "A", "B")
