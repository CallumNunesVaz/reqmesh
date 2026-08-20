"""``GET /projects/{id}`` gates the ``git`` block on the per-project permission level.

The git block can hold a credentialed remote URL, so it is only shown to callers
at the ``edit`` tier *for this project* — not merely to anyone whose global role
is ``maintainer``. A maintainer demoted to ``view`` on one project must get that
project's payload without the ``git`` key, exactly as ``require_maintain`` would
refuse them the settings page.

These tests exercise the real auth path (no dependency overrides), because
``get_project`` resolves the caller itself rather than through a ``require_*``
dependency.
"""
from app.core import auth
from app.core.dependencies import get_store


def _tok(username: str, role: str) -> dict:
    auth.register_user(username, "Password123!", role)
    return {"Authorization": f"Bearer {auth.create_token(username, role)}"}


def _make_project(client, project_id="p", git=None, permissions=None) -> str:
    admin = _tok("adm", "admin")
    r = client.post("/api/projects", json={"id": project_id, "name": "P"}, headers=admin)
    assert r.status_code == 201, r.text
    if git is not None or permissions is not None:
        store = get_store(project_id)
        meta = store.read_meta()
        if git is not None:
            meta["git"] = git
        if permissions is not None:
            meta["permissions"] = permissions
        store.write_meta(meta)
    return project_id


def _get(client, project_id, headers):
    return client.get(f"/api/projects/{project_id}", headers=headers)


def test_admin_gets_git(guest_client):
    _make_project(guest_client, git={"autocommit": True})
    body = _get(guest_client, "p", _tok("adm", "admin")).json()
    assert body["git"] == {"autocommit": True}


def test_maintainer_without_override_gets_git(guest_client):
    _make_project(guest_client, git={"autocommit": True})
    body = _get(guest_client, "p", _tok("maint", "maintainer")).json()
    assert body["git"] == {"autocommit": True}


def test_maintainer_demoted_to_view_loses_git_but_keeps_the_rest(guest_client):
    _make_project(
        guest_client,
        git={"autocommit": True},
        permissions={"guest": "view", "contributor": "propose",
                     "maintainer": "view", "admin": "admin"},
    )
    body = _get(guest_client, "p", _tok("maint", "maintainer")).json()
    assert "git" not in body
    # The rest of the project payload is unchanged.
    assert body["id"] == "p"
    assert body["name"] == "P"
    assert "naming" in body
    assert "workflow" in body


def test_contributor_does_not_get_git(guest_client):
    _make_project(guest_client, git={"autocommit": True})
    body = _get(guest_client, "p", _tok("cont", "contributor")).json()
    assert "git" not in body
