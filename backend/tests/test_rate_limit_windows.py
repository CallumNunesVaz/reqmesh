"""Per-bucket window eviction: a short-window sweep must not evict a long-window bucket.

`_evict_old_buckets` used to take the caller's window and sweep the entire
``_window_attempts`` dict against it. A request to a 60-second endpoint (login)
then deleted the buckets of the 300-second endpoints (register, forgot-password,
verify-email) whose timestamps were still fresh, silently degrading the strictest
limits in the app. The fix keys each bucket on its window and evicts against each
bucket's own window.
"""

import time

import pytest
from fastapi import HTTPException

from app.core import rate_limit as rl
from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Reset the in-memory limiter state so ordering cannot leak between tests."""
    rl._window_attempts.clear()
    rl._last_eviction = 0.0
    yield
    rl._window_attempts.clear()
    rl._last_eviction = 0.0


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeRequest:
    """The minimal surface ``rate_limit`` reads: client host, URL path, headers."""

    def __init__(self, path, host="203.0.113.7"):
        self.url = _FakeURL(path)
        self.client = _FakeClient(host)
        self.headers = {}


def test_short_window_sweep_does_not_evict_long_window_bucket():
    """The reproduction, inverted: a 300 s bucket 100 s old survives a 60 s sweep."""
    now = time.time()
    key = "1.2.3.4:/api/auth/forgot-password:300"
    rl._window_attempts[key] = (300, [now - 100, now - 99, now - 98])
    rl._last_eviction = 0.0

    rl._evict_old_buckets(now)

    assert key in rl._window_attempts
    assert rl._window_attempts[key][1] == [now - 100, now - 99, now - 98]


def test_genuinely_stale_bucket_is_evicted():
    """Eviction is not turned off: a bucket whose timestamps are all past its
    own window is still pruned (otherwise the dict leaks memory)."""
    now = time.time()
    key = "1.2.3.4:/api/auth/forgot-password:300"
    rl._window_attempts[key] = (300, [now - 400, now - 399, now - 398])
    rl._last_eviction = 0.0

    rl._evict_old_buckets(now)

    assert key not in rl._window_attempts


def test_independent_windows_on_one_path(monkeypatch):
    """Two limiters on one path with different windows do not share a bucket."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "time", lambda: clock["now"])

    limiter_60 = rl.rate_limit(3, 60)
    limiter_300 = rl.rate_limit(3, 300)
    req = _FakeRequest("/api/auth/something")

    for _ in range(3):
        limiter_60(req)
    with pytest.raises(HTTPException) as exc:
        limiter_60(req)
    assert exc.value.status_code == 429

    # The 300 s limiter on the same path is unaffected.
    for _ in range(3):
        limiter_300(req)


def test_forgot_password_survives_login_eviction_sweep(guest_client, monkeypatch):
    """End to end: login's 60 s sweep must not evict the 300 s forgot-password bucket."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    clock = {"now": 100.0}
    monkeypatch.setattr(rl.time, "time", lambda: clock["now"])
    rl._last_eviction = 0.0

    for _ in range(3):
        assert guest_client.post("/api/auth/forgot-password",
                                 json={"username": "nobody"}).status_code != 429
    assert guest_client.post("/api/auth/forgot-password",
                             json={"username": "nobody"}).status_code == 429

    # 250 s later the forgot-password timestamps are beyond login's 60 s window
    # but still inside their own 300 s window. This is the first moment the
    # throttle (300 s since _last_eviction == 0) lets a sweep fire.
    clock["now"] = 350.0
    for _ in range(5):
        guest_client.post("/api/auth/login",
                          json={"username": "nobody", "password": "wrong"})

    assert guest_client.post("/api/auth/forgot-password",
                             json={"username": "nobody"}).status_code == 429


def test_limiter_still_limits(monkeypatch):
    """max_attempts pass, the next is 429, and the window elapsing clears it."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "time", lambda: clock["now"])

    limiter = rl.rate_limit(3, 60)
    req = _FakeRequest("/api/auth/something")

    for _ in range(3):
        limiter(req)
    with pytest.raises(HTTPException) as exc:
        limiter(req)
    assert exc.value.status_code == 429

    clock["now"] += 61
    limiter(req)  # window elapsed: no longer limited
