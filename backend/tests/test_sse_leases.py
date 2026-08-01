"""The SSE connection cap must not be able to lock a user out permanently.

The cap used to be a pair of hand-maintained counters: incremented in the route
handler, decremented in the streaming generator's ``finally``. Those two live in
different scopes, so any path that took a slot without the generator running to
completion leaked it, and nothing ever gave it back. On the production host this
reached the per-user cap of 5, and every reconnect 429'd for eight hours while
the browser retried in a tight loop.

Slots are leases now. These tests pin the three properties that matter: the cap
is still enforced, a released slot frees up, and a slot that escapes release
expires on its own rather than being held forever.

Driven through ``_acquire_lease`` rather than the HTTP route on purpose — an SSE
response never ends, so a test that opens one waits for a stream that will not
close.
"""

import time

import pytest

from app.api import collab_routes as sse


PER_USER = sse.settings.max_sse_conns_per_user


@pytest.fixture(autouse=True)
def _clean_leases():
    sse._sse_leases.clear()
    yield
    sse._sse_leases.clear()


def _fill(username: str, count: int, age: float = 0.0) -> None:
    stamp = time.monotonic() - age
    for i in range(count):
        sse._sse_leases[f"{username}-{i}"] = (username, stamp)


def test_the_cap_is_enforced_for_live_connections():
    _fill("ada", PER_USER)
    assert sse._acquire_lease("new", "ada", time.monotonic()) == (
        "Too many SSE connections from this user. Try again later."
    )


def test_releasing_a_slot_frees_it():
    _fill("ada", PER_USER)
    sse._sse_leases.pop("ada-0")
    assert sse._acquire_lease("new", "ada", time.monotonic()) is None


def test_one_user_at_the_cap_does_not_block_another():
    _fill("ada", PER_USER)
    assert sse._acquire_lease("new", "grace", time.monotonic()) is None


def test_a_leaked_slot_expires_instead_of_locking_the_user_out():
    """The regression. Every slot held and none of them ever released."""
    _fill("ada", PER_USER, age=sse._SSE_LEASE_TTL_SECONDS + 1)

    assert sse._acquire_lease("new", "ada", time.monotonic()) is None, (
        "stale leases were not reclaimed — this is the state the old counters "
        "reached and could never leave"
    )
    assert list(sse._sse_leases) == ["new"]


def test_a_heartbeating_connection_is_never_reaped():
    """The TTL is a backstop for lost connections, not a session timeout."""
    _fill("ada", PER_USER, age=sse._SSE_LEASE_TTL_SECONDS - 1)
    assert sse._acquire_lease("new", "ada", time.monotonic()) is not None
    assert len(sse._sse_leases) == PER_USER


def test_the_global_cap_still_applies(monkeypatch):
    monkeypatch.setattr(sse.settings, "max_sse_conns_global", 3, raising=False)
    for i in range(3):
        sse._sse_leases[f"c{i}"] = (f"user{i}", time.monotonic())
    assert sse._acquire_lease("new", "someone-else", time.monotonic()) == (
        "Too many SSE connections. Try again later."
    )
