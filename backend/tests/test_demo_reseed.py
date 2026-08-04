"""Re-seeding the bundled example from system settings.

Re-seeding is a delete followed by a write: it removes the project directory
outright, git history included. These tests are mostly about the guard rather
than the seeding, which `test_demo_seed.py` already covers.
"""

import pytest

from app.services.demo_seed import PROJECT_ID


@pytest.fixture()
def seeded(client):
    """The bundled example, present. The suite's `project` fixture makes a
    different project, so the example is absent unless a test asks for it —
    which also exercises the create-when-absent path."""
    res = client.post("/api/system/demo-project/reseed", json={})
    assert res.status_code == 200, res.text
    assert res.json()["replaced"] is False
    return PROJECT_ID


def test_status_reports_absence_before_anything_is_seeded(client):
    body = client.get("/api/system/demo-project").json()
    assert body["exists"] is False
    assert body["requirements"] == 0


def test_status_reports_what_a_reseed_would_replace(client, seeded):
    res = client.get("/api/system/demo-project")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["exists"] is True
    assert body["id"] == PROJECT_ID
    # A count, not a bare boolean: "this replaces 57 requirements" is a warning
    # someone can act on.
    assert body["requirements"] > 0


def test_reseed_without_force_is_refused_and_changes_nothing(client, seeded):
    before = client.get(f"/api/projects/{PROJECT_ID}/requirements").json()
    res = client.post("/api/system/demo-project/reseed", json={})
    assert res.status_code == 409, res.text
    assert "force" in res.json()["detail"].lower()

    after = client.get(f"/api/projects/{PROJECT_ID}/requirements").json()
    assert after == before


def test_reseed_with_force_replaces_the_project(client, seeded):
    # Change something, then prove the re-seed undid it.
    rid = client.get(f"/api/projects/{PROJECT_ID}/requirements").json()["items"][0]["id"]
    patched = client.put(f"/api/projects/{PROJECT_ID}/requirements/{rid}",
                         json={"name": "Edited before the re-seed"})
    assert patched.status_code == 200, patched.text
    assert client.get(f"/api/projects/{PROJECT_ID}/requirements/{rid}").json()["name"] \
        == "Edited before the re-seed"

    res = client.post("/api/system/demo-project/reseed", json={"force": True})
    assert res.status_code == 200, res.text
    assert res.json()["replaced"] is True

    restored = client.get(f"/api/projects/{PROJECT_ID}/requirements/{rid}").json()
    assert restored["name"] != "Edited before the re-seed"


def test_reseed_leaves_other_projects_alone(client, seeded):
    client.post("/api/projects", json={"id": "keep-me", "name": "Keep Me"})
    client.post("/api/system/demo-project/reseed", json={"force": True})
    assert client.get("/api/projects/keep-me").status_code == 200


def test_both_routes_require_admin(guest_client):
    assert guest_client.get("/api/system/demo-project").status_code in (401, 403)
    assert guest_client.post("/api/system/demo-project/reseed",
                             json={"force": True}).status_code in (401, 403)
