"""The staleness guard is only as good as the field that feeds it.

`services/change_requests.py` refuses to execute a request whose target moved
since it was raised — but only when `base_fingerprints` holds a fingerprint for
that target. Every other test in this suite builds the change request by calling
`store.create_item` directly, which bypasses `ChangeRequestCreate`; that is why
the model omitting `base_fingerprints` went unnoticed. The field was dropped on
every request created through the API, so the dict was always empty and the
guard never fired.

These tests go through the HTTP route, which is the only path a real client uses.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.change_requests import redline
from app.services.fingerprint import compute_fingerprint
from app.services.yaml_store import YamlStore


def _store(project_id: str) -> YamlStore:
    return YamlStore(Path(settings.data_root) / project_id)


def _create_req(store, req_id: str) -> str:
    store.create_requirement({"id": req_id, "name": "Original", "description": "d"})
    return compute_fingerprint(store.get_requirement(req_id))


def test_create_preserves_base_fingerprints(client, project):
    """A fingerprint sent to POST /change-requests survives into the stored CR."""
    store = _store(project)
    fp = _create_req(store, "SYST-F1")

    resp = client.post(f"/api/projects/{project}/change-requests", json={
        "id": "CR-FP-1",
        "title": "Rename",
        "affected_requirements": ["SYST-F1"],
        "changes": {"SYST-F1": {"name": "New Name"}},
        "base_fingerprints": {"SYST-F1": fp},
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["base_fingerprints"] == {"SYST-F1": fp}

    stored = store.get_item("change_requests", "CR-FP-1")
    assert stored["base_fingerprints"] == {"SYST-F1": fp}


def test_guard_blocks_when_target_moved_after_creation(client, project):
    """The end-to-end guard: raise a CR, edit the target, redline blocks it."""
    store = _store(project)
    fp = _create_req(store, "SYST-F2")

    resp = client.post(f"/api/projects/{project}/change-requests", json={
        "id": "CR-FP-2",
        "title": "Rename",
        "affected_requirements": ["SYST-F2"],
        "changes": {"SYST-F2": {"name": "Proposed"}},
        "base_fingerprints": {"SYST-F2": fp},
    })
    assert resp.status_code == 201, resp.text

    # Not stale yet — nobody has touched the target.
    cr = store.get_item("change_requests", "CR-FP-2")
    assert redline(store, cr)["blocked"] is False

    # Someone else edits the target after the request was raised.
    store.update_requirement("SYST-F2", {"description": "edited by someone else"})

    cr = store.get_item("change_requests", "CR-FP-2")
    result = redline(store, cr)
    assert result["blocked"] is True, (
        "executing this request would overwrite an edit made after it was raised"
    )
    assert result["targets"][0]["stale"] is True
