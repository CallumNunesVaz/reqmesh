"""Renaming a parameter rewrites every reference to it.

A parameter is referenced in expressions as ``owner.name`` (and, inside its
owner, bare ``name``) and in text as ``[[owner.name]]`` / ``owner.name``. None
of those is a link the registry tracks, so editing the name in place silently
breaks them — this rewrite sweeps them the way the requirement and component
renames sweep their own text references.
"""
import pytest

from app.core.dependencies import get_store
from app.services.rename import rename_parameter
from tests.conftest import make_req


def _rename(client, project, owner_id, old_name, new_name):
    return client.post(
        f"/api/projects/{project}/parameters/{owner_id}/rename",
        json={"old_name": old_name, "new_name": new_name},
    )


def _make_component(client, project, cid, **fields):
    body = {"id": cid, "name": fields.pop("name", cid), **fields}
    res = client.post(f"/api/projects/{project}/components", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_qualified_expression_reference_is_rewritten(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    make_req(client, project, "REQ-2", parameters=[{"name": "x", "expr": "REQ-1.temp_max * 2"}])

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    assert store.get_requirement("REQ-2")["parameters"][0]["expr"] == "REQ-1.temp_limit * 2"


def test_prefix_is_left_alone(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    make_req(client, project, "REQ-2", parameters=[{"name": "x", "expr": "REQ-1.temp_max_limit + 1"}])

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    assert store.get_requirement("REQ-2")["parameters"][0]["expr"] == "REQ-1.temp_max_limit + 1"


def test_bare_reference_in_own_constraint_is_rewritten(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}],
             constraints=[{"expr": "temp_max < 120"}])

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    assert store.get_requirement("REQ-1")["constraints"][0]["expr"] == "temp_limit < 120"


def test_bare_reference_in_another_requirement_is_left_alone(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    make_req(client, project, "REQ-2", constraints=[{"expr": "temp_max < 120"}])

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    assert store.get_requirement("REQ-2")["constraints"][0]["expr"] == "temp_max < 120"


def test_rich_text_mention_is_rewritten(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    make_req(client, project, "REQ-2", description="See [[REQ-1.temp_max]] for the limit")

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    desc = store.get_requirement("REQ-2")["description"]
    assert "[[REQ-1.temp_limit]]" in desc
    assert "temp_max" not in desc


def test_plain_text_mention_is_rewritten(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    make_req(client, project, "REQ-2", description="Do not exceed REQ-1.temp_max at altitude")

    r = _rename(client, project, "REQ-1", "temp_max", "temp_limit")
    assert r.status_code == 200, r.text
    desc = store.get_requirement("REQ-2")["description"]
    assert "REQ-1.temp_limit" in desc
    assert "temp_max" not in desc


def test_component_rollup_is_rewritten(client, project):
    store = get_store(project)
    _make_component(client, project, "C172", parameters=[{"name": "mass", "value": 767.0}])
    make_req(client, project, "REQ-1",
             constraints=[{"expr": "rollup('C172', 'mass') <= 1157"}])

    r = _rename(client, project, "C172", "mass", "weight")
    assert r.status_code == 200, r.text
    assert store.get_requirement("REQ-1")["constraints"][0]["expr"] == "rollup('C172', 'weight') <= 1157"


def test_unknown_owner_raises(client, project):
    store = get_store(project)
    with pytest.raises(ValueError, match=r"^unknown owner: GHOST$"):
        rename_parameter(store, "GHOST", "temp_max", "temp_limit")


def test_unknown_parameter_raises(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    with pytest.raises(ValueError, match=r"^unknown parameter: nope$"):
        rename_parameter(store, "REQ-1", "nope", "temp_limit")


def test_existing_parameter_raises(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[
        {"name": "temp_max", "value": 100.0},
        {"name": "temp_limit", "value": 90.0},
    ])
    with pytest.raises(ValueError, match=r"^parameter already exists: temp_limit$"):
        rename_parameter(store, "REQ-1", "temp_max", "temp_limit")


def test_invalid_parameter_name_raises(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}])
    with pytest.raises(ValueError, match=r"^invalid parameter name: temp max$"):
        rename_parameter(store, "REQ-1", "temp_max", "temp max")


def test_renaming_to_the_same_name_is_a_no_op(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}],
             constraints=[{"expr": "temp_max < 120"}])

    result = rename_parameter(store, "REQ-1", "temp_max", "temp_max")
    assert result["expressions_rewritten"] == 0
    assert result["mentions_rewritten"] == 0
    assert result["records_touched"] == []

    req = store.get_requirement("REQ-1")
    assert req["parameters"][0]["name"] == "temp_max"
    assert req["constraints"][0]["expr"] == "temp_max < 120"


def test_counts_match_the_records_actually_changed(client, project):
    store = get_store(project)
    make_req(client, project, "REQ-1", parameters=[{"name": "temp_max", "value": 100.0}],
             constraints=[{"expr": "temp_max < 120"}])
    make_req(client, project, "REQ-2",
             parameters=[{"name": "x", "expr": "REQ-1.temp_max * 2"}],
             description="See [[REQ-1.temp_max]]")
    make_req(client, project, "REQ-3", description="limit REQ-1.temp_max here")

    result = rename_parameter(store, "REQ-1", "temp_max", "temp_limit")
    assert result["expressions_rewritten"] == 2
    assert result["mentions_rewritten"] == 2
    assert result["records_touched"] == ["REQ-1", "REQ-2", "REQ-3"]
