"""Rename a requirement, rewriting everything that referred to it.

An id is not just a label here: it is the YAML filename, the parent pointer of
every child, and the target of every relation anywhere in the project. Changing
it in one place and not the others is how a project ends up with dangling
traces that no page surfaces.

This is the same rewrite ``services.reparent`` performs when a move re-prefixes
a subtree, narrowed to a single node and made available on its own — which also
means a re-prefixed move is now reversible, where before there was no way back.
"""
from __future__ import annotations

from app.services.history import record_change
from app.services.link_registry import kind_matches, links_into, targets_of
from app.services.naming import get_naming
from app.services.naming import matches_scheme as matches_scheme  # noqa: F401  (re-export: one rule)


def suggest_id(requirements: list[dict], meta: dict, parent_id: str | None) -> str:
    """The default new id: the parent's prefix plus the next free slot.

    Mirrors the shared ``next_id`` generator's scheme so a rename and a create
    agree about what this project's ids look like.
    """
    naming = get_naming(meta, "requirements")
    prefix_len = int(naming.get("prefix_length", 4) or 4)
    separator = naming.get("separator", "")
    suffix_len = int(naming.get("suffix_length", 4) or 4)
    prefix_hint = naming.get("prefix_hint", "REQ")

    prefix = ""
    if parent_id:
        if separator and separator in parent_id:
            prefix = parent_id.split(separator)[0]
        else:
            prefix = parent_id[:prefix_len].upper()
    if not prefix:
        prefix = prefix_hint.upper()

    base = f"{prefix}{separator}" if separator else prefix
    max_suffix = -1
    for r in requirements:
        rid = r.get("id", "")
        if rid.startswith(base):
            rest = rid[len(base):]
            try:
                max_suffix = max(max_suffix, int(rest))
            except ValueError:
                pass
    return f"{base}{str(max_suffix + 1 if max_suffix >= 0 else 1).zfill(suffix_len)}"


def rename_requirement(store, old_id: str, new_id: str, username: str = "") -> dict:
    """Move *old_id* to *new_id* and repoint everything that referenced it.

    Returns ``{"id", "children", "relinked"}`` — the new id, the children whose
    parent pointer moved, and the requirements whose relations were rewritten.
    """
    node = store.get_requirement(old_id)
    if node is None:
        raise ValueError(f"Requirement not found: {old_id}")
    if new_id == old_id:
        return {"id": old_id, "children": [], "relinked": []}
    if store.get_requirement(new_id) is not None:
        raise ValueError(f"A requirement with id {new_id} already exists")

    before = dict(node)
    moved = dict(node)
    moved["id"] = new_id

    # Write the new record before deleting the old one. The reverse order would
    # leave the project with neither if the create failed.
    store.create_requirement(moved)
    store.delete_requirement(old_id)

    children: list[str] = []
    relinked: list[str] = []
    for r in store.list_requirements():
        if r["id"] == new_id:
            continue
        if r.get("parent") == old_id:
            store.update_requirement(r["id"], {"parent": new_id})
            children.append(r["id"])
        rels = r.get("relations", [])
        changed = False
        for rel in rels:
            if rel.get("target") == old_id:
                rel["target"] = new_id
                changed = True
        if changed:
            store.update_requirement(r["id"], {"relations": rels})
            relinked.append(r["id"])

    # The moved record's own relations may point at itself after a cycle of
    # edits; rewrite those too so nothing dangles.
    fresh = store.get_requirement(new_id) or moved
    own = fresh.get("relations", [])
    if any(rel.get("target") == old_id for rel in own):
        for rel in own:
            if rel.get("target") == old_id:
                rel["target"] = new_id
        store.update_requirement(new_id, {"relations": own})

    record_change(store, new_id, "rename", before, store.get_requirement(new_id), username)
    return {"id": new_id, "children": children, "relinked": relinked}


def _rewrite_baseline_snapshots(store, old_id: str, new_id: str) -> None:
    """Repoint a renamed component inside every frozen baseline.

    Live baseline membership carries baseline *names*, so nothing on a component
    changes there. But a frozen baseline's ``component_snapshot`` is keyed by
    component id — and each entry's ``parent`` is a component id — so a rename
    must move the key and repoint any snapshot whose parent was the old id.

    Frozen baselines written by the API ``freeze`` route carry no ``id`` field,
    so ``list_items("baselines")`` (which skips id-less files) would miss them;
    the directory is scanned directly instead.
    """
    baselines_dir = store.root / "baselines"
    if not baselines_dir.exists():
        return
    for f in sorted(baselines_dir.glob("*.yaml")):
        baseline = store._read_yaml(f)
        if not baseline:
            continue
        snapshot = baseline.get("component_snapshot")
        if not isinstance(snapshot, dict):
            continue
        changed = False
        new_snapshot: dict[str, dict] = {}
        for cid, comp in snapshot.items():
            if cid == old_id:
                cid = new_id
                changed = True
            if isinstance(comp, dict) and comp.get("parent") == old_id:
                comp["parent"] = new_id
                changed = True
            new_snapshot[cid] = comp
        if changed:
            baseline["component_snapshot"] = new_snapshot
            store.write_item("baselines", f.stem, baseline)


def rename_component(store, old_id: str, new_id: str, username: str = "") -> dict:
    """Move *old_id* to *new_id* and repoint everything that referenced it.

    Returns ``{"id", "children", "relinked"}`` — the new id, the child
    components whose parent pointer moved, and the ids of records whose
    references were rewritten.

    The inbound references are *derived* from ``link_registry.links_into``
    rather than hand-listed, so a link added to the model later is rewritten
    here without a second edit. Field shapes differ (scalars vs lists vs
    kind-discriminated comments), which the registry's ``many``/``kind_field``
    rows describe.

    Ordering matches ``rename_requirement``: write the new record before
    deleting the old one (the reverse order would leave the project with neither
    if the create failed), and only then rewrite referrers. This is ordered, not
    atomic — a failure midway through the referrer sweep leaves the record at
    the new id with some inbound references still naming the old one (dangling,
    but resolvable), never the old id deleted alongside a half-written new one.
    """
    node = store.get_component(old_id)
    if node is None:
        raise ValueError(f"Component not found: {old_id}")
    if new_id == old_id:
        return {"id": old_id, "children": [], "relinked": []}
    if store.get_component(new_id) is not None:
        raise ValueError(f"A component with id {new_id} already exists")

    before = dict(node)
    moved = dict(node)
    moved["id"] = new_id

    store.create_component(moved)
    store.delete_component(old_id)

    children: list[str] = []
    relinked: list[str] = []
    for link in links_into("components"):
        try:
            items = store.list_items(link.holder)
        except Exception:
            # A collection that does not exist in this project is not an error.
            continue
        for item in items:
            if not kind_matches(item, link):
                continue
            targets = targets_of(item, link)
            if old_id not in targets:
                continue
            new_targets = [new_id if t == old_id else t for t in targets]
            store.update_item(link.holder, item["id"],
                              {link.field: new_targets if link.many else new_targets[0]})
            if link.tree:
                if item["id"] not in children:
                    children.append(item["id"])
            elif item["id"] not in relinked:
                relinked.append(item["id"])

    _rewrite_baseline_snapshots(store, old_id, new_id)

    record_change(store, new_id, "rename", before, store.get_component(new_id), username)
    return {"id": new_id, "children": children, "relinked": relinked}
