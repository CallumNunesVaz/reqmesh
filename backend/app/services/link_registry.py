"""One declaration of every cross-entity link in the model.

Before this existed, "what points at a requirement" was knowledge spread across
``integrity.py``, ``tracing.py``, ``publisher.py`` and the individual route
handlers — and each of them knew a slightly different subset. That is why
dangling references held by components were reported while identical ones held
by specifications and decisions were not: someone remembered one list and not
the other.

Everything that needs to traverse the model reads this table instead:
integrity checking, delete protection, backlinks, and suspect-link
propagation. Adding an entity type or a link field means adding a row here, and
every one of those mechanisms picks it up at once.

Not covered on purpose:

* ``requirement.baselines`` holds baseline *names*, not ids, and a baseline is
  a label rather than a record that can dangle.
* ``requirement.attributes`` / ``parameters`` are free-form values.
* ``requirement.references`` point at source files, which live outside the
  store and are validated by the code-scan path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    """One directed reference from a holder record to a target record.

    ``holder``/``target`` are collection names as used by ``YamlStore``.
    ``field`` is the attribute on the holder. ``many`` distinguishes a list of
    ids from a single id.

    ``derived_inverse`` names a field on the *target* that mirrors this link and
    is maintained by the server rather than written by hand.

    ``inverse_stored`` says whether that mirror is also persisted. When it is
    (``allocated_to``), the two can genuinely fall out of step and the
    integrity checker compares them — a mismatch is a reqmesh bug, not a user
    mistake. When it is not (``verification_cases``, recomputed on every read),
    whatever sits in the YAML is ignored, so comparing against it would report
    a discrepancy that has no effect on anything.

    ``label`` is what the relationship is called in the UI.
    """

    holder: str
    field: str
    target: str
    label: str
    many: bool = True
    derived_inverse: str | None = None
    inverse_stored: bool = True
    # A self-referential tree link (parent). Traversal treats these separately:
    # deleting a node with children is a different question from deleting one
    # that a specification happens to cite.
    tree: bool = False


LINKS: tuple[Link, ...] = (
    # ── requirement → ─────────────────────────────────────────────────────────
    Link("requirements", "parent", "requirements", "parent", many=False, tree=True),
    Link("requirements", "cascade_from", "requirements", "cascaded from", many=False),
    Link("requirements", "subject", "components", "subject", many=False),
    # ── component → ──────────────────────────────────────────────────────────
    Link("components", "parent", "components", "parent", many=False, tree=True),
    Link("components", "satisfies", "requirements", "satisfies",
         derived_inverse="allocated_to"),
    Link("components", "verification_cases", "verification_cases", "verified by"),
    # ── verification case → ──────────────────────────────────────────────────
    # Owns the verify relationship; requirement.verification_cases is derived
    # from it on read. See services/verification_links.py.
    Link("verification_cases", "verified_requirements", "requirements", "verifies",
         derived_inverse="verification_cases", inverse_stored=False),
    # ── everything else that cites a requirement ─────────────────────────────
    Link("specifications", "requirements", "requirements", "contains"),
    Link("change_requests", "affected_requirements", "requirements", "affects"),
    Link("analysis_cases", "scope", "requirements", "scope"),
    Link("decisions", "linked_requirements", "requirements", "decides on"),
    Link("risks", "linked_requirements", "requirements", "threatens"),
    Link("comments", "requirement_id", "requirements", "comments on", many=False),
)


# Human-readable singular names, for messages like "3 specifications".
COLLECTION_LABELS = {
    "requirements": "requirement",
    "components": "component",
    "verification_cases": "verification case",
    "specifications": "specification",
    "change_requests": "change request",
    "analysis_cases": "analysis case",
    "decisions": "decision",
    "risks": "risk",
    "comments": "comment",
    "definitions": "definition",
    "baselines": "baseline",
}


def links_into(collection: str, include_tree: bool = True) -> list[Link]:
    """Every link whose target is *collection* — i.e. what can point at it."""
    return [ln for ln in LINKS
            if ln.target == collection and (include_tree or not ln.tree)]


def links_from(collection: str) -> list[Link]:
    """Every link held by records in *collection*."""
    return [ln for ln in LINKS if ln.holder == collection]


def targets_of(item: dict, link: Link) -> list[str]:
    """The ids *item* points at through *link*, normalized to a list.

    Tolerates the field being absent, None, a bare string where a list is
    declared, or a list containing blanks — all of which occur in
    hand-edited YAML.
    """
    raw = item.get(link.field)
    if raw is None:
        return []
    if link.many:
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            return []
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    return [text] if text else []


def find_referrers(store, collection: str, item_id: str,
                   include_tree: bool = True) -> list[dict]:
    """Every record pointing at ``collection/item_id``.

    Returns ``{holder, id, name, field, label, tree}`` per referrer. One pass
    per holder collection rather than per link, because two links can share a
    holder and the store's per-item reads bypass the collection cache.
    """
    wanted = links_into(collection, include_tree=include_tree)
    if not wanted:
        return []

    by_holder: dict[str, list[Link]] = {}
    for ln in wanted:
        by_holder.setdefault(ln.holder, []).append(ln)

    out: list[dict] = []
    for holder, holder_links in by_holder.items():
        try:
            items = store.list_items(holder)
        except Exception:
            # A collection that does not exist in this project is not an error;
            # older projects predate analysis_cases and definitions.
            continue
        for it in items:
            if holder == collection and it.get("id") == item_id:
                continue          # a record referring to itself is not a referrer
            for ln in holder_links:
                if item_id in targets_of(it, ln):
                    out.append({
                        "holder": holder,
                        "id": it.get("id", ""),
                        "name": it.get("name") or it.get("title") or "",
                        "field": ln.field,
                        "label": ln.label,
                        "tree": ln.tree,
                    })
    out.sort(key=lambda r: (r["holder"], r["id"]))
    return out


def find_dangling(store) -> list[dict]:
    """Every reference in the project whose target does not exist.

    Ids are loaded once per collection; the previous per-check implementations
    each rebuilt their own id sets, which is why they drifted apart.
    """
    ids: dict[str, set] = {}
    for name in {ln.target for ln in LINKS} | {ln.holder for ln in LINKS}:
        try:
            ids[name] = {i.get("id") for i in store.list_items(name)}
        except Exception:
            ids[name] = set()

    issues: list[dict] = []
    for holder in sorted({ln.holder for ln in LINKS}):
        try:
            items = store.list_items(holder)
        except Exception:
            continue
        for it in items:
            for ln in links_from(holder):
                for target_id in targets_of(it, ln):
                    if target_id not in ids.get(ln.target, set()):
                        issues.append({
                            "type": "dangling_reference",
                            "holder": holder,
                            "id": it.get("id", ""),
                            "field": ln.field,
                            "target": target_id,
                            "target_collection": ln.target,
                            "severity": "error",
                        })
    return issues
