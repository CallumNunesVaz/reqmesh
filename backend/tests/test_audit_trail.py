"""Audit trail for the four entity kinds that used to mutate without one.

Comments, definitions, analysis cases and verification runs all changed state
with no ``record_change`` call, so the activity feed and the changelog silently
under-reported them. Definitions and analysis cases were also written through
``YamlStore.write_item``, which stamps no ``created``/``modified`` — leaving
their optimistic-concurrency guard dead. These tests pin both fixes.
"""

from __future__ import annotations

from tests.conftest import make_req


def _actions(client, project, item_id: str) -> list[str]:
    res = client.get(f"/api/projects/{project}/history/{item_id}")
    assert res.status_code == 200, res.text
    return [e.get("action") for e in res.json()]


def test_comment_create_update_delete_are_audited(client, project):
    make_req(client, project, "REQ-1")
    created = client.post(
        f"/api/projects/{project}/comments",
        json={"entity_kind": "requirements", "entity_id": "REQ-1", "text": "hello"},
    ).json()
    comment_id = created["id"]

    assert client.patch(
        f"/api/projects/{project}/comments/{comment_id}",
        json={"resolved": True},
    ).status_code == 200
    assert client.delete(f"/api/projects/{project}/comments/{comment_id}").status_code == 200

    actions = _actions(client, project, comment_id)
    assert "create" in actions, actions
    assert "update" in actions, actions
    assert "delete" in actions, actions


def test_definition_create_update_delete_are_audited(client, project):
    body = {"id": "DEF-1", "type": "constraint", "parameters": ["a", "b"], "expr": "a <= b"}
    assert client.post(f"/api/projects/{project}/definitions", json=body).status_code == 201
    assert client.put(
        f"/api/projects/{project}/definitions/DEF-1", json={"expr": "a < b"},
    ).status_code == 200
    assert client.delete(f"/api/projects/{project}/definitions/DEF-1").status_code == 200

    actions = _actions(client, project, "DEF-1")
    assert "create" in actions, actions
    assert "update" in actions, actions
    assert "delete" in actions, actions


def test_analysis_case_create_update_delete_are_audited(client, project):
    body = {"id": "AN-1", "name": "Overweight", "scope": ["R1"], "overrides": {"R1.mass": 200.0}}
    assert client.post(f"/api/projects/{project}/analysis", json=body).status_code == 201
    assert client.put(
        f"/api/projects/{project}/analysis/AN-1", json={"name": "Renamed"},
    ).status_code == 200
    assert client.delete(f"/api/projects/{project}/analysis/AN-1").status_code == 200

    actions = _actions(client, project, "AN-1")
    assert "create" in actions, actions
    assert "update" in actions, actions
    assert "delete" in actions, actions


def test_verification_run_is_audited(client, project):
    client.post(f"/api/projects/{project}/verification", json={"id": "VC-1", "method": "test"})
    res = client.post(
        f"/api/projects/{project}/verification/VC-1/run",
        json={"status": "passed", "notes": "ran it"},
    )
    assert res.status_code == 200, res.text

    actions = _actions(client, project, "VC-1")
    assert "execute" in actions, actions


def test_bulk_update_specifications_records_one_history_entry_per_item(client, project):
    client.post(f"/api/projects/{project}/specifications", json={"id": "SPEC-1", "name": "one"})
    client.post(f"/api/projects/{project}/specifications", json={"id": "SPEC-2", "name": "two"})

    res = client.post(
        f"/api/projects/{project}/specifications/bulk",
        json={"ids": ["SPEC-1", "SPEC-2"], "updates": {"description": "bulk desc"}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 2

    for spec_id in ("SPEC-1", "SPEC-2"):
        updates = [a for a in _actions(client, project, spec_id) if a == "update"]
        assert len(updates) == 1, (spec_id, updates)


def test_definition_stale_if_match_returns_409(client, project):
    """The optimistic-concurrency guard works for definitions.

    Before the fix definitions were written via ``write_item``, which stamps no
    ``modified`` token, so ``check_precondition`` could never match and the
    guard was dead code.
    """
    res = client.post(
        f"/api/projects/{project}/definitions",
        json={"id": "DEF-CONC", "type": "constraint", "parameters": ["a", "b"], "expr": "a <= b"},
    )
    assert res.status_code == 201
    original_modified = res.json()["modified"]

    r1 = client.put(
        f"/api/projects/{project}/definitions/DEF-CONC",
        json={"expr": "a < b"},
        headers={"If-Match": original_modified},
    )
    assert r1.status_code == 200, r1.text

    r2 = client.put(
        f"/api/projects/{project}/definitions/DEF-CONC",
        json={"expr": "a > b"},
        headers={"If-Match": original_modified},
    )
    assert r2.status_code == 409, r2.text
    assert "DEF-CONC" in r2.json()["detail"]
