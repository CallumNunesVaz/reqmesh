from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# Bookkeeping fields that change on every write and would drown the log.
_IGNORED_FIELDS = {"modified"}


def diff_fields(before: dict | None, after: dict | None) -> dict:
    before = before or {}
    after = after or {}
    changes = {}
    for key in sorted(set(before) | set(after)):
        if key in _IGNORED_FIELDS:
            continue
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return changes


def record_change(store, item_id: str, action: str, before: dict | None, after: dict | None, user: str = "") -> None:
    """Append a field-level audit entry for an item. No-op if nothing changed."""
    changes = diff_fields(before, after)
    if not changes and action == "update":
        return
    store.append_history(item_id, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user": user,
        "changes": changes,
    })


def prune_all_history(data_root: Path, retention_days: int) -> int:
    """Prune every project's audit history under *data_root*; return the count.

    Walks the data root rather than taking a project id so the startup sweep and
    the admin endpoint share one implementation.
    """
    from app.services.yaml_store import YamlStore

    root = Path(data_root)
    if not root.exists() or retention_days <= 0:
        return 0
    removed = 0
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "_meta.yaml").exists():
            try:
                removed += YamlStore(d).prune_history(retention_days)
            except Exception:
                continue
    return removed
