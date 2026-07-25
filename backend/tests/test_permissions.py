"""Per-project permission enforcement.

Unlike most tests, these exercise the *real* auth guards (the ``guest_client``
fixture installs no dependency overrides), driving them with genuine bearer
tokens so we can verify the propose/edit tiers and the per-project permissions
map actually gate requests.
"""
from app.core import auth
from app.core.dependencies import get_store


def _tok(username: str, role: str) -> dict:
    auth.register_user(username, "Password123!", role)
    return {"Authorization": f"Bearer {auth.create_token(username, role)}"}


def _make_project(client) -> None:
    r = client.post("/api/projects", json={"id": "p", "name": "P"},
                    headers=_tok("adm", "admin"))
    assert r.status_code == 201, r.text


def _new_cr(client, headers, cr_id="CR-1"):
    return client.post("/api/projects/p/change-requests",
                       json={"id": cr_id, "title": "x"}, headers=headers)


def _new_req(client, headers, req_id="R-1"):
    return client.post("/api/projects/p/requirements",
                       json={"id": req_id, "name": "x"}, headers=headers)


class TestDefaultTiers:
    def test_contributor_can_propose_but_not_edit(self, guest_client):
        _make_project(guest_client)
        cont = _tok("cont", "contributor")
        assert _new_cr(guest_client, cont).status_code == 201       # propose tier
        assert _new_req(guest_client, cont).status_code == 403      # edit tier

    def test_maintainer_can_edit(self, guest_client):
        _make_project(guest_client)
        maint = _tok("maint", "maintainer")
        assert _new_cr(guest_client, maint).status_code == 201
        assert _new_req(guest_client, maint).status_code == 201

    def test_guest_cannot_propose(self, guest_client):
        _make_project(guest_client)
        assert _new_cr(guest_client, {}).status_code == 403

    def test_contributor_cannot_create_project(self, guest_client):
        # Project creation is maintainer-tier and global (no project to scope to).
        r = guest_client.post("/api/projects", json={"id": "q", "name": "Q"},
                              headers=_tok("cont", "contributor"))
        assert r.status_code == 403


class TestLegacyRolesHardened:
    def test_legacy_viewer_and_editor_are_blocked(self, guest_client):
        _make_project(guest_client)
        # Pre-migration roles aren't in the permissions map -> view (0).
        for role in ("viewer", "editor"):
            h = _tok(f"legacy_{role}", role)
            assert _new_cr(guest_client, h).status_code == 403, role
            assert _new_req(guest_client, h).status_code == 403, role


class TestProjectPermissionMap:
    def test_map_can_elevate_contributor_to_edit(self, guest_client):
        _make_project(guest_client)
        cont = _tok("cont", "contributor")
        assert _new_req(guest_client, cont).status_code == 403      # default: denied

        store = get_store("p")
        meta = store.read_meta()
        meta["permissions"] = {"guest": "view", "contributor": "edit",
                               "maintainer": "edit", "admin": "admin"}
        store.write_meta(meta)

        assert _new_req(guest_client, cont, "R-2").status_code == 201  # now allowed

    def test_map_cannot_demote_a_global_admin(self, guest_client):
        _make_project(guest_client)
        store = get_store("p")
        meta = store.read_meta()
        meta["permissions"] = {"admin": "view"}  # try to strip admin
        store.write_meta(meta)

        adm = {"Authorization": f"Bearer {auth.create_token('adm', 'admin')}"}
        assert _new_req(guest_client, adm, "R-3").status_code == 201
