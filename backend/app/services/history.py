from __future__ import annotations

from datetime import datetime, timezone

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
