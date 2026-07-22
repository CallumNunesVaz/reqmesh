"""WebSocket-based alternative to the SSE event bus for real-time collaboration.

Bridges the existing EventBus to WebSocket connections, replicating the SSE
behaviour (presence, mutations, heartbeats) over a persistent WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from app.core.auth import get_user_from_token
from app.services.event_bus import get_event_bus


async def websocket_handler(websocket: WebSocket, project_id: str, token: str | None = None):
    await websocket.accept()
    bus = get_event_bus()
    queue: asyncio.Queue = bus.subscribe(project_id)
    client_id = uuid.uuid4().hex
    username = "guest"
    role = "viewer"

    try:
        if token:
            user = get_user_from_token(token)
            if user:
                username = user.get("username", "guest")
                role = user.get("role", "viewer")

        if not token:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                data = json.loads(raw)
                if data.get("type") == "auth":
                    client_token = data.get("token", "")
                    user = get_user_from_token(client_token)
                    if user:
                        username = user.get("username", "guest")
                        role = user.get("role", "viewer")
            except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
                pass

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
