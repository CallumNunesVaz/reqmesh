"""`/ready` — a saturation probe for the sync threadpool.

`/health` is an async route returning a constant dict, so it answers "ok" on the
event loop even when every sync worker thread is wedged and real requests are
timing out. `/ready` observes the thing that actually saturates: anyio's worker
threadpool, which is where Starlette runs the sync (CPU-bound) routes.
"""
from app.core.config import settings


def test_ready_healthy_pool_matches_contract(client):
    res = client.get("/ready")
    assert res.status_code == 200

    body = res.json()
    assert set(body) == {"ready", "reason", "threadpool", "version"}
    assert body["ready"] is True
    assert body["reason"] == ""

    pool = body["threadpool"]
    assert set(pool) == {"capacity", "busy", "queued"}
    assert isinstance(pool["capacity"], int)
    assert isinstance(pool["busy"], int)
    assert isinstance(pool["queued"], int)
    assert pool["capacity"] > 0
    assert pool["busy"] < pool["capacity"]


def test_ready_saturated_returns_503(client, monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(
        main_mod,
        "_threadpool_snapshot",
        lambda: {"capacity": 4, "busy": 4, "queued": 7},
    )
    res = client.get("/ready")
    assert res.status_code == 503

    body = res.json()
    assert body["ready"] is False
    assert body["reason"] == "threadpool-saturated"
    assert body["threadpool"] == {"capacity": 4, "busy": 4, "queued": 7}


def test_health_keeps_its_exact_shape(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert set(res.json()) == {"status", "version", "profile"}


def test_ready_requires_no_auth(guest_client, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    assert guest_client.get("/ready").status_code == 200
