"""Bulk move re-prefix: allocation correctness and scan-count performance."""
from app.core.dependencies import get_store
from tests.conftest import make_req


def test_allocation_unchanged_with_existing_prefix(client, project):
    """The exact resulting ids must be identical to the old per-id rescan.

    Scenario: NEW prefix already has NEW-001 and NEW-002.  Two separate trees
    (SYS-A and SYS-B) are moved to NEW-001 with re_prefix.  The allocation
    must start past the highest existing NEW number (3), and the second group
    sees the first group's allocation.
    """
    store = get_store(project)
    # Parent (destination)
    make_req(client, project, "NEW-001", name="Parent")
    # Another existing requirement under the NEW prefix — blocks num 2.
    make_req(client, project, "NEW-002", name="Existing")
    # Two root-level requirements to be moved.
    make_req(client, project, "SYS-A", name="Subtree A")
    make_req(client, project, "SYS-B", name="Subtree B")

    # SYS-A has a child
    make_req(client, project, "SYS-A-1", name="Child A1")
    store.update_requirement("SYS-A-1", {"parent": "SYS-A"})
    # SYS-B has a child
    make_req(client, project, "SYS-B-1", name="Child B1")
    store.update_requirement("SYS-B-1", {"parent": "SYS-B"})

    resp = client.post(
        f"/api/projects/{project}/requirements/bulk-reparent",
        json={"ids": ["SYS-A", "SYS-B"], "parent": "NEW-001", "re_prefix": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["updated"] >= 2  # both roots renamed, plus children

    # Allocation: NEW-001 and NEW-002 exist, so first rename starts at NEW-003.
    # SYS-A  -> NEW-003
    # SYS-A-1 -> NEW-004 (continues allocation, not a separate scan)
    # SYS-B  -> NEW-005 (sees NEW-003 and NEW-004 via live_nums)
    # SYS-B-1 -> NEW-006
    expected_ids = {"NEW-003", "NEW-004", "NEW-005", "NEW-006"}
    actual_ids = set(data["ids"])
    assert actual_ids == expected_ids, f"expected {expected_ids}, got {actual_ids}"

    # Verify the store reflects the move.
    reqs = {r["id"]: r for r in store.list_requirements()}
    assert "SYS-A" not in reqs
    assert "SYS-B" not in reqs
    assert reqs["NEW-003"]["parent"] == "NEW-001"
    assert reqs["NEW-004"]["parent"] == "NEW-003"
    assert reqs["NEW-005"]["parent"] == "NEW-001"
    assert reqs["NEW-006"]["parent"] == "NEW-005"


def test_no_collision_with_used_destination_ids(client, project):
    """Moving a subtree does not collide with an id already in the destination prefix."""
    store = get_store(project)
    make_req(client, project, "NEW-001", name="Parent")
    # Pre-create NEW-003 and NEW-004 under the destination prefix so they block
    # those numbers.
    make_req(client, project, "NEW-003", name="Block three")
    make_req(client, project, "NEW-004", name="Block four")

    # Two roots to move — they should skip 3 and 4.
    make_req(client, project, "SYS-X", name="X")
    make_req(client, project, "SYS-Y", name="Y")

    resp = client.post(
        f"/api/projects/{project}/requirements/bulk-reparent",
        json={"ids": ["SYS-X", "SYS-Y"], "parent": "NEW-001", "re_prefix": True},
    )
    assert resp.status_code == 200, resp.text
    updated_ids = set(resp.json()["ids"])

    # NEW-001 exists, NEW-003 and NEW-004 block 3-4.
    # First rename picks the next available (max+1 = 5).
    assert "NEW-005" in updated_ids
    assert "NEW-006" in updated_ids

    # None of the blockers were overwritten.
    reqs = {r["id"] for r in store.list_requirements()}
    assert "NEW-001" in reqs
    assert "NEW-003" in reqs
    assert "NEW-004" in reqs


def test_relations_rewritten_from_inside_and_outside(client, project):
    """Relations pointing at renamed ids are rewritten, from both inside and
    outside the moved subtree."""
    store = get_store(project)
    make_req(client, project, "NEW-001", name="Parent")

    # Subtree root with a child, both referencing each other. Created in
    # dependency order: a relation names a target that must already exist.
    make_req(client, project, "SYS-2", name="Subtree child")
    make_req(client, project, "SYS-1", name="Subtree root",
             relations=[{"type": "refines", "target": "SYS-2"}])
    client.put(f"/api/projects/{project}/requirements/SYS-2",
               json={"relations": [{"type": "refines", "target": "SYS-1"}]})
    store.update_requirement("SYS-2", {"parent": "SYS-1"})

    # Outside requirement that references a to-be-renamed id.
    make_req(client, project, "EXT-REF", name="External reference",
             relations=[{"type": "refines", "target": "SYS-1"}])

    resp = client.post(
        f"/api/projects/{project}/requirements/bulk-reparent",
        json={"ids": ["SYS-1"], "parent": "NEW-001", "re_prefix": True},
    )
    assert resp.status_code == 200, resp.text
    updated_ids = set(resp.json()["ids"])
    assert len(updated_ids) == 2  # SYS-1 and SYS-2 both renamed

    renamed_1, renamed_2 = "NEW-002", "NEW-003"  # only NEW-001 existed before
    assert renamed_1 in updated_ids
    assert renamed_2 in updated_ids

    reqs = {r["id"]: r for r in store.list_requirements()}
    # External reference updated
    ext = reqs["EXT-REF"]
    ext_targets = {rel["target"] for rel in ext.get("relations", [])}
    assert renamed_1 in ext_targets or renamed_2 in ext_targets
    assert "SYS-1" not in ext_targets
    # Internal references updated
    for rid in (renamed_1, renamed_2):
        node_targets = {rel["target"] for rel in reqs[rid].get("relations", [])}
        assert rid not in node_targets, f"self-reference not rewritten in {rid}"
        # Should reference the other renamed id, not the old one.
        assert "SYS-1" not in node_targets
        assert "SYS-2" not in node_targets


def test_list_requirements_called_bounded_times(client, project):
    """Regardless of how many ids are moved, store.list_requirements is called
    a bounded number of times — this is the whole point of the optimization."""
    import app.core.dependencies as deps

    store = get_store(project)
    make_req(client, project, "NEW-001", name="Parent")

    # Create many root-level requirements to move.
    num_roots = 10
    for i in range(num_roots):
        rid = f"ROOT-{i:02d}"
        make_req(client, project, rid, name=f"Root {i}")

    # Save originals so we can restore them after the test — patches on
    # module-level objects leak across tests otherwise.
    _original_get_store = deps.get_store
    _original_list_reqs = store.list_requirements

    try:
        # Count calls to list_requirements on the store used during the request.
        call_count = 0

        def counted():
            nonlocal call_count
            call_count += 1
            return _original_list_reqs()

        store.list_requirements = counted
        deps.get_store = lambda pid, _store=store: _store

        resp = client.post(
            f"/api/projects/{project}/requirements/bulk-reparent",
            json={"ids": [f"ROOT-{i:02d}" for i in range(num_roots)],
                  "parent": "NEW-001", "re_prefix": True},
        )
        assert resp.status_code == 200, resp.text

        # The old code called list_requirements once per moved id (num_roots times)
        # plus the hierarchy snapshot and the external-relation rewrite pass.
        # The new code does one pre-scan, plus the snapshot and rewrite pass.
        # We expect at most a small constant (e.g. 3), never num_roots.
        assert call_count <= 3, (
            f"list_requirements called {call_count} times for {num_roots} roots — "
            f"should be bounded (≤3), not O(n)"
        )
    finally:
        store.list_requirements = _original_list_reqs
        deps.get_store = _original_get_store
