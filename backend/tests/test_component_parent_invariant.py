"""A component's parent is always another component.

Components form their own hierarchy and reach requirements through
``satisfies``; parenthood is design structure, not traceability. Every write
path enforced that except ``POST /components/bulk``, which validated only the
shape — ``ComponentUpdate.parent`` is a bare ``Optional[str]`` — so a
requirement id could be written there and then sit on disk unseen, because
``build_flat_tree`` buckets an unresolvable parent under ``None`` and the
component renders as a root.
"""
from app.core.dependencies import get_store
from tests.conftest import make_req


def _comp(client, project, cid, **fields):
    body = {"id": cid, "name": fields.pop("name", cid), **fields}
    r = client.post(f"/api/projects/{project}/components", json=body)
    assert r.status_code == 201, r.text
    return r


def _bulk(client, project, ids, updates):
    return client.post(
        f"/api/projects/{project}/components/bulk",
        json={"ids": ids, "updates": updates},
    )


# ── The hole ─────────────────────────────────────────────────────────────────

def test_bulk_update_refuses_a_requirement_id_as_parent(client, project):
    """The reported bug, at the layer that allowed it."""
    make_req(client, project, "SYS-1", name="Wing Assembly")
    _comp(client, project, "WING", name="Wing Assembly")

    r = _bulk(client, project, ["WING"], {"parent": "SYS-1"})
    assert r.status_code == 400
    assert "SYS-1" in r.json()["detail"]

    # And nothing was written.
    assert get_store(project).get_component("WING").get("parent") in (None, "")


def test_bulk_update_refuses_a_parent_that_does_not_exist_at_all(client, project):
    _comp(client, project, "WING")

    r = _bulk(client, project, ["WING"], {"parent": "NOPE"})
    assert r.status_code == 400
    assert get_store(project).get_component("WING").get("parent") in (None, "")


def test_bulk_update_refuses_a_cycle(client, project):
    store = get_store(project)
    _comp(client, project, "SYS")
    _comp(client, project, "SUB", parent="SYS")

    r = _bulk(client, project, ["SYS"], {"parent": "SUB"})
    assert r.status_code == 400
    assert store.get_component("SYS").get("parent") in (None, "")


def test_one_bad_id_in_a_batch_writes_none_of_them(client, project):
    """Validated for every id before anything is written, so a batch does not
    land half of itself."""
    store = get_store(project)
    _comp(client, project, "ROOT")
    _comp(client, project, "A")
    _comp(client, project, "B")

    # "B" under "ROOT" is fine; "ROOT" under itself is not.
    r = _bulk(client, project, ["A", "ROOT"], {"parent": "ROOT"})
    assert r.status_code == 400
    assert store.get_component("A").get("parent") in (None, "")


# ── Still permits what it should ─────────────────────────────────────────────

def test_bulk_update_accepts_a_real_component_parent(client, project):
    _comp(client, project, "SYS")
    _comp(client, project, "SUB")

    r = _bulk(client, project, ["SUB"], {"parent": "SYS"})
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert get_store(project).get_component("SUB")["parent"] == "SYS"


def test_bulk_update_of_an_unrelated_field_is_unaffected(client, project):
    """The guard is gated on `parent` being present, so the common path — the
    UI only ever sends `{type}` — does not pay for it."""
    _comp(client, project, "WING")

    r = _bulk(client, project, ["WING"], {"type": "subsystem"})
    assert r.status_code == 200
    assert get_store(project).get_component("WING")["type"] == "subsystem"


def test_bulk_update_refuses_a_dangling_satisfies_link(client, project):
    """Same omission, same consequence: a link to something that does not exist
    is a silent hole in traceability."""
    _comp(client, project, "WING")

    r = _bulk(client, project, ["WING"], {"satisfies": ["NO-SUCH-REQ"]})
    assert r.status_code == 400
    assert "NO-SUCH-REQ" in r.json()["detail"]


def test_bulk_update_records_history(client, project):
    """Bulk component edits recorded nothing, while the requirements handler
    beside them always has — so the audit trail depended on which button the
    user reached the edit through."""
    _comp(client, project, "WING")

    assert _bulk(client, project, ["WING"], {"type": "subsystem"}).status_code == 200

    r = client.get(f"/api/projects/{project}/history/WING")
    assert r.status_code == 200
    entries = r.json()
    assert any(e["action"] == "update" for e in entries), entries
