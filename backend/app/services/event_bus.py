"""Lightweight pub/sub event bus for SSE change notifications."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone


class EventBus:
    """In-memory publish/subscribe with async queue per listener."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

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


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus
