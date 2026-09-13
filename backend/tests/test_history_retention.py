"""Audit-history retention.

Retention is opt-in: 0 keeps the full history, which is the default, so a test
pins that nothing is deleted unless an operator asks for it.
"""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.history import prune_all_history
from app.services.yaml_store import YamlStore


def _make_history(store: YamlStore, item_id: str, days_ago: int, tag: str) -> None:
    d = store.history_dir(item_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y%m%dT%H%M%S%f")
    (d / f"{stamp}-{tag}.yaml").write_text("action: update\n")


def test_prune_history_removes_only_old_entries(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    _make_history(store, "R-1", 400, "old")
    _make_history(store, "R-1", 1, "new")

    assert store.prune_history(365) == 1
    remaining = list(store.history_dir("R-1").glob("*.yaml"))
    assert len(remaining) == 1
    assert "new" in remaining[0].name


def test_prune_history_zero_keeps_everything(tmp_path):
    store = YamlStore(tmp_path / "p")
    store.ensure_dirs()
    _make_history(store, "R-1", 4000, "ancient")
    assert store.prune_history(0) == 0
    assert len(list(store.history_dir("R-1").glob("*.yaml"))) == 1


def test_prune_all_history_walks_projects(tmp_path):
    root = tmp_path / "projects"
    for pid in ("a", "b"):
        s = YamlStore(root / pid)
        s.ensure_dirs()
        s.write_meta({"name": pid})
        _make_history(s, "R-1", 400, "old")
    # A directory without _meta.yaml is not a project and is skipped.
    (root / "not-a-project").mkdir()
    assert prune_all_history(root, 365) == 2


def test_prune_endpoint_is_disabled_until_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "history_retention_days", 0)
    assert client.post("/api/system/history/prune").status_code == 400


def test_prune_endpoint_runs_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "history_retention_days", 365)
    res = client.post("/api/system/history/prune")
    assert res.status_code == 200, res.text
    assert res.json()["retention_days"] == 365
