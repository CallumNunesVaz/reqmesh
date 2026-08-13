"""Write-time validation of link targets, shared by every route that accepts
ids pointing at another collection.

A link to something that does not exist is a silent hole in traceability: it
sits in the YAML, renders as a broken edge, and is only noticed if someone runs
``GET /validate``. Component links (``satisfies`` / ``verification_cases``) have
been guarded on write since ``component_routes._validate_links``; the other
id-bearing fields were not, so a typo'd requirement in a risk's
``linked_requirements`` was accepted and surfaced much later. This module is the
single implementation every write path uses, so a missing target is rejected at
the API boundary with one error shape rather than six copies of the check
drifting apart.

Not covered on purpose — for the same reasons ``link_registry`` leaves them out:

* ``requirement.baselines`` / ``component.baselines`` hold baseline *names*, not
  ids; a baseline is a label rather than a record that can dangle.
* ``change_request.creates`` legitimately names ids that do not exist yet — they
  are the ids the request proposes to *create*, so validating them as targets
  would break the feature.
"""

from __future__ import annotations

#: Singular label per target collection, for the 400 ``detail``. Matches the
#: message shape the component validator already used ("Requirement not found:
#: <id>") so a rejected link reads the same regardless of which entity carries
#: it.
_COLLECTION_LABELS = {
    "requirements": "Requirement",
    "verification_cases": "Verification case",
}


def first_missing(store, targets, allowed: set[str] | None = None) -> str | None:
    """Return the reason the first target does not resolve, or None.

    ``targets`` is a sequence of ``(collection, ids)`` pairs; every id must
    resolve in its collection. The returned string is the ``detail`` for the 400
    the caller raises.

    ``allowed`` names ids that are exempt from the existence check. A change
    request lists its proposed-new ids in ``affected_requirements`` as well as
    in ``creates`` — those ids do not exist yet and must not be rejected.
    """
    allowed = allowed or set()
    for collection, ids in targets:
        for item_id in ids or []:
            if item_id in allowed:
                continue
            if store.get_item(collection, item_id) is None:
                return f"{_COLLECTION_LABELS[collection]} not found: {item_id}"
    return None


def first_missing_relation(store, relations) -> str | None:
    """Return the reason the first relation target does not resolve, or None.

    A relation may name a requirement or a verification case; either is valid.
    Accepts the Pydantic ``Relation`` objects the write models carry, or plain
    dicts.
    """
    for rel in relations or []:
        target = getattr(rel, "target", None)
        if target is None and isinstance(rel, dict):
            target = rel.get("target")
        if not target:
            continue
        if store.get_requirement(target) is None and store.get_verification_case(target) is None:
            return f"Relation target not found: {target}"
    return None
