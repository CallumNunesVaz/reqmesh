"""Deletes and creates behave the same way whichever entity kind you picked.

Three separate inconsistencies, all of them things a user could hit:

* the referential guard was enforced on every single-item DELETE and on none of
  the six bulk deletes, so ticking the rows first skipped it;
* four deletes reported success for an id that never existed while three 404'd;
* `delete_baseline` and `delete_system_state` returned the same number under two
  different key names.

Each test here fails against the pre-fix routes.
"""
from __future__ import annotations

import pytest

from tests.conftest import make_req


def _component(client, project, comp_id, **fields):
    res = client.post(f"/api/projects/{project}/components",
                      json={"id": comp_id, "name": fields.pop("name", comp_id), **fields})
    assert res.status_code == 201, res.text
    return res.json()


# ── The bulk paths honour the guard the single paths enforce ────────────────

class TestBulkDeleteRespectsReferrers:
    def test_a_referenced_requirement_survives_a_bulk_delete(self, client, project):
        make_req(client, project, "REQ-FREE")
        make_req(client, project, "REQ-HELD")
        _component(client, project, "C-001", satisfies=["REQ-HELD"])

        res = client.post(f"/api/projects/{project}/requirements/bulk-delete",
                          json={"ids": ["REQ-FREE", "REQ-HELD"]})
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["deleted"] == 1, "only the unreferenced one should go"
        assert "refused" in body, "the caller has to be told which were kept"
        assert any("REQ-HELD" in str(r) for r in body["refused"])

        assert client.get(f"/api/projects/{project}/requirements/REQ-FREE").status_code == 404
        assert client.get(f"/api/projects/{project}/requirements/REQ-HELD").status_code == 200

    def test_force_deletes_the_referenced_one_too(self, client, project):
        make_req(client, project, "REQ-HELD")
        _component(client, project, "C-001", satisfies=["REQ-HELD"])

        res = client.post(f"/api/projects/{project}/requirements/bulk-delete",
                          json={"ids": ["REQ-HELD"], "force": True})
        assert res.status_code == 200, res.text
        assert res.json()["deleted"] == 1
        assert client.get(f"/api/projects/{project}/requirements/REQ-HELD").status_code == 404

    def test_a_referenced_component_survives_a_bulk_delete(self, client, project):
        # `requirement.subject` is a non-tree link into components. A parent
        # link would not do: it is a tree link, and `check_deletable` passes
        # `include_tree=False` because the delete promotes children instead of
        # refusing.
        _component(client, project, "C-HELD")
        _component(client, project, "C-FREE")
        make_req(client, project, "REQ-001", subject="C-HELD")

        res = client.post(f"/api/projects/{project}/components/bulk-delete",
                          json={"ids": ["C-FREE", "C-HELD"]})
        assert res.status_code == 200, res.text
        body = res.json()

        assert client.get(f"/api/projects/{project}/components/C-FREE").status_code == 404
        assert client.get(f"/api/projects/{project}/components/C-HELD").status_code == 200
        assert body["deleted"] == 1
        assert any("C-HELD" in str(r) for r in body["refused"])

    def test_an_unknown_id_is_skipped_rather_than_counted(self, client, project):
        """A regression guard, not a fix.

        `bulk_delete_requirements` used to call `delete_requirement` blind where
        its siblings fetched first, and the obvious worry is that a missing id
        still counted. It did not — `delete_requirement` returns False and the
        count sat behind an `if`. This pins that, because the pre-fetch that was
        added for consistency now makes the two guards look redundant, and the
        wrong one could be removed later.
        """
        make_req(client, project, "REQ-REAL")

        res = client.post(f"/api/projects/{project}/requirements/bulk-delete",
                          json={"ids": ["REQ-REAL", "REQ-GHOST"]})
        assert res.status_code == 200, res.text
        assert res.json()["deleted"] == 1


# ── A delete of something that isn't there is a 404 ─────────────────────────

@pytest.mark.parametrize("path,expected", [
    ("definitions/NOPE", "Definition not found"),
    ("analysis/NOPE", "Analysis case not found"),
    ("baselines/NOPE", "Baseline not found"),
    ("system-states/NOPE", "System state not found"),
])
def test_deleting_something_that_does_not_exist_404s(client, project, path, expected):
    res = client.delete(f"/api/projects/{project}/{path}")
    assert res.status_code == 404, res.text
    assert res.json()["detail"] == expected


# ── 404 messages name their entity ──────────────────────────────────────────

def test_a_missing_comment_names_itself(client, project):
    res = client.delete(f"/api/projects/{project}/comments/NOPE")
    assert res.status_code == 404
    assert res.json()["detail"] == "Comment not found", \
        "it returned a bare 'Not found' while update_comment named the entity"


def test_impact_on_a_missing_requirement_names_itself(client, project):
    res = client.get(f"/api/projects/{project}/requirements/NOPE/impact")
    assert res.status_code == 404
    assert res.json()["detail"] == "Requirement not found"


def test_review_of_a_missing_requirement_names_itself(client, project):
    res = client.post(f"/api/projects/{project}/requirements/NOPE/review",
                      json={"comment": "looks fine"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Requirement not found"


# ── One name for one value ──────────────────────────────────────────────────

def test_both_deletes_report_the_cleared_count_under_the_same_key(client, project):
    """`delete_baseline` said `requirements_cleared`, `delete_system_state` said
    `requirements_affected`, for the same quantity."""
    client.post(f"/api/projects/{project}/baselines", json={"name": "PDR"})
    client.post(f"/api/projects/{project}/system-states", json={"name": "takeoff",
                                                               "description": ""})

    baseline = client.delete(f"/api/projects/{project}/baselines/PDR")
    assert baseline.status_code == 200, baseline.text
    assert "requirements_cleared" in baseline.json()

    state = client.delete(f"/api/projects/{project}/system-states/takeoff")
    assert state.status_code == 200, state.text
    assert "requirements_cleared" in state.json()
    assert "requirements_affected" not in state.json()


# ── The publish error lists only what this route accepts ────────────────────

def test_publish_rejects_a_bad_format_without_advertising_the_wrong_ones(client, project):
    res = client.post(f"/api/projects/{project}/publish", json={"format": "docx"})
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    # pdf and xlsx are download-route formats; POST /publish cannot produce them.
    assert "pdf" not in detail.split("use")[-1].split(";")[0]
    assert "xlsx" not in detail.split("use")[-1].split(";")[0]
