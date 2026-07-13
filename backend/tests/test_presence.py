"""Tests for real-time collaboration presence (Phase 5)."""

from __future__ import annotations

import asyncio

from app.services.event_bus import EventBus


def test_event_bus_presence_join_leave():
    bus = EventBus()
    assert bus.roster("proj") == []

    bus.join("proj", "c1", "alice", "editor")
    bus.join("proj", "c2", "bob", "viewer")
    roster = bus.roster("proj")
    assert {u["username"] for u in roster} == {"alice", "bob"}
    assert {u["role"] for u in roster} == {"editor", "viewer"}

    bus.leave("proj", "c1")
    assert {u["username"] for u in bus.roster("proj")} == {"bob"}

    bus.leave("proj", "c2")
    assert bus.roster("proj") == []


def test_event_bus_join_broadcasts_presence():
    async def scenario():
        bus = EventBus()
        q = bus.subscribe("proj")
        bus.join("proj", "c1", "alice", "editor")
        return await asyncio.wait_for(q.get(), timeout=1.0)

    event = asyncio.run(scenario())
    assert event["type"] == "presence"
    assert event["users"][0]["username"] == "alice"


def test_presence_endpoint_empty(client, project):
    res = client.get(f"/api/projects/{project}/presence")
    assert res.status_code == 200
    body = res.json()
    assert body == {"users": [], "count": 0}
