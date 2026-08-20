"""Tests for the JSON body size cap middleware.

The cap must hold regardless of what the client declares: a chunked body with no
``Content-Length`` used to bypass the check entirely and Starlette buffered the
whole thing. These tests use a tiny ``max_json_body_mb`` so none of them has to
send hundreds of megabytes.
"""

import pytest

from app.core.config import settings

MAX_BYTES = 1 * 1024 * 1024


@pytest.fixture
def small_body_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_json_body_mb", 1)


def test_content_length_above_limit_is_rejected(client, small_body_limit):
    res = client.post(
        "/api/projects",
        content=b"x" * (MAX_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json() == {"detail": "Request body too large"}


def test_non_integer_content_length_is_rejected(client, small_body_limit):
    res = client.post(
        "/api/projects",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "abc"},
    )
    assert res.status_code == 400
    assert res.json() == {"detail": "Invalid Content-Length"}


def test_chunked_body_above_limit_is_rejected(client, small_body_limit):
    def body():
        yield b"x" * (MAX_BYTES + 1)

    res = client.post(
        "/api/projects",
        content=body(),
        headers={"content-type": "application/json"},
    )
    # 413 and not 401/422: a 401 means auth ran (the cap fired too late) and a
    # 422 means the body reached FastAPI's validation (the cap never fired).
    assert res.status_code == 413
    assert res.json() == {"detail": "Request body too large"}


def test_body_under_limit_passes_through(client, small_body_limit):
    body = ('{"id": "p1", "name": "' + "y" * (MAX_BYTES - 32) + '"}').encode()
    assert len(body) < MAX_BYTES
    res = client.post("/api/projects", content=body, headers={"content-type": "application/json"})
    assert res.status_code == 201
    assert res.json()["id"] == "p1"


def test_websocket_connection_is_not_intercepted(client, small_body_limit):
    with client.websocket_connect("/api/projects/ws-test/ws?token=x") as websocket:
        assert websocket.receive_json()["type"] == "connected"
