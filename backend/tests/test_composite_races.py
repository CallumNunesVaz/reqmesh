"""C1/C2 — composite-operation ordering races.

C2 is the delete TOCTOU: ``check_deletable`` scans referrers outside any lock and
the caller then removes the file, so a reference created in that window is stored
against a missing id. Fixed by serialising the scan and the removal under a
project-scoped lock.

C1 is the composite operations that remain non-atomic: ``rename_requirement``
and ``reparent``. The tests here are *characterisation* tests — they assert the
state the code produces today, not the state it should produce, and they are
expected to change when a follow-up makes those operations atomic.
"""
from __future__ import annotations

import threading

from app.core.dependencies import get_store
from app.services.integrity import IntegrityChecker
from app.services.rename import rename_requirement
from app.services.reparent import apply_reparent, plan_reparent
from tests.conftest import make_req
from tests.test_concurrency import Latch


def _run(fn):
    """Run *fn* on a fresh thread, returning ``(thread, errors)``."""
    errors = []

    def wrap():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - reported by the caller
            errors.append(exc)

    t = threading.Thread(target=wrap)
    t.start()
    return t, errors


def _pause_first_find_referrers(monkeypatch, scanned: Latch, resumed: Latch) -> None:
    """Make the *first* ``find_referrers`` call pause after scanning.

    The first call is the delete under test (the seam is inside
    ``check_deletable``, i.e. between the scan and the removal). Pausing on the
    first call only keeps a second scan (a bulk loop, or another project's
    delete) running through un-paused.
    """
    import app.services.delete_guard as dg

    real = dg.find_referrers
    state = {"paused": False}

    def pausing(store, collection, item_id, include_tree=True):
        result = real(store, collection, item_id, include_tree)
        if not state["paused"]:
            state["paused"] = True
            scanned.release()
            resumed.wait()
        return result

    monkeypatch.setattr(dg, "find_referrers", pausing)


def _wait_quietly(latch: Latch, timeout: float = 2.0) -> None:
    """Wait for a rendezvous that may legitimately not happen.

    The reference creation completes inside the delete's scan/remove window on
    the *unfixed* code, but blocks on the delete's project lock on the fixed
    code. Waiting for it here makes the unfixed failure deterministic; the
    interleaving itself is still established by the scanned/resumed latches.
    """
    try:
        latch.wait(timeout=timeout)
    except AssertionError:
        pass


class TestC2DeleteTOCTOU:
    def test_reference_created_during_window_is_not_dangling(self, client, project, monkeypatch):
        """C2 — a reference created between the scan and the removal must not
        be stored against a missing id. The reference creation is serialised
        behind the delete's project lock and, seeing the id gone, is refused."""
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Doomed")
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": "SPEC-1", "name": "Spec", "requirements": []})

        scanned = Latch("delete scanned")
        resumed = Latch("resume delete")
        _pause_first_find_referrers(monkeypatch, scanned, resumed)

        statuses = {}

        def do_delete():
            res = client.delete(f"/api/projects/{project}/requirements/REQ-001")
            statuses["delete"] = res.status_code

        reference_done = Latch("reference creation finished")

        def do_reference():
            res = client.put(f"/api/projects/{project}/specifications/SPEC-1",
                             json={"requirements": ["REQ-001"]})
            statuses["reference"] = res.status_code
            reference_done.release()

        delete_thread, delete_errors = _run(do_delete)
        scanned.wait()

        reference_thread, reference_errors = _run(do_reference)
        _wait_quietly(reference_done)

        resumed.release()
        delete_thread.join(timeout=30)
        reference_thread.join(timeout=30)
        assert not delete_errors, f"delete worker raised: {delete_errors}"
        assert not reference_errors, f"reference worker raised: {reference_errors}"

        assert store.get_requirement("REQ-001") is None
        spec = store.get_item("specifications", "SPEC-1")
        assert "REQ-001" not in (spec.get("requirements") or [])

    def test_force_path_still_deletes_and_reports_dangling(self, client, project, monkeypatch):
        """C2 force path — ``force=true`` keeps its meaning: the reference is
        left pointing at the removed id and the integrity check reports it,
        rather than the guard refusing the delete. The reference is written with
        the store directly so it is not refused by the write-time link check."""
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Doomed")
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": "SPEC-1", "name": "Spec", "requirements": []})

        scanned = Latch("delete scanned")
        resumed = Latch("resume delete")
        _pause_first_find_referrers(monkeypatch, scanned, resumed)

        statuses = {}

        def do_delete():
            res = client.delete(f"/api/projects/{project}/requirements/REQ-001?force=true")
            statuses["delete"] = res.status_code

        delete_thread, delete_errors = _run(do_delete)
        scanned.wait()

        # The reference is written straight to the store while the delete holds
        # the project lock, so the interleaving is exactly the C2 window.
        get_store(project).update_item("specifications", "SPEC-1",
                                       {"requirements": ["REQ-001"]})

        resumed.release()
        delete_thread.join(timeout=30)
        assert not delete_errors, f"delete worker raised: {delete_errors}"

        assert statuses["delete"] == 200, statuses
        assert store.get_requirement("REQ-001") is None
        spec = store.get_item("specifications", "SPEC-1")
        assert spec.get("requirements") == ["REQ-001"], "force delete must not rewrite the referrer"

        issues = IntegrityChecker(get_store(project)).check_all()["issues"]
        assert any(i.get("type") == "dangling_reference" and i.get("id") == "SPEC-1"
                   for i in issues), issues

    def test_delete_in_one_project_does_not_block_another(self, client, project, monkeypatch):
        """C2 no false serialisation — the lock is project-scoped, so a delete
        in project A must not hold up a delete in project B."""
        client.post("/api/projects", json={"id": "other", "name": "Other"})
        client.patch("/api/projects/other", json={"naming": {"enforce": False}})
        make_req(client, project, "REQ-A-1")
        make_req(client, "other", "REQ-B-1")

        scanned = Latch("project A scanned")
        resumed = Latch("resume project A")
        _pause_first_find_referrers(monkeypatch, scanned, resumed)

        def delete_a():
            client.delete(f"/api/projects/{project}/requirements/REQ-A-1")

        b_done = Latch("project B delete finished")

        def delete_b():
            client.delete("/api/projects/other/requirements/REQ-B-1")
            b_done.release()

        a_thread, a_errors = _run(delete_a)
        scanned.wait()  # A is now paused, holding its project lock

        b_thread, b_errors = _run(delete_b)
        # B must complete while A still holds its (different) project lock.
        b_done.wait(timeout=3)

        resumed.release()
        a_thread.join(timeout=30)
        b_thread.join(timeout=30)
        assert not a_errors, f"A worker raised: {a_errors}"
        assert not b_errors, f"B worker raised: {b_errors}"

        assert get_store(project).get_requirement("REQ-A-1") is None
        assert get_store("other").get_requirement("REQ-B-1") is None

    def test_bulk_delete_covers_every_id_under_one_lock(self, client, project, monkeypatch):
        """C2 bulk path — the bulk loop holds the project lock once, so the
        reference created against the *second* id is refused and every id is
        still deleted."""
        store = get_store(project)
        make_req(client, project, "REQ-1")
        make_req(client, project, "REQ-2")
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": "SPEC-1", "name": "Spec", "requirements": []})

        scanned = Latch("bulk scanned")
        resumed = Latch("resume bulk")
        _pause_first_find_referrers(monkeypatch, scanned, resumed)

        results = {}

        def do_bulk_delete():
            res = client.post(f"/api/projects/{project}/requirements/bulk-delete",
                              json={"ids": ["REQ-1", "REQ-2"]})
            results["bulk"] = res.json()

        reference_done = Latch("reference creation finished")

        def do_reference():
            res = client.put(f"/api/projects/{project}/specifications/SPEC-1",
                             json={"requirements": ["REQ-2"]})
            results["reference"] = res.status_code
            reference_done.release()

        bulk_thread, bulk_errors = _run(do_bulk_delete)
        scanned.wait()

        reference_thread, reference_errors = _run(do_reference)
        _wait_quietly(reference_done)

        resumed.release()
        bulk_thread.join(timeout=30)
        reference_thread.join(timeout=30)
        assert not bulk_errors, f"bulk worker raised: {bulk_errors}"
        assert not reference_errors, f"reference worker raised: {reference_errors}"

        assert results["bulk"].get("deleted") == 2, results
        assert store.get_requirement("REQ-1") is None
        assert store.get_requirement("REQ-2") is None
        spec = store.get_item("specifications", "SPEC-1")
        assert "REQ-2" not in (spec.get("requirements") or [])


class TestC1Characterisation:
    def test_rename_sweep_loses_a_concurrent_referrer_update(self, client, project):
        """C1, rename vs update — ``rename_requirement`` plans its referrer
        sweep from a single snapshot and then applies it as individual writes,
        so an update to a not-yet-swept referrer is clobbered by the stale
        rewrite. This documents the state today and is expected to change."""
        store = get_store(project)
        make_req(client, project, "REQ-001", name="Doomed")
        make_req(client, project, "REQ-003", name="Unrelated")
        client.post(f"/api/projects/{project}/specifications",
                    json={"id": "SPEC-1", "name": "Spec"})
        client.put(f"/api/projects/{project}/specifications/SPEC-1",
                   json={"requirements": ["REQ-001"]})
        client.post(f"/api/projects/{project}/change-requests",
                    json={"id": "CR-1", "title": "CR", "description": "d",
                          "rationale": "r", "urgency": "low",
                          "affected_requirements": ["REQ-001"]})

        reached = Latch("rename mid-sweep")
        resume = Latch("resume rename")

        real_update_item = store.update_item
        state = {"paused": False}

        def pausing_update_item(collection, item_id, data):
            result = real_update_item(collection, item_id, data)
            if not state["paused"]:
                state["paused"] = True
                reached.release()
                resume.wait()
            return result

        store.update_item = pausing_update_item

        rename_thread, rename_errors = _run(
            lambda: rename_requirement(store, "REQ-001", "REQ-002", "tester"))
        reached.wait()

        # Update a not-yet-swept referrer while the rename is parked mid-sweep.
        get_store(project).update_item(
            "change_requests", "CR-1",
            {"affected_requirements": ["REQ-002", "REQ-003"]})

        resume.release()
        rename_thread.join(timeout=30)
        assert not rename_errors, f"rename worker raised: {rename_errors}"

        cr = store.get_item("change_requests", "CR-1")
        # The rename's stale sweep clobbers the concurrent addition of REQ-003.
        assert cr["affected_requirements"] == ["REQ-002"], cr

    def test_two_reparents_duplicate_a_subtree(self, client, project):
        """C1, two concurrent reparents of the same subtree — ``apply_reparent``
        deletes and recreates each node, so a second reparent of the same
        subtree while the first is parked leaves the subtree duplicated (one
        copy under each destination) with the first's trailing nodes dropped.
        This documents the state today and is expected to change."""
        store = get_store(project)
        make_req(client, project, "AAA-1", name="Destination A")
        make_req(client, project, "BBB-1", name="Destination B")
        make_req(client, project, "MOVE-1", name="Root")
        make_req(client, project, "MOVE-2", name="Child")
        store.update_requirement("MOVE-2", {"parent": "MOVE-1"})

        requirements = store.list_requirements()
        plan_a = plan_reparent(requirements, ["MOVE-1"], "AAA-1", re_prefix=True)
        plan_b = plan_reparent(requirements, ["MOVE-1"], "BBB-1", re_prefix=True)

        reached = Latch("reparent A mid-move")
        resume = Latch("resume reparent A")

        real_delete = store.delete_requirement
        state = {"paused": False}

        def pausing_delete(req_id):
            if not state["paused"]:
                state["paused"] = True
                reached.release()
                resume.wait()
            return real_delete(req_id)

        store.delete_requirement = pausing_delete

        a_thread, a_errors = _run(
            lambda: apply_reparent(store, plan_a, "tester"))
        reached.wait()

        # Run the second reparent of the same subtree to completion.
        apply_reparent(store, plan_b, "tester")

        resume.release()
        a_thread.join(timeout=30)
        assert not a_errors, f"reparent A worker raised: {a_errors}"

        fresh = get_store(project)
        ids = {r["id"] for r in fresh.list_requirements()}
        # The stale first reparent still lands its root copy …
        assert "AAA-2" in ids, ids
        assert fresh.get_requirement("AAA-2")["parent"] == "AAA-1"
        # … while the second reparent landed the whole subtree.
        assert "BBB-2" in ids and "BBB-3" in ids, ids
        # The first reparent's trailing node was skipped (its source was deleted).
        assert "AAA-3" not in ids, ids
        assert not ids & {"MOVE-1", "MOVE-2"}
