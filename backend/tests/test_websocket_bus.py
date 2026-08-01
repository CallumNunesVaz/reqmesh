"""WebSocket connection limits.

This module previously had no tests at all, and it showed. When connection
limits were added, two defects shipped together:

  * two ``global _ws_conns_global`` declarations in one function, the second
    after the name was used — a **SyntaxError**, so the module could not be
    imported. ``collab_routes`` imports it lazily inside the handler, so the
    app started, the whole suite passed, and the failure only surfaced when a
    real user opened a socket.
  * the limit checks ``return`` from inside the ``try``, so the ``finally``
    decremented a counter that was never incremented. Each rejected connection
    pushed the global count down, so tripping the limit once left it below the
    threshold — the protection inverted into unlimited connections.

The first test is deliberately an import: that alone would have caught the
SyntaxError.
"""

import asyncio

import pytest


def test_the_module_imports():
    """A SyntaxError here is invisible to every other test in the suite."""
    from app.services import websocket_bus
    assert callable(websocket_bus.websocket_handler)


class FakeWebSocket:
    """Disconnects after *sends_before_drop* messages.

    An accepted connection sits in a `while True` loop that only exits on
    disconnect, so a fake that never drops hangs the test forever rather than
    failing. Raising WebSocketDisconnect from send_json is how a real client
    going away surfaces here.
    """

    def __init__(self, sends_before_drop: int = 1):
        self.closed_code = None
        self.sent: list[dict] = []
        self._budget = sends_before_drop

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)
        if self._budget <= 0:
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect(code=1001)
        self._budget -= 1

    async def close(self, code=1000):
        self.closed_code = code

    async def receive_text(self):
        raise asyncio.TimeoutError


@pytest.fixture
def bus(monkeypatch):
    from app.services import websocket_bus as wb
    monkeypatch.setattr(wb.settings, "max_sse_conns_global", 2, raising=False)
    monkeypatch.setattr(wb.settings, "max_sse_conns_per_user", 1, raising=False)
    wb._ws_conns_global = 0
    wb._ws_conns_by_user.clear()
    yield wb
    wb._ws_conns_global = 0
    wb._ws_conns_by_user.clear()


def test_a_connection_over_the_global_limit_is_refused(bus):
    bus._ws_conns_global = 2
    ws = FakeWebSocket()
    asyncio.run(bus.websocket_handler(ws, "p"))
    assert ws.closed_code == 1013
    assert any("Too many" in str(m) for m in ws.sent)


def test_rejected_connections_do_not_corrupt_the_counter(bus):
    """The regression: each rejection used to decrement, so tripping the limit
    once left the count below the threshold and the limit stopped applying."""
    bus._ws_conns_global = 2
    for _ in range(5):
        asyncio.run(bus.websocket_handler(FakeWebSocket(), "p"))
    assert bus._ws_conns_global == 2, (
        f"counter drifted to {bus._ws_conns_global} — rejections are decrementing"
    )


def test_rejected_connections_do_not_corrupt_the_per_user_counter(bus):
    bus._ws_conns_by_user["guest"] = 1          # already at the per-user limit
    bus._ws_conns_global = 0
    for _ in range(3):
        asyncio.run(bus.websocket_handler(FakeWebSocket(), "p"))
    assert bus._ws_conns_by_user.get("guest", 0) == 1


def test_an_accepted_connection_releases_its_slot(bus):
    """The client drops after the handshake, so the handler runs to completion
    and the finally must give the slot back."""
    asyncio.run(bus.websocket_handler(FakeWebSocket(sends_before_drop=1), "p"))
    assert bus._ws_conns_global == 0
    assert bus._ws_conns_by_user == {}
