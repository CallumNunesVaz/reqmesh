"""The settled response shapes from task 099.

One ``detail`` shape (string or ``{error, message, ...}`` envelope) across every
raising path, and a typed bulk body that rejects a bare string in ``ids`` instead
of iterating it per-character. These are contract tests: the three detail cases
are asserted side by side so the shapes cannot diverge again.
"""

from __future__ import annotations

from tests.conftest import make_req


def _referenced_409_detail(client, project) -> dict:
    make_req(client, project, "REQ-HELD")
    client.post(f"/api/projects/{project}/components",
                json={"id": "C-001", "satisfies": ["REQ-HELD"]})
    res = client.delete(f"/api/projects/{project}/requirements/REQ-HELD")
    assert res.status_code == 409, res.text
    return res.json()["detail"]


def _bulk_422_detail(client, project) -> dict:
    make_req(client, project, "SYST0001")
    res = client.post(f"/api/projects/{project}/requirements/bulk",
                      json={"ids": ["SYST0001"], "updates": {"status": "not-a-status"}})
    assert res.status_code == 422, res.text
    return res.json()["detail"]


def _string_detail(client, project) -> str:
    res = client.get(f"/api/projects/{project}/requirements/NOPE")
    assert res.status_code == 404, res.text
    return res.json()["detail"]


def test_detail_has_one_settled_shape(client, project):
    """Three raising paths, one shape.

    Structured errors (the delete guard's 409, the bulk routes' 422) share a
    single ``{error, message, ...}`` envelope with a stable ``error``
    discriminator; plain errors stay a plain string. FastAPI's own request
    validation (a list of error objects) is the one documented exception.
    """
    referenced = _referenced_409_detail(client, project)
    validation = _bulk_422_detail(client, project)

    # Both structured cases are the same envelope: a discriminator + a message.
    for detail in (referenced, validation):
        assert isinstance(detail, dict)
        assert set(detail) >= {"error", "message"}
        assert isinstance(detail["error"], str)
        assert isinstance(detail["message"], str)

    # The discriminator distinguishes the kind; both carry the same two keys.
    assert referenced["error"] == "referenced"
    assert validation["error"] == "validation"
    assert set(referenced.keys()) >= {"error", "message"}
    assert set(validation.keys()) >= {"error", "message"}

    # The common case is still a plain string.
    assert isinstance(_string_detail(client, project), str)


def test_bulk_rejects_a_bare_string_for_ids(client, project):
    """A bare string in ``ids`` used to iterate per-character and no-op.

    ``ids`` is now a typed ``list[str]`` on the request model, so the string is
    rejected with a 422 before any write happens.
    """
    make_req(client, project, "SYST0001")
    res = client.post(f"/api/projects/{project}/requirements/bulk",
                      json={"ids": "SYST0001", "updates": {"status": "approved"}})
    assert res.status_code == 422, res.text
    # Nothing was written: the requirement is still in its default state.
    assert client.get(f"/api/projects/{project}/requirements/SYST0001").json()["status"] == "proposed"


# ── paginate: one return type ────────────────────────────────────────────────
#
# `paginate` used to return a bare list when neither offset nor limit was given
# and the envelope otherwise, so a client could not tell which it would get
# without knowing how it had been called. Eleven tests elsewhere fail if that
# regresses, but none of them says so — they fail on `.items` of a list, which
# reads as a bug in the caller. These assert the contract directly.

def test_paginate_always_returns_the_envelope():
    from app.api._utils import paginate

    items = [{"id": f"R{i}"} for i in range(5)]

    unpaged = paginate(items)
    assert set(unpaged) == {"items", "total", "offset", "limit"}
    assert unpaged["items"] == items
    assert unpaged["total"] == 5

    paged = paginate(items, offset=1, limit=2)
    assert set(paged) == {"items", "total", "offset", "limit"}
    assert paged["items"] == items[1:3]
    assert paged["total"] == 5, "total is the collection size, not the page size"


def test_paginate_unpaged_still_caps_at_max_limit():
    """The cap predates the envelope and must survive it — an unpaged call on a
    large collection returns max_limit items, not everything."""
    from app.api._utils import paginate

    items = [{"id": f"R{i}"} for i in range(2500)]
    assert len(paginate(items)["items"]) == 2000
    assert paginate(items)["total"] == 2500
