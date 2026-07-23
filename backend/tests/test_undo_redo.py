"""Tests for undo/redo functionality via the API.

The undo/redo system works by:
1. The frontend captures "before" state before a mutation
2. On undo: calls PUT with the old state and ?skip_workflow=true
3. On redo: calls PUT with the new state (normal workflow applies)
"""

from .conftest import make_req


class TestUndoRedoStatusChange:
    """The original bug: undoing a status change gave 400 because workflow
    validation rejected the reverse transition.  ?skip_workflow=true fixes that."""

    def test_undo_status_change_bypasses_workflow(self, client, project):
        req = make_req(client, project, "UNDO01", name="Status Undo Test", status="proposed")

        # Change status normally (workflow validates this).
        res = client.put(
            f"/api/projects/{project}/requirements/UNDO01",
            json={"status": "approved"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "approved"

        # Undo: reverting to "proposed" would normally fail workflow validation
        # (approved→proposed might be disallowed).  ?skip_workflow=true must allow it.
        res2 = client.put(
            f"/api/projects/{project}/requirements/UNDO01?skip_workflow=true",
            json={"status": "proposed"},
        )
        assert res2.status_code == 200, f"Undo should succeed, got {res2.status_code}: {res2.text}"
        assert res2.json()["status"] == "proposed"

    def test_skip_workflow_allows_any_transition(self, client, project):
        req = make_req(client, project, "UNDO02", name="Any Transition", status="implemented")

        # Jump from implemented all the way back to proposed — workflow would
        # normally forbid this, but skip_workflow must allow it.
        res = client.put(
            f"/api/projects/{project}/requirements/UNDO02?skip_workflow=true",
            json={"status": "proposed"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "proposed"

    def test_workflow_still_enforced_without_flag(self, client, project):
        """The ?skip_workflow flag should only be used for undo — normal
        updates must still enforce workflow rules."""
        # Install a custom workflow that makes 'rejected' terminal.
        client.patch(
            f"/api/projects/{project}",
            json={"workflow": {"transitions": {"rejected": []}}},
        )
        make_req(client, project, "UNDO03", name="Workflow Test", status="rejected")

        # Rejected is a terminal state in the custom workflow — no transitions
        # are allowed out of it.  The plain PUT must reject this.
        res = client.put(
            f"/api/projects/{project}/requirements/UNDO03",
            json={"status": "approved"},
        )
        assert res.status_code == 400
        assert "transition" in res.json()["detail"].lower() or "terminal" in res.json()["detail"].lower()


class TestUndoRedoCreateDelete:
    """Create and delete are the two other mutation families that need undo
    coverage.  Create → undo = delete, redo = re-create.  Delete → undo =
    re-create, redo = delete."""

    def test_undo_create_is_delete(self, client, project):
        created = make_req(client, project, "UNDO10", name="Undo Create")

        # Undo the create: delete the requirement.
        res = client.delete(f"/api/projects/{project}/requirements/UNDO10")
        assert res.status_code == 200
        assert res.json() == {"ok": True}

        # Verify it's gone.
        assert client.get(f"/api/projects/{project}/requirements/UNDO10").status_code == 404

    def test_redo_create_is_recreate(self, client, project):
        created = make_req(client, project, "UNDO11", name="Redo Create Test")
        client.delete(f"/api/projects/{project}/requirements/UNDO11")

        # Redo: re-create with the same data.
        res = client.post(
            f"/api/projects/{project}/requirements",
            json={"id": "UNDO11", "name": "Redo Create Test", "status": "proposed"},
        )
        assert res.status_code == 201
        assert res.json()["id"] == "UNDO11"
        assert res.json()["name"] == "Redo Create Test"

    def test_undo_delete_is_recreate(self, client, project):
        original = make_req(client, project, "UNDO12", name="Undo Delete", priority="high")

        # Simulate delete.
        client.delete(f"/api/projects/{project}/requirements/UNDO12")

        # Undo delete: re-create with the saved data.
        res = client.post(
            f"/api/projects/{project}/requirements",
            json={"id": "UNDO12", "name": "Undo Delete", "priority": "high"},
        )
        assert res.status_code == 201
        assert res.json()["id"] == "UNDO12"
        assert res.json()["priority"] == "high"

    def test_redo_delete_is_delete_again(self, client, project):
        make_req(client, project, "UNDO13", name="Redo Delete")

        res = client.delete(f"/api/projects/{project}/requirements/UNDO13")
        assert res.status_code == 200
        assert res.json() == {"ok": True}

        # Verify it's gone (redo of create-undo executes the delete again).
        assert client.get(f"/api/projects/{project}/requirements/UNDO13").status_code == 404


class TestUndoRedoFieldChanges:
    """Partial field updates — every editable field should round-trip through
    undo and redo correctly."""

    def test_undo_restores_previous_field_values(self, client, project):
        req = make_req(
            client, project, "UNDO20",
            name="Original", priority="low", rationale="old rationale",
            source="old source", allocated_to="old component",
            verification_method="test", verification_status="pending",
        )

        # Mutate several fields.
        res = client.put(
            f"/api/projects/{project}/requirements/UNDO20",
            json={
                "name": "Changed",
                "priority": "critical",
                "rationale": "new rationale",
                "source": "new source",
                "allocated_to": "new component",
                "verification_method": "inspection",
                "verification_status": "passed",
            },
        )
        assert res.status_code == 200
        updated = res.json()
        assert updated["name"] == "Changed"
        assert updated["priority"] == "critical"

        # Undo each field individually (simulating what the undo stack does).
        undo_res = client.put(
            f"/api/projects/{project}/requirements/UNDO20?skip_workflow=true",
            json={
                "name": "Original",
                "priority": "low",
                "rationale": "old rationale",
                "source": "old source",
                "allocated_to": "old component",
                "verification_method": "test",
                "verification_status": "pending",
            },
        )
        assert undo_res.status_code == 200
        restored = undo_res.json()
        assert restored["name"] == "Original"
        assert restored["priority"] == "low"
        assert restored["rationale"] == "old rationale"
        assert restored["source"] == "old source"
        assert restored["allocated_to"] == "old component"
        assert restored["verification_method"] == "test"
        assert restored["verification_status"] == "pending"

    def test_redo_reapplies_field_changes(self, client, project):
        make_req(client, project, "UNDO21", name="Redo Fields")

        # Change a field.
        client.put(
            f"/api/projects/{project}/requirements/UNDO21",
            json={"name": "After Change"},
        )

        # Undo it.
        client.put(
            f"/api/projects/{project}/requirements/UNDO21?skip_workflow=true",
            json={"name": "Redo Fields"},
        )

        # Redo: reapply the change.
        res = client.put(
            f"/api/projects/{project}/requirements/UNDO21",
            json={"name": "After Change"},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "After Change"

    def test_multiple_sequential_undo_redo(self, client, project):
        """Simulate a multi-step undo/redo session:
        1. Change name
        2. Change priority
        3. Undo priority (restore old)
        4. Undo name (restore old)
        5. Redo name (reapply)
        6. Redo priority (reapply)
        """
        make_req(client, project, "UNDO22", name="Seq", priority="low")

        # Step 1 & 2
        client.put(f"/api/projects/{project}/requirements/UNDO22", json={"name": "Seq1"})
        client.put(f"/api/projects/{project}/requirements/UNDO22", json={"priority": "high"})

        r = client.get(f"/api/projects/{project}/requirements/UNDO22").json()
        assert r["name"] == "Seq1"
        assert r["priority"] == "high"

        # Step 3: undo priority
        client.put(f"/api/projects/{project}/requirements/UNDO22?skip_workflow=true", json={"priority": "low"})
        r = client.get(f"/api/projects/{project}/requirements/UNDO22").json()
        assert r["priority"] == "low"

        # Step 4: undo name
        client.put(f"/api/projects/{project}/requirements/UNDO22?skip_workflow=true", json={"name": "Seq"})
        r = client.get(f"/api/projects/{project}/requirements/UNDO22").json()
        assert r["name"] == "Seq"

        # Step 5: redo name
        client.put(f"/api/projects/{project}/requirements/UNDO22", json={"name": "Seq1"})
        r = client.get(f"/api/projects/{project}/requirements/UNDO22").json()
        assert r["name"] == "Seq1"

        # Step 6: redo priority
        client.put(f"/api/projects/{project}/requirements/UNDO22", json={"priority": "high"})
        r = client.get(f"/api/projects/{project}/requirements/UNDO22").json()
        assert r["priority"] == "high"


class TestUndoRedoWithRelations:
    """When a requirement has relations, the undo/redo should preserve them."""

    def test_undo_delete_restores_relations(self, client, project):
        parent = make_req(client, project, "UNDO30", name="Parent")
        child = make_req(client, project, "UNDO31", name="Child")

        # Add a relation from child to parent.
        client.put(
            f"/api/projects/{project}/requirements/UNDO31",
            json={"relations": [{"type": "refines", "target": "UNDO30"}]},
        )

        # Delete child — the undo should re-create it with its relation.
        snap = client.get(f"/api/projects/{project}/requirements/UNDO31").json()
        client.delete(f"/api/projects/{project}/requirements/UNDO31")

        # Undo: re-create with relations.
        data = {k: v for k, v in snap.items() if k in ("id", "name", "type", "priority", "status", "relations")}
        res = client.post(f"/api/projects/{project}/requirements", json=data)
        assert res.status_code == 201
        restored = res.json()
        assert len(restored["relations"]) == 1
        assert restored["relations"][0]["type"] == "refines"
        assert restored["relations"][0]["target"] == "UNDO30"


class TestUndoDeleteWithFullSnapshot:
    """Regression: the frontend undo command passes the full GET response back
    to POST /requirements.  Pydantic v2 must ignore extra fields (created,
    modified, verification_status) — this class validates that."""

    def test_full_get_snapshot_roundtrips(self, client, project):
        """Take the full GET response of a requirement, delete it, then
        POST it back as-is — must succeed (extra fields ignored)."""
        created = make_req(
            client, project, "FULL01",
            name="Full Snapshot", priority="critical", status="approved",
            rationale="because", source="src", allocated_to="alloc",
        )
        # Get the full representation as the frontend sees it.
        snap = client.get(f"/api/projects/{project}/requirements/FULL01").json()
        assert snap["created"]
        assert snap["modified"]
        assert snap["verification_status"] == "pending"

        # Delete it.
        client.delete(f"/api/projects/{project}/requirements/FULL01")
        assert client.get(f"/api/projects/{project}/requirements/FULL01").status_code == 404

        # Undo: POST the full snapshot (including created/modified/verification_status).
        res = client.post(f"/api/projects/{project}/requirements", json=snap)
        assert res.status_code == 201, f"Undo with full snapshot should succeed, got {res.status_code}: {res.text}"
        restored = res.json()
        assert restored["id"] == "FULL01"
        assert restored["name"] == "Full Snapshot"
        assert restored["priority"] == "critical"
        assert restored["status"] == "approved"
        assert restored["rationale"] == "because"
