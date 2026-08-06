"""Entity kind resolver for audit history entries.

Item ids are keyed by collection, not globally unique — a component and a
requirement can share an id (``test_component_links.py`` asserts exactly this).
The resolver picks the first match in a fixed precedence order and will
misidentify an item whose id collides with one from a higher-precedence
collection. The correct fix is recording the collection in the audit entry at
write time, which is a separate migration.
"""
from __future__ import annotations

# Mapping from the resolver's human label to the API/canonical kind key used by
# the activity endpoint and the chart stacking order.
KIND_LABEL_TO_KEY: dict[str, str] = {
    "Requirement": "requirement",
    "Verification": "verification",
    "Component": "component",
    "Specification": "specification",
    "Risk": "risk",
    "Change Request": "change",
    "Decision": "decision",
    "Item": "item",
}


def resolve_entity_label(store, item_id: str) -> tuple[str, str]:
    """Return ``(kind_label, name)`` for an audited item id.

    Precedence (the same order ``Publisher._entity_label`` used before the
    lift — kept deliberately so existing behaviour is preserved):

    1. requirements
    2. verification cases
    3. components
    4. specifications
    5. risks
    6. change requests
    7. decisions

    Falls back to ``("Item", "")``.

    Because ids are not globally unique, an item whose id collides with one in
    a higher-precedence collection will resolve to the wrong kind.  Recording
    the collection alongside the audit entry is the proper fix (out of scope
    here).
    """
    # The collection cache inside the store makes repeated list_* calls in a
    # tight loop virtually free after the first — each list populates the
    # in‑memory cache, and a unit of work that calls this function hundreds of
    # times (the changelog, the activity aggregator) pays the I/O cost once per
    # collection.

    reqs_by_id = {r["id"]: r for r in store.list_requirements()}
    if item_id in reqs_by_id:
        return "Requirement", reqs_by_id[item_id].get("name", "")

    vcs_by_id = {v["id"]: v for v in store.list_verification_cases()}
    if item_id in vcs_by_id:
        return "Verification", vcs_by_id[item_id].get("name", "")

    comps_by_id = {c["id"]: c for c in store.list_components()}
    if item_id in comps_by_id:
        return "Component", comps_by_id[item_id].get("name", "")

    specs_by_id = {s["id"]: s for s in store.list_specifications()}
    if item_id in specs_by_id:
        return "Specification", specs_by_id[item_id].get("name", "")

    for kind_label, collection in (
        ("Risk", "risks"),
        ("Change Request", "change_requests"),
        ("Decision", "decisions"),
    ):
        try:
            for it in store.list_items(collection):
                if it.get("id") == item_id:
                    return kind_label, it.get("title", "") or it.get("name", "")
        except Exception:
            pass

    # Deleted items keep their audit trail but no longer resolve to a record.
    return "Item", ""
