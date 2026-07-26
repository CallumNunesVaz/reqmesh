"""BUG-4 — locking and lost updates.

The repo had no concurrency test at all, which is why these went unnoticed:

* ``load_users() → mutate → save_users()`` was unlocked, so two admins creating
  accounts each wrote back their own snapshot (one account silently never
  existed), and a login racing ``delete_user`` wrote the whole dict back
  *including the deleted entry* — resurrecting the account.
* Only ``update_item`` took the store's file lock; create/delete/write and the
  trace matrix did not.
* ``PUT /traces`` replaced the whole document from a client-side snapshot with
  no version check, so a stale tab erased everything added since it loaded.
* The cascade wrote each child's whole pre-request snapshot back, clobbering
  concurrent edits, and only ever went one level deep.
"""
import threading

import pytest

from app.core import auth
from app.core.dependencies import get_store
from tests.conftest import make_req


def _run_concurrently(fns):
    """Run callables on real threads and surface any exception."""
    errors = []

    def wrap(f):
        try:
            f()
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(f,)) for f in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, f"worker raised: {errors}"


class TestUserStoreLocking:
    def test_concurrent_account_creation_loses_nobody(self, workspace):
        auth.load_users()  # materialise the file (and the default admin) first
        names = [f"user{i}" for i in range(12)]
        _run_concurrently([
            (lambda n=n: auth.register_user(n, "Password123!", "contributor"))
            for n in names
        ])
        users = auth.load_users()
        missing = [n for n in names if n not in users]
        assert not missing, f"lost {len(missing)} accounts: {missing}"

    def test_login_cannot_resurrect_a_deleted_account(self, workspace):
        """A login writes the whole user dict back; racing a delete used to
        restore the deleted entry with a token already issued."""
        auth.register_user("victim", "Password123!", "contributor")

        results = {}

        def login():
            results["login"] = auth.authenticate("victim", "Password123!")

        def delete():
            auth.delete_user("victim")

        for _ in range(15):
            auth.register_user("victim", "Password123!", "contributor")
            _run_concurrently([login, delete])
            assert "victim" not in auth.load_users(), "deleted account was resurrected"

    def test_concurrent_failed_logins_do_not_lose_a_role_change(self, workspace):
        auth.register_user("bob", "Password123!", "contributor")

        def hammer():
            for _ in range(5):
                auth.authenticate("bob", "wrong-password")

        def promote():
            auth.set_user_role("bob", "maintainer")

        _run_concurrently([hammer, promote, hammer])
        assert auth.load_users()["bob"]["role"] == "maintainer"


class TestStoreWriteLocking:
    def test_concurrent_creates_all_land(self, client, project):
        store = get_store(project)
        ids = [f"REQ-{i:03d}" for i in range(20)]
        _run_concurrently([
            (lambda i=i: store.create_requirement({"id": i, "name": i}))
            for i in ids
        ])
        stored = {r["id"] for r in store.list_requirements()}
        assert set(ids) <= stored, f"lost {set(ids) - stored}"

    def test_concurrent_updates_to_one_item_do_not_lose_fields(self, client, project):
        """Each writer patches a different field; all must survive."""
        make_req(client, project, "REQ-001")
        store = get_store(project)
        fields = ["rationale", "source", "allocated_to"]
        _run_concurrently([
            (lambda f=f: [store.update_requirement("REQ-001", {f: f"set-{f}"})
                          for _ in range(5)])
            for f in fields
        ])
        final = store.get_requirement("REQ-001")
        for f in fields:
            assert final.get(f) == f"set-{f}", f"{f} was lost"


class TestTraceMatrixConcurrency:
    def _links(self, n):
        return {"links": [{"source": f"R{i}", "target": f"V{i}", "type": "verifies"}
                          for i in range(n)]}

    def test_stale_write_is_refused_with_if_match(self, client, project):
        res = client.get(f"/api/projects/{project}/traces")
        etag = res.headers.get("ETag")
        assert etag, "GET /traces should expose an ETag"

        # Somebody else saves first.
        assert client.put(f"/api/projects/{project}/traces",
                          json=self._links(3)).status_code == 200

        # Our stale snapshot must not silently erase theirs.
        stale = client.put(f"/api/projects/{project}/traces", json=self._links(1),
                           headers={"If-Match": etag})
        assert stale.status_code == 409, stale.text
        assert len(client.get(f"/api/projects/{project}/traces").json()["links"]) == 3

    def test_current_version_is_accepted(self, client, project):
        client.put(f"/api/projects/{project}/traces", json=self._links(2))
        etag = client.get(f"/api/projects/{project}/traces").headers["ETag"]
        res = client.put(f"/api/projects/{project}/traces", json=self._links(5),
                         headers={"If-Match": etag})
        assert res.status_code == 200, res.text
        assert len(client.get(f"/api/projects/{project}/traces").json()["links"]) == 5

    def test_without_if_match_the_old_behaviour_is_kept(self, client, project):
        """Existing clients that don't send the header must keep working."""
        assert client.put(f"/api/projects/{project}/traces",
                          json=self._links(2)).status_code == 200


class TestCascade:
    def _child(self, client, project, cid, parent):
        make_req(client, project, cid)
        get_store(project).update_requirement(cid, {"cascade_from": parent})

    def test_cascade_sends_only_changed_fields(self, client, project):
        """A concurrent edit to an unrelated field on the child must survive."""
        make_req(client, project, "PARENT", name="Parent")
        self._child(client, project, "CHILD", "PARENT")
        store = get_store(project)
        store.update_requirement("CHILD", {"rationale": "child's own rationale"})

        res = client.put(f"/api/projects/{project}/requirements/PARENT",
                         json={"name": "Renamed parent"})
        assert res.status_code == 200, res.text

        child = store.get_requirement("CHILD")
        assert child["name"] == "Renamed parent", "cascade did not apply"
        assert child["rationale"] == "child's own rationale", \
            "cascade clobbered a field it was not propagating"

    def test_cascade_reaches_grandchildren(self, client, project):
        make_req(client, project, "PARENT", name="Parent")
        self._child(client, project, "CHILD", "PARENT")
        self._child(client, project, "GRAND", "CHILD")

        client.put(f"/api/projects/{project}/requirements/PARENT",
                   json={"name": "Renamed"})

        store = get_store(project)
        assert store.get_requirement("CHILD")["name"] == "Renamed"
        assert store.get_requirement("GRAND")["name"] == "Renamed", \
            "cascade stopped at one level"

    def test_cascade_cycle_terminates(self, client, project):
        """A cascade_from loop must not hang or recurse forever."""
        make_req(client, project, "A", name="A")
        make_req(client, project, "B", name="B")
        store = get_store(project)
        store.update_requirement("A", {"cascade_from": "B"})
        store.update_requirement("B", {"cascade_from": "A"})

        res = client.put(f"/api/projects/{project}/requirements/A",
                         json={"name": "Loop"})
        assert res.status_code in (200, 404), res.text
