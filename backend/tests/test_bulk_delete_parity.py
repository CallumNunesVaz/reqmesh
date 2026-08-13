"""Bulk delete parity for the four pages that gained selection.

Decisions, analysis cases, definitions and system states now expose the same
bulk-delete bar the six equipped pages have. The referential guard the single
deletes enforce must also hold on the bulk path for the three kinds that can be
referenced (decisions, analysis cases, definitions all accept comments); system
states are never targeted by the link registry, so their bulk delete skips the
guard deliberately, mirroring the single delete.
"""
from __future__ import annotations


def _make_decision(client, project, dec_id):
    res = client.post(f"/api/projects/{project}/decisions", json={"id": dec_id, "title": dec_id})
    assert res.status_code == 201, res.text
    return res.json()


def _make_definition(client, project, def_id):
    res = client.post(f"/api/projects/{project}/definitions", json={"id": def_id, "expr": "x"})
    assert res.status_code == 201, res.text
    return res.json()


def _make_analysis_case(client, project, case_id):
    res = client.post(f"/api/projects/{project}/analysis", json={"id": case_id, "name": case_id})
    assert res.status_code == 201, res.text
    return res.json()


def _comment_on(client, project, entity_kind, entity_id):
    res = client.post(
        f"/api/projects/{project}/comments",
        json={"entity_kind": entity_kind, "entity_id": entity_id, "text": "hold"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _state(client, project, name):
    res = client.post(f"/api/projects/{project}/system-states", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


class TestBulkDeleteRespectsReferrers:
    """The guard the single deletes enforce also holds on the bulk path."""

    def test_a_referenced_decision_survives_a_bulk_delete(self, client, project):
        _make_decision(client, project, "DEC-FREE")
        _make_decision(client, project, "DEC-HELD")
        _comment_on(client, project, "decisions", "DEC-HELD")

        res = client.post(f"/api/projects/{project}/decisions/bulk-delete",
                          json={"ids": ["DEC-FREE", "DEC-HELD"]})
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["deleted"] == 1
        assert "refused" in body
        assert any("DEC-HELD" in str(r) for r in body["refused"])

        assert client.get(f"/api/projects/{project}/decisions/DEC-FREE").status_code == 404
        assert client.get(f"/api/projects/{project}/decisions/DEC-HELD").status_code == 200

    def test_a_referenced_definition_survives_a_bulk_delete(self, client, project):
        _make_definition(client, project, "MassBudget")
        _make_definition(client, project, "PowerMargin")
        _comment_on(client, project, "definitions", "PowerMargin")

        res = client.post(f"/api/projects/{project}/definitions/bulk-delete",
                          json={"ids": ["MassBudget", "PowerMargin"]})
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["deleted"] == 1
        assert any("PowerMargin" in str(r) for r in body["refused"])
        assert client.get(f"/api/projects/{project}/definitions/MassBudget").status_code == 404
        assert client.get(f"/api/projects/{project}/definitions/PowerMargin").status_code == 200

    def test_a_referenced_analysis_case_survives_a_bulk_delete(self, client, project):
        _make_analysis_case(client, project, "heavy")
        _make_analysis_case(client, project, "cold")
        _comment_on(client, project, "analysis_cases", "cold")

        res = client.post(f"/api/projects/{project}/analysis/bulk-delete",
                          json={"ids": ["heavy", "cold"]})
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["deleted"] == 1
        assert any("cold" in str(r) for r in body["refused"])
        assert client.get(f"/api/projects/{project}/analysis/heavy").status_code == 404
        assert client.get(f"/api/projects/{project}/analysis/cold").status_code == 200

    def test_force_deletes_the_referenced_one_too(self, client, project):
        _make_decision(client, project, "DEC-HELD")
        _comment_on(client, project, "decisions", "DEC-HELD")

        res = client.post(f"/api/projects/{project}/decisions/bulk-delete",
                          json={"ids": ["DEC-HELD"], "force": True})
        assert res.status_code == 200, res.text
        assert res.json()["deleted"] == 1
        assert client.get(f"/api/projects/{project}/decisions/DEC-HELD").status_code == 404


class TestBulkDeleteSystemStates:
    """System states skip the guard deliberately — nothing targets them."""

    def test_bulk_delete_removes_exactly_the_named_states(self, client, project):
        _state(client, project, "takeoff")
        _state(client, project, "cruise")
        _state(client, project, "landing")

        res = client.post(f"/api/projects/{project}/system-states/bulk-delete",
                          json={"ids": ["takeoff", "landing"]})
        assert res.status_code == 200, res.text
        assert res.json() == {"deleted": 2}

        names = [s["name"] for s in client.get(f"/api/projects/{project}/system-states").json()["states"]]
        assert names == ["cruise"]
