"""Refuse a delete that would leave references pointing at nothing.

Deleting a record used to be a single-file operation: nothing looked for who
was pointing at it, so removing a requirement left every specification, change
request, decision, risk, component and verification case that cited it holding
a dead id. Only the component ones were ever reported.

The guard reports rather than repairs. Cascading the cleanup automatically
would mean editing records the deleter may not own — a specification silently
losing a requirement, showing up in git history as an unattributed change to
someone else's document. Making the caller pass ``force=true`` keeps the
decision with the person who has the context, and puts their name on it.

Tree links (``parent``) are deliberately *not* guarded. Deleting a node with
children already has defined behaviour — components promote their children to
the grandparent — and blocking it would break a working feature to protect
against something the code already handles. The guard is about citations from
elsewhere in the model, which nothing handles.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.services.errors import error_envelope
from app.services.link_registry import COLLECTION_LABELS, find_referrers


def _describe(referrers: list[dict]) -> str:
    by_holder: dict[str, int] = {}
    for r in referrers:
        by_holder[r["holder"]] = by_holder.get(r["holder"], 0) + 1
    parts = []
    for holder, n in sorted(by_holder.items()):
        label = COLLECTION_LABELS.get(holder, holder)
        parts.append(f"{n} {label}{'s' if n != 1 else ''}")
    return ", ".join(parts)


def check_deletable(store, collection: str, item_id: str, force: bool = False) -> list[dict]:
    """Raise 409 if anything references ``collection/item_id``.

    Returns the referrer list so the caller can record it. With ``force`` the
    references are returned rather than raised on, and the caller proceeds —
    the records are left pointing at a missing id, which the integrity check
    will then report as ``dangling_reference``.
    """
    referrers = find_referrers(store, collection, item_id, include_tree=False)
    if force or not referrers:
        return referrers

    label = COLLECTION_LABELS.get(collection, collection)
    raise HTTPException(
        status_code=409,
        detail=error_envelope(
            "referenced",
            (
                f"This {label} is referenced by {_describe(referrers)}. "
                f"Deleting it will leave those references pointing at nothing. "
                f"Retry with force=true to delete anyway."
            ),
            id=item_id,
            collection=collection,
            referrers=referrers,
        ),
    )
