"""A cluster of low-severity security findings (S5, S7, S8, S9/D7, S12, C7).

Each section pins one finding so the suite fails if any of them regresses:

* S7 — ``GET /projects`` must not disclose absolute filesystem paths.
* S8 — ``POST /auth/register`` must validate an admin-supplied role.
* S12 — a ``scope="ws"`` token must not act as an HTTP session credential.
* S5 — ``proxy_trusted_cidr`` defaults to loopback only, so a LAN peer cannot
  spoof ``X-Forwarded-For``.
* C7 — concurrent ``run_migrations`` calls must leave a single valid marker.
"""
from __future__ import annotations

import json
import threading

from fastapi.testclient import TestClient
from ruamel.yaml import YAML

from app.core import auth
from app.core import rate_limit
from app.core.config import Settings, settings
from app.main import app
from app.services import migrations


# ── S7 — GET /projects must not disclose absolute paths ───────────────────────


def test_list_projects_has_no_path(client, project):
    res = client.get("/api/projects")
    assert res.status_code == 200
    items = res.json()
    assert items, "expected at least one project"
    for item in items:
        assert "path" not in item, f"GET /projects leaked a filesystem path: {item!r}"
        assert "id" in item
        assert "name" in item


# ── S8 — admin-assigned roles are validated on the register path ──────────────


def test_register_admin_rejects_unknown_role(guest_client, workspace):
    auth.register_user("boss", "Password123!", "admin")
    token = auth.create_token("boss", "admin")
    res = guest_client.post(
        "/api/auth/register",
        json={"username": "wiz", "password": "Password123!", "role": "wizard"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400


def test_register_admin_accepts_known_role(guest_client, workspace):
    auth.register_user("boss", "Password123!", "admin")
    token = auth.create_token("boss", "admin")
    res = guest_client.post(
        "/api/auth/register",
        json={"username": "maint", "password": "Password123!", "role": "maintainer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert auth.load_users()["maint"]["role"] == "maintainer"


# ── S12 — a ws-scoped token is not an HTTP credential ─────────────────────────


def test_ws_scoped_token_rejected_on_http_route(workspace, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    auth.register_user("alice", "Password123!", "contributor")
    ws_token = auth.create_token("alice", "contributor", ttl=120, scope="ws")
    session_token = auth.create_token("alice", "contributor")

    with TestClient(app) as c:
        rejected = c.get("/api/projects",
                         headers={"Authorization": f"Bearer {ws_token}"})
        accepted = c.get("/api/projects",
                         headers={"Authorization": f"Bearer {session_token}"})

    assert rejected.status_code == 401
    assert accepted.status_code == 200


# ── S5 — proxy trust is narrowed to loopback by default ───────────────────────


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, xff: str | None = None) -> None:
        self.client = _FakeClient(host)
        self.headers = {"X-Forwarded-For": xff} if xff else {}


def test_proxy_trusted_cidr_default_is_loopback():
    assert Settings().proxy_trusted_cidr == "127.0.0.0/8"


def test_lan_peer_x_forwarded_for_is_not_trusted(monkeypatch):
    monkeypatch.setattr(settings, "proxy_trusted_cidr", "127.0.0.0/8")
    rate_limit._trusted_proxies._cache = None  # type: ignore[attr-defined]

    # The immediate peer is a LAN host, so the spoofed X-Forwarded-For must be
    # ignored and the peer's own IP returned.
    assert rate_limit._is_trusted_proxy("10.0.0.5") is False
    assert rate_limit._client_ip(_FakeRequest("10.0.0.5", "1.2.3.4")) == "10.0.0.5"

    # Loopback is still trusted, so X-Forwarded-For is honoured there.
    assert rate_limit._is_trusted_proxy("127.0.0.1") is True


# ── C7 — concurrent migrations leave a single valid marker ────────────────────


def test_concurrent_run_migrations_leave_a_single_valid_marker(tmp_path):
    yaml = YAML()
    data_root = tmp_path / "data"
    proj = data_root / "p1"
    (proj / "comments").mkdir(parents=True)
    (proj / "_meta.yaml").write_text("name: P1\n")
    with open(proj / "comments" / "C1.yaml", "w") as f:
        yaml.dump({"id": "C1", "requirement_id": "R-1", "text": "hello"}, f)

    errors: list[Exception] = []

    def run() -> None:
        try:
            migrations.run_migrations(data_root)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion
            errors.append(exc)

    # Enough iterations and threads to actually race the marker read-modify-write.
    for _ in range(10):
        (data_root / ".reqmesh-schema.json").write_text(
            json.dumps({"schema_version": 1}))
        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads), "migration did not finish"
        assert migrations.read_schema_version(data_root) == migrations.CURRENT_SCHEMA_VERSION

    assert not errors, errors
    marker = json.loads((data_root / ".reqmesh-schema.json").read_text())
    assert marker == {"schema_version": migrations.CURRENT_SCHEMA_VERSION}
    # The migration's real work happened (idempotently, not twice).
    comment = yaml.load((proj / "comments" / "C1.yaml").read_text())
    assert comment["entity_id"] == "R-1"
    assert "requirement_id" not in comment
