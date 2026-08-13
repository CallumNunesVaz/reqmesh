"""Comments attach to any commentable entity — not just requirements.

Before the model carried ``entity_kind`` + ``entity_id``, a comment could only
target a requirement, so a risk or a change request could not be discussed at
all.  These tests assert the new shape round-trips through every commentable
collection, that the legacy ``requirement_id`` path is now rejected, and that
the delete guard respects the comment link direction so a comment on a risk does
**not** block deleting a requirement of the same id.
"""

from __future__ import annotations


from tests.conftest import make_req


def _make_risk(client, project_id, risk_id, **fields):
    body = {"id": risk_id, "title": risk_id, **fields}
    res = client.post(f"/api/projects/{project_id}/risks", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _make_cr(client, project_id, cr_id, **fields):
    body = {"id": cr_id, "title": cr_id, **fields}
    res = client.post(f"/api/projects/{project_id}/change-requests", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _make_component(client, project_id, cid, **fields):
    body = {"id": cid, "name": cid, **fields}
    res = client.post(f"/api/projects/{project_id}/components", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _create_comment(client, project_id, *, entity_kind, entity_id, text="test comment"):
    res = client.post(
        f"/api/projects/{project_id}/comments",
        json={"entity_kind": entity_kind, "entity_id": entity_id, "text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _list_comments(client, project_id, *, entity_kind=None, entity_id=None):
    qs_parts = []
    if entity_kind:
        qs_parts.append(f"entity_kind={entity_kind}")
    if entity_id:
        qs_parts.append(f"entity_id={entity_id}")
    qs = "?" + "&".join(qs_parts) if qs_parts else ""
    return client.get(f"/api/projects/{project_id}/comments{qs}").json()["items"]


# ── round-trips ──────────────────────────────────────────────────────────────


def test_comment_on_risk_roundtrips(client, project):
    _make_risk(client, project, "RSK-1")
    c = _create_comment(client, project, entity_kind="risks", entity_id="RSK-1")
    assert c["entity_kind"] == "risks"
    assert c["entity_id"] == "RSK-1"

    listed = _list_comments(client, project, entity_kind="risks", entity_id="RSK-1")
    assert isinstance(listed, list)
    assert len(listed) == 1
    assert listed[0]["id"] == c["id"]


def test_comment_on_component_roundtrips(client, project):
    _make_component(client, project, "C-001")
    c = _create_comment(client, project, entity_kind="components", entity_id="C-001")
    assert c["entity_kind"] == "components"
    assert c["entity_id"] == "C-001"

    listed = _list_comments(client, project, entity_kind="components", entity_id="C-001")
    assert len(listed) == 1
    assert listed[0]["id"] == c["id"]


def test_comment_on_change_request_roundtrips(client, project):
    _make_cr(client, project, "CR-001")
    c = _create_comment(client, project, entity_kind="change_requests", entity_id="CR-001")
    assert c["entity_kind"] == "change_requests"
    assert c["entity_id"] == "CR-001"

    listed = _list_comments(client, project, entity_kind="change_requests", entity_id="CR-001")
    assert len(listed) == 1
    assert listed[0]["id"] == c["id"]


# ── filtering ────────────────────────────────────────────────────────────────


def test_entity_id_without_entity_kind_is_400(client, project):
    res = client.get(f"/api/projects/{project}/comments?entity_id=R-1")
    assert res.status_code == 400
    assert "entity_kind" in res.text.lower()


def test_legacy_requirement_id_on_create_is_422(client, project):
    make_req(client, project, "REQ-LEGACY")
    res = client.post(
        f"/api/projects/{project}/comments",
        json={"requirement_id": "REQ-LEGACY", "text": "via legacy field"},
    )
    assert res.status_code == 422, res.text


def test_list_by_legacy_requirement_id_is_ignored(client, project):
    """The legacy query parameter is ignored — all comments are returned, not
    just the one that would have matched."""
    make_req(client, project, "REQ-OLDQ")
    make_req(client, project, "REQ-OTHER")
    c1 = _create_comment(client, project, entity_kind="requirements", entity_id="REQ-OLDQ")
    c2 = _create_comment(client, project, entity_kind="requirements", entity_id="REQ-OTHER",
                         text="another")
    # Query with the deprecated parameter — the filter is ignored so all
    # comments come back, not just the one on REQ-OLDQ.
    res = client.get(f"/api/projects/{project}/comments?requirement_id=REQ-OLDQ")
    assert res.status_code == 200
    body = res.json()["items"]
    assert isinstance(body, list)
    ids = {x["id"] for x in body}
    assert c1["id"] in ids  # present, but because *all* comments are returned
    assert c2["id"] in ids  # also present, proving the filter was ignored


def test_invalid_entity_kind_is_422(client, project):
    res = client.post(
        f"/api/projects/{project}/comments",
        json={"entity_kind": "nonsense", "entity_id": "X", "text": "bad"},
    )
    assert res.status_code == 422


# ── same id, different collections ───────────────────────────────────────────


def test_same_id_in_two_collections_does_not_cross_leak(client, project):
    """A risk and a requirement sharing the same id each return only their own comments."""
    make_req(client, project, "DUPE-1", name="dupe req")
    _make_risk(client, project, "DUPE-1", title="dupe risk")

    rc = _create_comment(client, project, entity_kind="requirements", entity_id="DUPE-1",
                         text="on req")
    rsc = _create_comment(client, project, entity_kind="risks", entity_id="DUPE-1",
                          text="on risk")

    req_comments = _list_comments(client, project, entity_kind="requirements", entity_id="DUPE-1")
    risk_comments = _list_comments(client, project, entity_kind="risks", entity_id="DUPE-1")

    req_ids = {c["id"] for c in req_comments}
    risk_ids = {c["id"] for c in risk_comments}

    assert rc["id"] in req_ids
    assert rc["id"] not in risk_ids
    assert rsc["id"] in risk_ids
    assert rsc["id"] not in req_ids


# ── delete guard ─────────────────────────────────────────────────────────────


def test_commented_risk_cannot_be_deleted_without_force(client, project):
    _make_risk(client, project, "RSK-LOCK")
    _create_comment(client, project, entity_kind="risks", entity_id="RSK-LOCK")
    res = client.delete(f"/api/projects/{project}/risks/RSK-LOCK")
    assert res.status_code == 409
    assert "comment" in res.text.lower() or "referenced" in res.text.lower()


def test_risk_comment_does_not_block_deleting_same_id_requirement(client, project):
    """A comment on a risk should not block deleting a requirement that happens to share the id."""
    make_req(client, project, "SHARED-1", name="shared req")
    _make_risk(client, project, "SHARED-1", title="shared risk")
    _create_comment(client, project, entity_kind="risks", entity_id="SHARED-1")
    # Deleting the *requirement* with the same id must succeed — the comment
    # targets the risk, not the requirement.
    res = client.delete(f"/api/projects/{project}/requirements/SHARED-1")
    assert res.status_code == 200, res.text
