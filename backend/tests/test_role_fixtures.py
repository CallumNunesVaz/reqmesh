"""The role fixtures must enforce real permission tiers.

As first written, `contributor_client` overrode `require_admin` along with
every other guard, so a "contributor" satisfied every check. A test asserting
"a contributor cannot do X" would have passed regardless of the guards — the
fixture would have certified the permission model without exercising it.

Note these deliberately never use the `client` fixture: it installs *global*
dependency overrides on the shared app object, which would authorise every
other client in the same test as an admin. Setup goes through a real admin
token instead.
"""

import pytest


@pytest.fixture()
def admin_client(_real_role_client):
    with _real_role_client("admin", "setup_admin") as c:
        yield c


@pytest.fixture()
def project(admin_client):
    r = admin_client.post("/api/projects", json={"id": "rp", "name": "RP"})
    assert r.status_code == 201, r.text
    return "rp"


def test_maintainer_can_edit_requirements(project, maintainer_client):
    r = maintainer_client.post(f"/api/projects/{project}/requirements",
                               json={"id": "R1", "name": "x"})
    assert r.status_code == 201, r.text


def test_contributor_cannot_edit_requirements(project, contributor_client):
    r = contributor_client.post(f"/api/projects/{project}/requirements",
                                json={"id": "R2", "name": "x"})
    assert r.status_code == 403, f"contributor reached the edit tier: {r.status_code}"


def test_contributor_can_propose_a_change_request(project, contributor_client):
    r = contributor_client.post(f"/api/projects/{project}/change-requests",
                                json={"id": "CR1", "title": "x"})
    assert r.status_code == 201, r.text


def test_maintainer_is_not_an_admin(maintainer_client):
    r = maintainer_client.get("/api/system/settings")
    assert r.status_code == 403, f"maintainer passed require_admin: {r.status_code}"


def test_contributor_cannot_create_a_project(contributor_client):
    r = contributor_client.post("/api/projects", json={"id": "nope", "name": "N"})
    assert r.status_code == 403


def test_contributor_cannot_dry_run_an_import(project, contributor_client):
    """A preview still reads the whole project and is one checkbox away from a
    real import — it is not a read-only escape hatch around require_maintain."""
    import io

    csv_bytes = (
        '"id","type","name","description"\n'
        '"R3","functional","x","d"'
    ).encode("utf-8")
    r = contributor_client.post(
        f"/api/projects/{project}/import",
        data={"format": "csv", "mode": "merge", "dry_run": "true"},
        files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 403, f"contributor previewed an import: {r.status_code}"


def test_contributor_cannot_rename_a_requirement(project, maintainer_client, contributor_client):
    """Renaming rewrites ids project-wide, so it sits at the maintainer tier."""
    maintainer_client.post(f"/api/projects/{project}/requirements",
                           json={"id": "R9", "name": "x"})

    r = contributor_client.post(f"/api/projects/{project}/requirements/R9/rename",
                                json={"new_id": "R10"})
    assert r.status_code == 403, f"contributor renamed a requirement: {r.status_code}"


def test_viewer_cannot_restore_requirement(project, maintainer_client, guest_client):
    """A viewer (guest) gets 403 on the restore endpoint."""
    maintainer_client.post(f"/api/projects/{project}/requirements",
                           json={"id": "R-VIEW", "name": "x"})
    maintainer_client.put(f"/api/projects/{project}/requirements/R-VIEW",
                          json={"name": "y"})
    history = maintainer_client.get(f"/api/projects/{project}/history/R-VIEW").json()
    entry_id = history[0]["id"]

    r = guest_client.post(
        f"/api/projects/{project}/requirements/R-VIEW/history/{entry_id}/restore")
    assert r.status_code == 403, f"viewer restored a requirement: {r.status_code}"


def test_contributor_cannot_restore_requirement(project, maintainer_client, contributor_client):
    """A contributor gets 403 on the restore endpoint."""
    maintainer_client.post(f"/api/projects/{project}/requirements",
                           json={"id": "R-CONT", "name": "x"})
    maintainer_client.put(f"/api/projects/{project}/requirements/R-CONT",
                          json={"name": "y"})
    history = maintainer_client.get(f"/api/projects/{project}/history/R-CONT").json()
    entry_id = history[0]["id"]

    r = contributor_client.post(
        f"/api/projects/{project}/requirements/R-CONT/history/{entry_id}/restore")
    assert r.status_code == 403, f"contributor restored a requirement: {r.status_code}"
