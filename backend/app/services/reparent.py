"""Planning and application of bulk reparent moves.

Split into a pure planner and an applier so the move can be *previewed*. With
``re_prefix`` a move renames the requirement and its whole subtree and rewrites
relation targets project-wide, which is the most destructive thing the API
does and the one thing it used to do with no confirmation and no audit trail.

The planner is pure and takes the requirement list rather than the store for
two reasons: it can then be run twice (once to preview, once to apply) without
a second scan, and ``test_bulk_move_perf`` caps ``store.list_requirements()``
at three calls for the whole request — a cycle guard that consulted the store
itself, the way the single-item PUT does, would blow that budget.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def leading_prefix(item_id: str) -> str:
    """The leading alphabetic run of an ID, e.g. 'REQ' from 'REQ-0001'."""
    m = re.match(r"^([A-Za-z]+)", item_id or "")
    return m.group(1) if m else ""


def collect_subtree(children_by_parent: dict[str, list[str]], root_id: str) -> list[str]:
    """Return root_id followed by all transitive descendant ids (pre-order)."""
    out = [root_id]
    for child_id in children_by_parent.get(root_id, []):
        out.extend(collect_subtree(children_by_parent, child_id))
    return out


def renumber_subtree(subtree: list[str], old_prefix: str, new_prefix: str,
                     sep: str, width: int, live_nums: set[int]) -> dict[str, str]:
    """Allocate fresh numbers under *new_prefix* for *subtree*, in order.

    The one place the re-prefix arithmetic lives, shared by the bulk reparent
    and the requirement rename cascade. Only nodes that share *old_prefix* are
    renamed (mixed-tree descendants keep their id and get their parent repointed
    by the caller); every node still appears in the returned map, identity where
    unrenamed, so callers can index by old id. *live_nums* is mutated in place,
    so a sequence of calls keeps allocating past earlier ones.
    """
    subtree_new_nums = {int(mm.group(1)) for old_id in subtree
                        if (mm := re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", old_id))}
    effective_used = live_nums - subtree_new_nums
    next_num = (max(effective_used) + 1) if effective_used else 1
    local_map = {old_id: old_id for old_id in subtree}
    for old_id in subtree:
        if old_id.startswith(old_prefix):
            local_map[old_id] = f"{new_prefix}{sep}{str(next_num).zfill(width)}"
            live_nums.add(next_num)
            next_num += 1
    return local_map


@dataclass
class RenameGroup:
    """One moved subtree whose ids are being rewritten to the new prefix."""
    root_id: str
    order: list[str]                      # subtree ids, pre-order
    local_map: dict[str, str]             # old id -> new id (identity if unrenamed)


@dataclass
class ReparentPlan:
    new_parent: str | None
    simple_moves: list[str] = field(default_factory=list)
    groups: list[RenameGroup] = field(default_factory=list)
    id_map: dict[str, str] = field(default_factory=dict)   # old -> new, renames only
    rejected: list[tuple[str, str]] = field(default_factory=list)

    @property
    def renames(self) -> list[dict[str, str]]:
        return [{"from": k, "to": v} for k, v in sorted(self.id_map.items())]

    @property
    def affected_count(self) -> int:
        return len(self.simple_moves) + sum(len(g.order) for g in self.groups)


def plan_reparent(
    requirements: list[dict],
    ids: list[str],
    new_parent: str | None,
    re_prefix: bool,
) -> ReparentPlan:
    """Work out every write a bulk reparent would perform, without performing any.

    Allocation of new numbers depends on the order of *ids* — each group's
    allocations feed the live used-number set that later groups see — so this
    must iterate *ids* in the caller's order.
    """
    by_id = {r["id"]: r for r in requirements}

    # Snapshot the hierarchy before any mutation so subtree collection is stable.
    children_by_parent: dict[str, list[str]] = {}
    for r in requirements:
        children_by_parent.setdefault(r.get("parent"), []).append(r["id"])

    new_prefix = leading_prefix(new_parent) if new_parent else ""

    # Pre-scan all requirements once to build the used-numbers set for the
    # destination prefix. The per-id rescan in the old code was O(n·m) with a
    # regex per pair; moving 200 requirements in a 5000-requirement project was
    # a million regex matches. This single scan feeds a live set that each
    # group updates with its own allocations, matching the old rescan exactly.
    used_nums_by_prefix: dict[str, set[int]] = {}
    if new_prefix and re_prefix:
        for r in requirements:
            mm = re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", r["id"])
            if mm:
                used_nums_by_prefix.setdefault(new_prefix, set()).add(int(mm.group(1)))

    plan = ReparentPlan(new_parent=new_parent)

    for req_id in ids:
        if req_id not in by_id:
            continue

        # Reparenting must not create a loop. The single-item PUT has guarded
        # this since a cycle made both branches unreachable in the tree, but
        # the bulk path did not — so the same move the API refused one at a
        # time was accepted in a batch.
        if new_parent is not None:
            if new_parent == req_id:
                plan.rejected.append((req_id, "A requirement cannot be its own parent"))
                continue
            if new_parent in collect_subtree(children_by_parent, req_id):
                plan.rejected.append((
                    req_id,
                    f"Setting parent to {new_parent} would create a parent cycle",
                ))
                continue

        old_prefix = leading_prefix(req_id)
        if re_prefix and new_parent and new_prefix and old_prefix and old_prefix != new_prefix:
            subtree = collect_subtree(children_by_parent, req_id)
            # Mirror the new parent's ID shape (separator + zero-padded width)
            # so re-prefixed IDs match the destination namespace's convention.
            pm = re.match(r"^[A-Za-z]+(\D*)(\d+)$", new_parent)
            sep, width = (pm.group(1), len(pm.group(2))) if pm else ("", 4)
            # Use the pre-scanned used-numbers set, warmed by allocations from
            # earlier groups. Exclude any subtree node that already bears the
            # new prefix — the old per-id scan did the same, and changing it
            # would shift the allocation.
            local_map = renumber_subtree(
                subtree, old_prefix, new_prefix, sep, width,
                used_nums_by_prefix.setdefault(new_prefix, set()),
            )
            plan.groups.append(RenameGroup(root_id=req_id, order=subtree, local_map=local_map))
            plan.id_map.update({k: v for k, v in local_map.items() if k != v})
            continue

        plan.simple_moves.append(req_id)

    return plan


def apply_reparent(store, plan: ReparentPlan, username: str = "") -> dict:
    """Execute *plan* against the store. Returns ``{"updated", "ids", "renames"}``."""
    from app.services.history import record_change

    updated: list[str] = []

    for group in plan.groups:
        for old_id in group.order:
            node = store.get_requirement(old_id)
            if node is None:
                continue
            before = dict(node)
            node = dict(node)
            node["id"] = group.local_map[old_id]
            if old_id == group.root_id:
                node["parent"] = plan.new_parent
            else:
                node["parent"] = group.local_map.get(node.get("parent"), node.get("parent"))
            for rel in node.get("relations", []):
                if rel.get("target") in group.local_map:
                    rel["target"] = group.local_map[rel["target"]]
            store.delete_requirement(old_id)
            store.create_requirement(node)
            # A project-wide id rewrite left no audit trail at all before this.
            record_change(store, node["id"], "reparent", before, node, username)
            updated.append(node["id"])

    for req_id in plan.simple_moves:
        before = store.get_requirement(req_id)
        if store.update_requirement(req_id, {"parent": plan.new_parent}):
            after = store.get_requirement(req_id)
            record_change(store, req_id, "reparent", before, after, username)
            updated.append(req_id)

    # Rewrite relation targets that point at renamed IDs from outside the moves.
    if plan.id_map:
        renamed_new_ids = set(plan.id_map.values())
        for r in store.list_requirements():
            if r["id"] in renamed_new_ids:
                continue  # its internal relations were already remapped above
            rels = r.get("relations", [])
            changed = False
            for rel in rels:
                tgt = rel.get("target")
                if tgt in plan.id_map:
                    rel["target"] = plan.id_map[tgt]
                    changed = True
            if changed:
                store.update_requirement(r["id"], {"relations": rels})

    return {"updated": len(updated), "ids": updated, "renames": plan.renames}


def validate_component_parent(components: list[dict], component_id: str, parent_id: str | None) -> str | None:
    """Reason the parent is invalid, or None.

    Takes the component list rather than the store so bulk callers can reuse a
    single scan; ``component_routes._validate_parent`` wraps this for the
    single-item path, where one extra read costs nothing.
    """
    if parent_id is None:
        return None
    if parent_id == component_id:
        return "A component cannot be its own parent"
    by_id = {c["id"]: c for c in components}
    if parent_id not in by_id:
        return f"Parent component not found: {parent_id}"

    seen = {component_id}
    cursor = parent_id
    while cursor is not None:
        if cursor in seen:
            return "Circular parent reference"
        seen.add(cursor)
        cursor = (by_id.get(cursor) or {}).get("parent")
    return None
