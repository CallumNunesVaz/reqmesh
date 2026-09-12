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
    "Definition": "definition",
    "Analysis Case": "analysis",
    "Comment": "comment",
    "Item": "item",
}


def build_entity_index(store) -> dict[str, tuple[str, str]]:
    """Build one ``id → (kind_label, name)`` index for a whole request.

    ``resolve_entity_label`` rebuilds the id maps for every collection on each
    call. A caller that resolves thousands of audit entries (the activity
    endpoint) should build this once and pass it in, turning
    O(entries × entities) into O(entities).

    Iterated highest-precedence first so a higher-precedence collection wins a
    shared id, matching :func:`resolve_entity_label`'s order.
    """
    index: dict[str, tuple[str, str]] = {}
    for collection, label in (
        ("requirements", "Requirement"),
        ("verification_cases", "Verification"),
        ("components", "Component"),
        ("specifications", "Specification"),
        ("risks", "Risk"),
        ("change_requests", "Change Request"),
        ("decisions", "Decision"),
        ("definitions", "Definition"),
        ("analysis_cases", "Analysis Case"),
        ("comments", "Comment"),
    ):
        try:
            for it in store.list_items(collection):
                iid = it.get("id")
                if iid and iid not in index:
                    index[iid] = (label, it.get("title", "") or it.get("name", ""))
        except Exception:
            continue
    return index


def resolve_entity_label(store, item_id: str,
                         index: dict[str, tuple[str, str]] | None = None) -> tuple[str, str]:
    """Return ``(kind_label, name)`` for an audited item id.

    Pass ``index`` (from :func:`build_entity_index`) when resolving many ids in
    one request to avoid rebuilding every collection's map per call.

    Precedence (the same order ``Publisher._entity_label`` used before the
    lift — kept deliberately so existing behaviour is preserved):

    1. requirements
    2. verification cases
    3. components
    4. specifications
    5. risks
    6. change requests
    7. decisions
    8. definitions
    9. analysis cases
    10. comments

    Falls back to ``("Item", "")``.

    Because ids are not globally unique, an item whose id collides with one in
    a higher-precedence collection will resolve to the wrong kind.  Recording
    the collection alongside the audit entry is the proper fix (out of scope
    here).
    """
    if index is not None:
        return index.get(item_id, ("Item", ""))

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
        ("Definition", "definitions"),
        ("Analysis Case", "analysis_cases"),
        ("Comment", "comments"),
    ):
        try:
            for it in store.list_items(collection):
                if it.get("id") == item_id:
                    return kind_label, it.get("title", "") or it.get("name", "")
        except Exception:
            pass

    # Deleted items keep their audit trail but no longer resolve to a record.
    return "Item", ""
