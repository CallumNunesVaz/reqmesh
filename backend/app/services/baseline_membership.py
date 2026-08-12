"""Additive baseline membership for bulk operations.

Membership is curated: a requirement's ``baselines`` list is the record of
which milestones a human decided it belongs to. The bulk bar used to *replace*
that list with the single baseline being applied, so ticking twenty rows and
picking "PDR" silently dropped every other baseline those rows carried.

The read-modify-write lives here rather than in the client because the client
merges against the snapshot from its last load. A collaborator adding a
baseline in between would be clobbered by the merged write, and the bulk
endpoints have no precondition path (``_check_precondition`` guards only the
single-item PUTs) for the client to notice with.
"""
from __future__ import annotations

from app.core.filelock import file_lock
from app.services.history import record_change


def defined_baseline_names(meta: dict) -> set[str]:
    """The baseline names declared in ``_meta.yaml``.

    Accepts the legacy bare-string form alongside the object form, matching
    ``normalize_baseline_defs``. That function is not reused here because it
    lives in the API layer, and a service importing from ``app.api`` would
    invert the dependency.
    """
    names: set[str] = set()
    for item in (meta.get("baselines") or []):
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name", "")
        else:
            continue
        if name:
            names.add(name)
    return names


def apply_membership(
    store,
    ids: list[str],
    add: list[str],
    remove: list[str],
    username: str = "",
) -> dict:
    """Add and/or remove baseline memberships across *ids*.

    Returns the ids that *actually changed*, not the ids asked for. An undo
    built from these will not strip a baseline from a requirement that already
    carried it before the bulk action ran.

    Order within a requirement's list is preserved: additions append, so a
    frozen sequence is never reshuffled by an unrelated bulk edit.
    """
    add_set = [b for b in (add or []) if b]
    remove_set = {b for b in (remove or []) if b}

    added: list[str] = []
    removed: list[str] = []
    updated: list[str] = []

    for item_id in ids:
        path = store._item_path("requirements", item_id)
        # Hold the item lock across the read-modify-write so a concurrent
        # baseline edit to the same requirement cannot clobber this one.
        with file_lock(path):
            before = store.get_requirement(item_id)
            if before is None:
                continue

            current = list(before.get("baselines") or [])
            after = [b for b in current if b not in remove_set]
            for name in add_set:
                if name not in after:
                    after.append(name)

            if after == current:
                continue

            result = store._update_item_unlocked("requirements", item_id, {"baselines": after})
            if not result:
                continue

            record_change(store, item_id, "update", before, result, username)
        updated.append(item_id)
        if any(b not in current for b in after):
            added.append(item_id)
        if any(b not in after for b in current):
            removed.append(item_id)

    return {
        "updated": len(updated),
        "ids": updated,
        "added": added,
        "removed": removed,
    }
