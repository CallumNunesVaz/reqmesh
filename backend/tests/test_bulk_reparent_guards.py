"""Bulk reparent: cycle refusal, dry-run preview, and audit trail.

The bulk path used to accept moves the single-item PUT refuses, perform a
project-wide id rewrite with no way to see it first, and record nothing in
history while doing it.
"""
from app.core.dependencies import get_store
from tests.conftest import make_req


def _reparent(client, project, ids, parent, **extra):
    return client.post(
        f"/api/projects/{project}/requirements/bulk-reparent",
        json={"ids": ids, "parent": parent, **extra},
    )


# ── Cycles ───────────────────────────────────────────────────────────────────

def test_cannot_move_a_requirement_under_itself(client, project):
    make_req(client, project, "SYS-1", name="Root")

    r = _reparent(client, project, ["SYS-1"], "SYS-1")
    assert r.status_code == 400
    assert "own parent" in r.json()["detail"]


def test_cannot_move_a_requirement_under_its_own_descendant(client, project):
    """The single-item PUT has always refused this; the bulk path did not, so
    both branches became unreachable in the tree."""
    store = get_store(project)
    make_req(client, project, "SYS-1", name="Root")
    make_req(client, project, "SYS-2", name="Child")
    store.update_requirement("SYS-2", {"parent": "SYS-1"})

    r = _reparent(client, project, ["SYS-1"], "SYS-2")
    assert r.status_code == 400
    assert "cycle" in r.json()["detail"].lower()

    # Nothing moved.
    assert store.get_requirement("SYS-1").get("parent") in (None, "")
    assert store.get_requirement("SYS-2")["parent"] == "SYS-1"


def test_components_cannot_be_moved_under_their_own_descendant(client, project):
    client.post(f"/api/projects/{project}/components", json={"id": "C1", "name": "One"})
    client.post(f"/api/projects/{project}/components", json={"id": "C2", "name": "Two", "parent": "C1"})

    r = client.post(f"/api/projects/{project}/components/bulk-reparent",
                    json={"ids": ["C1"], "parent": "C2"})
    assert r.status_code == 400

    store = get_store(project)
    assert store.get_component("C2")["parent"] == "C1"


def test_component_bulk_reparent_rejects_a_missing_parent(client, project):
    client.post(f"/api/projects/{project}/components", json={"id": "C1", "name": "One"})

    r = client.post(f"/api/projects/{project}/components/bulk-reparent",
                    json={"ids": ["C1"], "parent": "NOPE"})
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


def test_component_bulk_reparent_still_detaches_with_a_null_parent(client, project):
    client.post(f"/api/projects/{project}/components", json={"id": "C1", "name": "One"})
    client.post(f"/api/projects/{project}/components", json={"id": "C2", "name": "Two", "parent": "C1"})

    r = client.post(f"/api/projects/{project}/components/bulk-reparent",
                    json={"ids": ["C2"], "parent": None})
    assert r.status_code == 200, r.text
    assert get_store(project).get_component("C2").get("parent") in (None, "")


# ── Dry run ──────────────────────────────────────────────────────────────────

def _snapshot(store):
    return sorted((r["id"], r.get("parent"), str(r.get("relations")))
                  for r in store.list_requirements())


def test_dry_run_writes_nothing(client, project):
    store = get_store(project)
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "SYS-A", name="Moving")
    make_req(client, project, "SYS-A-1", name="Child")
    store.update_requirement("SYS-A-1", {"parent": "SYS-A"})
    before = _snapshot(store)

    r = _reparent(client, project, ["SYS-A"], "NEW-001", re_prefix=True, dry_run=True)
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True

    assert _snapshot(store) == before


def test_dry_run_renames_match_the_real_move_exactly(client, project):
    """The preview shares the planner with the write path, so it cannot drift."""
    store = get_store(project)
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "NEW-002", name="Blocker")
    make_req(client, project, "SYS-A", name="Moving")
    make_req(client, project, "SYS-A-1", name="Child")
    store.update_requirement("SYS-A-1", {"parent": "SYS-A"})

    preview = _reparent(client, project, ["SYS-A"], "NEW-001",
                        re_prefix=True, dry_run=True).json()
    real = _reparent(client, project, ["SYS-A"], "NEW-001", re_prefix=True).json()

    assert preview["renames"] == real["renames"]
    assert preview["renames"], "expected the move to rename something"
    assert sorted(x["to"] for x in preview["renames"]) == sorted(real["ids"])


def test_dry_run_reports_the_affected_count_without_re_prefix(client, project):
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "SYS-A", name="Moving")

    r = _reparent(client, project, ["SYS-A"], "NEW-001", dry_run=True)
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    # Nothing is renamed when re_prefix is off — this is the default the UI uses.
    assert r.json()["renames"] == []


def test_dry_run_surfaces_a_cycle_before_anything_is_written(client, project):
    store = get_store(project)
    make_req(client, project, "SYS-1", name="Root")
    make_req(client, project, "SYS-2", name="Child")
    store.update_requirement("SYS-2", {"parent": "SYS-1"})

    r = _reparent(client, project, ["SYS-1"], "SYS-2", dry_run=True)
    assert r.status_code == 400


# ── History ──────────────────────────────────────────────────────────────────

def test_a_move_is_recorded_in_history(client, project):
    """A project-wide id rewrite left no audit trail at all before this."""
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "SYS-A", name="Moving")

    _reparent(client, project, ["SYS-A"], "NEW-001")

    hist = client.get(f"/api/projects/{project}/history/SYS-A").json()
    assert any(e.get("action") == "reparent" for e in hist), hist


def test_a_renamed_requirement_records_history_under_its_new_id(client, project):
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "SYS-A", name="Moving")

    res = _reparent(client, project, ["SYS-A"], "NEW-001", re_prefix=True).json()
    new_id = res["ids"][0]

    hist = client.get(f"/api/projects/{project}/history/{new_id}").json()
    assert any(e.get("action") == "reparent" for e in hist), hist


# ── Unchanged behaviour ──────────────────────────────────────────────────────

def test_moving_to_top_level_still_works(client, project):
    store = get_store(project)
    make_req(client, project, "SYS-1", name="Root")
    make_req(client, project, "SYS-2", name="Child")
    store.update_requirement("SYS-2", {"parent": "SYS-1"})

    r = _reparent(client, project, ["SYS-2"], None)
    assert r.status_code == 200, r.text
    assert store.get_requirement("SYS-2").get("parent") in (None, "")


def test_an_unknown_id_is_skipped_not_fatal(client, project):
    make_req(client, project, "NEW-001", name="Destination")
    make_req(client, project, "SYS-A", name="Moving")

    r = _reparent(client, project, ["SYS-A", "GHOST-9"], "NEW-001")
    assert r.status_code == 200, r.text
    assert r.json()["ids"] == ["SYS-A"]
