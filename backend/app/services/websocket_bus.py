"""WebSocket-based alternative to the SSE event bus for real-time collaboration.

Bridges the existing EventBus to WebSocket connections, replicating the SSE
behaviour (presence, mutations, heartbeats) over a persistent WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from app.core.auth import get_user_from_token
from app.core.config import settings
from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

_ws_lock: asyncio.Lock = asyncio.Lock()
_ws_conns_by_user: dict[str, int] = {}
_ws_conns_global: int = 0


async def websocket_handler(websocket: WebSocket, project_id: str, token: str | None = None):
    await websocket.accept()
    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)
    client_id = uuid.uuid4().hex
    username = "guest"
    role = "guest"
    global _ws_conns_global
    # Only decrement what we actually incremented: the limit checks below
    # `return` from inside the try, so the finally runs for rejected
    # connections too.
    counted = False

    try:
        if token:
            user = get_user_from_token(token)
            if user:
                username = user.get("username", "guest")
                role = user.get("role", "guest")

        if not token:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                data = json.loads(raw)
                if data.get("type") == "auth":
                    client_token = data.get("token", "")
                    user = get_user_from_token(client_token)
                    if user:
                        username = user.get("username", "guest")
                        role = user.get("role", "guest")
            except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
                pass

        async with _ws_lock:
            if _ws_conns_global >= settings.max_sse_conns_global:
                await websocket.send_json({"type": "error", "detail": "Too many WebSocket connections. Try again later."})
                await websocket.close(code=1013)
                return
            if _ws_conns_by_user.get(username, 0) >= settings.max_sse_conns_per_user:
                await websocket.send_json({"type": "error", "detail": "Too many WebSocket connections from this user. Try again later."})
                await websocket.close(code=1013)
                return
            _ws_conns_global += 1
            _ws_conns_by_user[username] = _ws_conns_by_user.get(username, 0) + 1
            counted = True

        await websocket.send_json({"type": "connected"})
        bus.join(project_id, client_id, username, role)
        await websocket.send_json({"type": "presence", "users": bus.roster(project_id)})

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                break
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        bus.leave(project_id, client_id)
        bus.unsubscribe(project_id, queue)
        if counted:
            async with _ws_lock:
                _ws_conns_by_user[username] = _ws_conns_by_user.get(username, 0) - 1
                if _ws_conns_by_user[username] <= 0:
                    _ws_conns_by_user.pop(username, None)
                _ws_conns_global -= 1
