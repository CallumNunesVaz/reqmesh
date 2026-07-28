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
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
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
                # Drop the oldest event to make room — a backlogged client
                # needs the freshest data, not stale history.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    # --- Presence -------------------------------------------------------------

    # A connection is considered gone after this long with no heartbeat. The SSE
    # loop touches every 30 s, so this is ten missed beats — long enough to ride
    # out a slow network, short enough that a ghost clears within a coffee break.
    _PRESENCE_TTL_SECONDS = 300

    def _prune(self, project_id: str, now: datetime) -> bool:
        """Drop connections that have stopped heartbeating. Returns True if any went.

        Keyed on ``last_seen``, not ``since``: ``since`` is the join time and is
        never refreshed, so pruning on it evicted anyone whose session had
        simply lasted longer than the TTL — while they were still connected and
        watching the roster lose them.
        """
        roster = self._presence.get(project_id, {})
        stale = [
            cid for cid, info in roster.items()
            if (now - datetime.fromisoformat(info["last_seen"])).total_seconds()
            > self._PRESENCE_TTL_SECONDS
        ]
        for cid in stale:
            del roster[cid]
        return bool(stale)

    def join(self, project_id: str, client_id: str, username: str, role: str) -> None:
        roster = self._presence.setdefault(project_id, {})
        now = datetime.now(timezone.utc)
        self._prune(project_id, now)
        roster[client_id] = {
            "username": username or "guest",
            "role": role or "guest",
            "since": now.isoformat(),
            "last_seen": now.isoformat(),
        }
        self._broadcast_presence(project_id)

    def touch(self, project_id: str, client_id: str) -> None:
        """Mark a connection alive. Called from the SSE loop's heartbeat.

        Deliberately silent — no presence broadcast — so a roomful of idle
        clients heartbeating every 30 s does not generate cross-traffic.
        """
        info = self._presence.get(project_id, {}).get(client_id)
        if info is not None:
            info["last_seen"] = datetime.now(timezone.utc).isoformat()

    def leave(self, project_id: str, client_id: str) -> None:
        roster = self._presence.get(project_id, {})
        if client_id in roster:
            del roster[client_id]
            self._broadcast_presence(project_id)

    def roster(self, project_id: str) -> list[dict]:
        # Prune here too, so a ghost clears on the next read even when nobody
        # new joins — join() alone left it visible indefinitely on a quiet project.
        self._prune(project_id, datetime.now(timezone.utc))
        # last_seen is bookkeeping, not part of the wire format.
        return [
            {k: v for k, v in info.items() if k != "last_seen"}
            for info in self._presence.get(project_id, {}).values()
        ]

    def _broadcast_presence(self, project_id: str) -> None:
        self.publish(project_id, {"type": "presence", "users": self.roster(project_id)})


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus
