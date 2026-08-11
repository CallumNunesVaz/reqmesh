"""Tests for POST /projects/{id}/requirements/{req_id}/history/{entry_id}/restore."""

from tests.conftest import make_req


def _latest_entry(history):
    """Newest entry (index 0 after reverse-chronological sort)."""
    return history[0]


def _entry_id(history, index=0):
    return history[index]["id"]


def test_restore_reverts_only_the_target_changes_fields(client, project):
    """Editing a requirement twice and restoring the first change puts back only
    that change's fields, leaving the second change's fields alone."""
    make_req(client, project, "R-A", name="Original", status="proposed", priority="low")

    # First edit: change name and status.
    client.put(f"/api/projects/{project}/requirements/R-A",
               json={"name": "Renamed", "status": "approved"})

    # Second edit: change priority only.
    client.put(f"/api/projects/{project}/requirements/R-A",
               json={"priority": "high"})

    # History should have three entries: update (priority), update (name+status), create.
    history = client.get(f"/api/projects/{project}/history/R-A").json()
    assert len(history) == 3

    # The first (newest) entry is the priority-only update.
    # The second entry is the name+status update.
    first_change_entry = history[1]
    assert first_change_entry["action"] == "update"
    assert "name" in first_change_entry["changes"]
    assert "status" in first_change_entry["changes"]
    assert first_change_entry["changes"]["name"]["before"] == "Original"
    assert first_change_entry["changes"]["name"]["after"] == "Renamed"

    # Restore the first change.
    res = client.post(
        f"/api/projects/{project}/requirements/R-A/history/{first_change_entry['id']}/restore")
    assert res.status_code == 200, res.text
    req = res.json()
    # Name and status go back to their before values.
    assert req["name"] == "Original"
    assert req["status"] == "proposed"
    # Priority from the second edit survives.
    assert req["priority"] == "high"


def test_restore_appends_update_entry(client, project):
    """The restore records an 'update' entry attributed to the caller."""
    make_req(client, project, "R-B", name="Before", priority="medium")

    client.put(f"/api/projects/{project}/requirements/R-B",
               json={"name": "After"})

    history = client.get(f"/api/projects/{project}/history/R-B").json()
    entry = history[0]
    assert entry["action"] == "update"

    res = client.post(
        f"/api/projects/{project}/requirements/R-B/history/{entry['id']}/restore")
    assert res.status_code == 200

    # New history should be 3 entries: restore update, original update, create.
    updated_history = client.get(f"/api/projects/{project}/history/R-B").json()
    assert len(updated_history) == 3
    newest = updated_history[0]
    assert newest["action"] == "update"
    assert newest["user"] == "tester"
    assert "name" in newest["changes"]
    assert newest["changes"]["name"]["before"] == "After"
    assert newest["changes"]["name"]["after"] == "Before"


def test_restoring_same_entry_twice_is_safe(client, project):
    """Restoring the same entry twice: the second is a no-op, not an error."""
    make_req(client, project, "R-C", name="Original")

    client.put(f"/api/projects/{project}/requirements/R-C",
               json={"name": "Changed"})

    history = client.get(f"/api/projects/{project}/history/R-C").json()
    entry = history[0]

    # First restore.
    r1 = client.post(
        f"/api/projects/{project}/requirements/R-C/history/{entry['id']}/restore")
    assert r1.status_code == 200
    assert r1.json()["name"] == "Original"

    # Second restore of the same entry — no-op, still fine.
    r2 = client.post(
        f"/api/projects/{project}/requirements/R-C/history/{entry['id']}/restore")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Original"


def test_create_entry_returns_409(client, project):
    """Restoring a 'create' entry is refused with 409."""
    make_req(client, project, "R-D", name="Something")

    history = client.get(f"/api/projects/{project}/history/R-D").json()
    create_entry = history[-1]  # oldest is the create
    assert create_entry["action"] == "create"

    res = client.post(
        f"/api/projects/{project}/requirements/R-D/history/{create_entry['id']}/restore")
    assert res.status_code == 409
    assert "create" in res.json()["detail"].lower()


def test_delete_entry_returns_409(client, project):
    """Restoring a 'delete' entry is refused with 409."""
    make_req(client, project, "R-E", name="Will Be Deleted")

    client.delete(f"/api/projects/{project}/requirements/R-E")

    # The delete was recorded under R-E's history, which still exists.
    history = client.get(f"/api/projects/{project}/history/R-E").json()
    delete_entry = history[0]
    assert delete_entry["action"] == "delete"

    res = client.post(
        f"/api/projects/{project}/requirements/R-E/history/{delete_entry['id']}/restore")
    assert res.status_code == 409
    assert "delete" in res.json()["detail"].lower()


def test_unknown_entry_id_is_404(client, project):
    """An entry id that does not exist returns 404."""
    make_req(client, project, "R-F", name="x")

    res = client.post(
        f"/api/projects/{project}/requirements/R-F/history/20200101T000000000000/restore")
    assert res.status_code == 404


def test_entry_belonging_to_another_requirement_is_404(client, project):
    """An entry id from another requirement is not found in this one's history
    and returns 404."""
    make_req(client, project, "R-G", name="G")
    make_req(client, project, "R-H", name="H")

    client.put(f"/api/projects/{project}/requirements/R-G",
               json={"name": "G Prime"})

    g_history = client.get(f"/api/projects/{project}/history/R-G").json()
    g_entry_id = g_history[0]["id"]

    # Use R-G's entry id on R-H's restore endpoint.
    res = client.post(
        f"/api/projects/{project}/requirements/R-H/history/{g_entry_id}/restore")
    assert res.status_code == 404


def test_unsafe_entry_id_is_rejected(client, project):
    """An entry_id with path traversal characters is rejected."""
    make_req(client, project, "R-I", name="Safe")

    res = client.post(
        f"/api/projects/{project}/requirements/R-I/history/entry..etc/restore")
    assert res.status_code == 400


def test_unsafe_req_id_is_rejected(client, project):
    """A req_id with path traversal characters is rejected."""
    res = client.post(
        f"/api/projects/{project}/requirements/req..unsafe/history/20200101T000000000000/restore")
    assert res.status_code == 400


def test_restore_rejects_a_value_the_model_will_not_take(client, project):
    """History files are hand-editable and arrive by git pull, so a recorded
    `before` is not trusted input. Without validation the restore wrote it
    straight through, putting a status no enum allows into the requirement."""
    from pathlib import Path

    from app.core.config import settings
    from app.services.yaml_store import YamlStore

    make_req(client, project, "R-BAD", name="Original", status="proposed")
    client.put(f"/api/projects/{project}/requirements/R-BAD", json={"status": "approved"})

    store = YamlStore(Path(settings.data_root) / project)
    entry = [h for h in store.list_history("R-BAD") if h.get("action") == "update"][0]

    # Corrupt the recorded before-value, as a hand edit or a bad merge would.
    path = store.history_dir("R-BAD") / f"{entry['id']}.yaml"
    raw = store._read_yaml(path)
    raw["changes"]["status"]["before"] = "not-a-status"
    store._write_yaml(path, raw)

    res = client.post(
        f"/api/projects/{project}/requirements/R-BAD/history/{entry['id']}/restore")
    assert res.status_code == 400, res.text

    # And the requirement is untouched.
    assert client.get(f"/api/projects/{project}/requirements/R-BAD").json()["status"] == "approved"


def test_restoring_a_field_that_did_not_exist_clears_it_to_the_model_default(client, project):
    """A field genuinely absent before the change records `before: None`.
    Writing that back verbatim leaves `rationale: null` where every reader
    expects a string, so the model's own empty value is restored instead.

    The requirement is written through the store rather than the API because
    the API fills every field's default on create, which is exactly what stops
    a `None` before-value from arising.
    """
    from pathlib import Path

    from app.core.config import settings
    from app.services.yaml_store import YamlStore

    store = YamlStore(Path(settings.data_root) / project)
    store.create_requirement({"id": "R-SPARSE", "name": "Sparse"})  # no rationale key at all

    res = client.put(f"/api/projects/{project}/requirements/R-SPARSE",
                     json={"rationale": "Because"})
    assert res.status_code == 200, res.text

    entry = [h for h in store.list_history("R-SPARSE") if h.get("action") == "update"][0]
    assert entry["changes"]["rationale"]["before"] is None, "expected a genuinely absent field"

    res = client.post(
        f"/api/projects/{project}/requirements/R-SPARSE/history/{entry['id']}/restore")
    assert res.status_code == 200, res.text
    assert res.json()["rationale"] == ""
