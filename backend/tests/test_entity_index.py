"""The shared entity-id index used by the activity endpoint.

`build_entity_index` exists so resolving thousands of audit entries does not
rebuild every collection's id map per entry. It must agree with the per-call
`resolve_entity_label`, including the precedence rule for a colliding id.
"""
from app.services.entity_kinds import build_entity_index, resolve_entity_label
from app.services.yaml_store import YamlStore


def _store(tmp_path) -> YamlStore:
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    return store


def test_index_resolves_kinds_and_names(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({"id": "R-1", "name": "Requirement One"})
    store.create_component({"id": "C-1", "name": "Component One"})

    index = build_entity_index(store)
    assert index["R-1"] == ("Requirement", "Requirement One")
    assert index["C-1"] == ("Component", "Component One")
    assert index.get("missing", ("Item", "")) == ("Item", "")


def test_index_matches_the_per_call_resolver(tmp_path):
    store = _store(tmp_path)
    store.create_requirement({"id": "R-1", "name": "One"})
    store.create_component({"id": "C-1", "name": "Two"})

    index = build_entity_index(store)
    for item_id in ("R-1", "C-1", "missing"):
        expected = resolve_entity_label(store, item_id)
        assert index.get(item_id, ("Item", "")) == expected


def test_index_honours_resolver_precedence_for_a_shared_id(tmp_path):
    """Ids are only unique per collection; requirements outrank components."""
    store = _store(tmp_path)
    store.create_requirement({"id": "SHARED", "name": "Requirement wins"})
    store.create_component({"id": "SHARED", "name": "Component loses"})

    assert build_entity_index(store)["SHARED"][0] == "Requirement"
    assert resolve_entity_label(store, "SHARED")[0] == "Requirement"
