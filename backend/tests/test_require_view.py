"""The view gate: a project's ``permissions`` map can now deny reads.

SEC-5 asked for two things and only one shipped — the map became writable but
the ``view`` gate was never built, so the ``view`` tier meant "cannot write"
rather than "can read". These tests pin the gate on ``GET .../publish/download``.

Deliberately do not use the ``client`` fixture here: it installs global
dependency overrides that authorise every other client in the same test as an
admin. Setup goes through a real admin token, exactly like ``test_role_fixtures.py``.
"""
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.dependencies import PERMISSION_LEVELS, user_permission_level
from app.services.yaml_store import YamlStore


@pytest.fixture()
def admin_client(_real_role_client):
    with _real_role_client("admin", "view_admin") as c:
        yield c


@pytest.fixture()
def project(admin_client):
    r = admin_client.post("/api/projects", json={"id": "vp", "name": "VP"})
    assert r.status_code == 201, r.text
    admin_client.patch("/api/projects/vp", json={"naming": {"enforce": False}})
    return "vp"


def _download(client, project, fmt="md"):
    return client.get(f"/api/projects/{project}/publish/download?format={fmt}")


def test_contributor_can_download_with_default_permissions(project, contributor_client):
    """The default map grants ``view`` to every role, so reads keep working."""
    assert _download(contributor_client, project).status_code == 200


def test_contributor_mapped_to_none_is_denied(project, admin_client, contributor_client):
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"contributor": "none"}})
    r = _download(contributor_client, project)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "View permission required"


def test_maintainer_still_downloads_when_contributor_mapped_to_none(project, admin_client, maintainer_client):
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"contributor": "none"}})
    assert _download(maintainer_client, project).status_code == 200


def test_admin_never_demoted_by_the_map(project, admin_client):
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"admin": "none"}})
    assert _download(admin_client, project).status_code == 200


def test_unauthenticated_401_when_require_auth_on(project, guest_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    r = _download(guest_client, project)
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "Authentication required"


def test_unauthenticated_not_401_when_require_auth_off(project, guest_client):
    """With ``RT_REQUIRE_AUTH`` off (the ``personal`` profile), a guest reads as
    ``view`` and must not be bounced with 401."""
    r = _download(guest_client, project)
    assert r.status_code == 200, r.text


def test_none_survives_settings_round_trip(project, admin_client):
    res = admin_client.patch(f"/api/projects/{project}",
                             json={"permissions": {"contributor": "none"}})
    assert res.status_code == 200, res.text
    assert res.json()["permissions"]["contributor"] == "none"
    store = YamlStore(Path(settings.data_root) / project)
    assert store.read_meta()["permissions"]["contributor"] == "none"


def test_none_is_below_view_so_denial_is_expressible(project, admin_client):
    """Regression for the trap in the goal: ``view`` is 0 and unknown roles
    floor at 0, so a gate written as ``level >= PERMISSION_LEVELS["view"]``
    passes for everyone. A suite that only asserted 200s would pass against the
    no-op version of this gate — ``none`` must sit below ``view`` so a project
    can say "no access at all"."""
    assert PERMISSION_LEVELS["none"] < PERMISSION_LEVELS["view"]
    admin_client.patch(f"/api/projects/{project}",
                       json={"permissions": {"contributor": "none"}})
    level = user_permission_level({"role": "contributor"}, project)
    assert level == PERMISSION_LEVELS["none"]
    assert level < PERMISSION_LEVELS["view"]
