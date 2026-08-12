"""A failed YAML write must not break the next one.

ruamel keeps emitter state on the `YAML()` object. When the store shared one
instance, a dump that raised part-way left it mid-document and every later dump
in the process failed with `expected DocumentEndEvent, but got
DocumentStartEvent` — until the process restarted. In production that turned one
bad write into 56 consecutive 500s on "Mark Reviewed" and "Request a Change",
with "Internal Server Error" the only thing the user saw.

A lock does not help: it serialises access, it cannot un-poison an object. These
tests pin the property that actually fixes it — writer instances are per call, so
one failure cannot reach the next.
"""

import threading

import pytest
from ruamel.yaml import YAMLError

from app.services.yaml_store import YamlStore, _round_trip_yaml, _fast_reader


class _Unrepresentable:
    """ruamel cannot represent this, so dumping one raises mid-document."""


def test_a_failed_dump_does_not_break_the_next_write(tmp_path):
    store = YamlStore(tmp_path / "proj")
    store.ensure_dirs()
    store.write_meta({"name": "before"})

    # Poison attempt: a value ruamel cannot represent, dumped through the store.
    with pytest.raises(YAMLError):
        store.write_meta({"name": "bad", "boom": _Unrepresentable()})

    # The next write must still succeed. Sharing one instance made this fail
    # for the rest of the process.
    store.write_meta({"name": "after"})
    assert store.read_meta()["name"] == "after"


def test_a_failed_dump_does_not_break_requirement_writes(tmp_path):
    store = YamlStore(tmp_path / "proj")
    store.ensure_dirs()
    store.create_requirement({"id": "R1", "name": "One", "description": "d"})

    with pytest.raises(YAMLError):
        store.write_meta({"boom": _Unrepresentable()})

    # Exactly the path that 500'd in production: review and change-request both
    # end in update_requirement -> _write_yaml.
    assert store.update_requirement("R1", {"name": "Two"})
    assert store.get_requirement("R1")["name"] == "Two"


def test_writers_are_not_shared_between_calls():
    assert _round_trip_yaml() is not _round_trip_yaml()
    assert _fast_reader() is not _fast_reader()


def test_concurrent_writes_all_land(tmp_path):
    """The race the old lock existed for, without the lock."""
    store = YamlStore(tmp_path / "proj")
    store.ensure_dirs()
    for i in range(12):
        store.create_requirement({"id": f"R{i}", "name": f"n{i}", "description": "d"})

    errors: list[BaseException] = []

    def rewrite(i: int) -> None:
        try:
            store.update_requirement(f"R{i}", {"name": f"renamed-{i}"})
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=rewrite, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    for i in range(12):
        assert store.get_requirement(f"R{i}")["name"] == f"renamed-{i}"
