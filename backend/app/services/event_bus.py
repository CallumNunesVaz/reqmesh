"""Lightweight pub/sub event bus for SSE change notifications and presence.

In-memory only: this backs single-process real-time collaboration (live change
notifications plus a "who's viewing this project" presence roster). A restart
clears all subscriptions, which is fine — clients auto-reconnect.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone


class EventBus:
    """In-memory publish/subscribe with an async queue per listener.

    Also tracks presence: each subscriber is a distinct connection with an
    opaque ``client_id``; ``roster`` collapses those into the set of users
    currently viewing a project.
    """

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # project_id -> {client_id: {"username", "role", "since"}}
        self._presence: dict[str, dict[str, dict]] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(project_id, []).append(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(project_id, [])
        if q in subs:
            subs.remove(q)

    def publish(self, project_id: str, event: dict) -> None:
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        for q in self._subscribers.get(project_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # --- Presence -------------------------------------------------------------

    def join(self, project_id: str, client_id: str, username: str, role: str) -> None:
        roster = self._presence.setdefault(project_id, {})
        roster[client_id] = {
            "username": username or "guest",
            "role": role or "viewer",
            "since": datetime.now(timezone.utc).isoformat(),
        }
        self._broadcast_presence(project_id)

    def leave(self, project_id: str, client_id: str) -> None:
        roster = self._presence.get(project_id, {})
        if client_id in roster:
            del roster[client_id]
            self._broadcast_presence(project_id)

    def roster(self, project_id: str) -> list[dict]:
        return list(self._presence.get(project_id, {}).values())

    def _broadcast_presence(self, project_id: str) -> None:
        self.publish(project_id, {"type": "presence", "users": self.roster(project_id)})


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus
