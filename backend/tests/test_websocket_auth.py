"""WebSocket admission: authenticate before accepting.

The WebSocket used to call ``accept()`` first and treat the token as an
optional identity *upgrade*, never as an admission check — so with
``RT_REQUIRE_AUTH`` on, an anonymous socket still connected, joined the presence
roster, and received a live feed of every mutation. These tests pin the fix:
identity is resolved before the socket is accepted, the WebSocket token is
short-lived and WS-only, and a refused connection never subscribes to anything.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import auth
from app.core.config import settings
from app.main import app
from app.services.event_bus import get_event_bus


@pytest.fixture()
def ws_client(workspace):
    """A real client (no auth dependency overrides) with a project to join."""
    root = Path(settings.data_root) / "demo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "_meta.yaml").write_text("name: Demo\n")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_bus():
    """The event bus is a module-level singleton; isolate it between tests."""
    bus = get_event_bus()
    bus._subscribers.clear()
    bus._presence.clear()
    yield
    bus._subscribers.clear()
    bus._presence.clear()


def _refused(ws_client, url):
    """Attempt a connection and assert the handshake is refused with 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with ws_client.websocket_connect(url):
            pass
    assert exc.value.code == 1008


def test_no_token_or_cookie_is_refused(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    _refused(ws_client, "/api/projects/demo/ws")


def test_valid_session_cookie_connects(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    auth.register_user("alice", "Password123!", "contributor")
    token = auth.create_token("alice", "contributor")  # scp="session"
    with ws_client.websocket_connect("/api/projects/demo/ws",
                                     cookies={"token": token}) as ws:
        assert ws.receive_json()["type"] == "connected"
        assert ws.receive_json()["type"] == "presence"


def test_valid_ws_token_in_query_connects(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    auth.register_user("alice", "Password123!", "contributor")
    token = auth.create_token("alice", "contributor", ttl=120, scope="ws")
    with ws_client.websocket_connect(f"/api/projects/demo/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "connected"
        assert ws.receive_json()["type"] == "presence"


def test_force_logout_invalidates_the_token(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    auth.register_user("alice", "Password123!", "contributor")
    token = auth.create_token("alice", "contributor")
    auth.bump_token_version("alice")
    _refused(ws_client, f"/api/projects/demo/ws?token={token}")


def test_mutation_is_not_delivered_to_a_refused_client(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    bus = get_event_bus()

    _refused(ws_client, "/api/projects/demo/ws")

    # The finding: the anonymous socket used to join the roster and then receive
    # the live feed. Now the refused connection never joined, so a mutation
    # reaches nobody.
    mutation = {"type": "requirement.updated", "project_id": "demo",
                "entity_id": "R-1", "method": "PATCH"}
    bus.publish("demo", dict(mutation))

    assert bus.roster("demo") == []
    assert bus._subscribers.get("demo", []) == []


def test_user_without_read_permission_is_refused(ws_client, monkeypatch):
    """An authenticated token whose role is ``guest`` is refused when auth is
    required — a guest account has no read access in that deployment."""
    monkeypatch.setattr(settings, "require_auth", True)
    auth.register_user("bob", "Password123!", "guest")
    token = auth.create_token("bob", "guest")
    _refused(ws_client, f"/api/projects/demo/ws?token={token}")


def test_anonymous_connects_as_guest_when_auth_not_required(ws_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", False)
    with ws_client.websocket_connect("/api/projects/demo/ws") as ws:
        ws.send_json({"type": "noop"})  # skip the 5s post-accept auth wait
        assert ws.receive_json()["type"] == "connected"
        presence = ws.receive_json()
        assert presence["type"] == "presence"
        assert any(u["username"] == "guest" for u in presence["users"])
