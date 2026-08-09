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

import re

from app.services.history import record_change


def suggest_id(requirements: list[dict], meta: dict, parent_id: str | None) -> str:
    """The default new id: the parent's prefix plus the next free slot.

    Mirrors the ``next-uid`` route's scheme so a rename and a create agree about
    what this project's ids look like.
    """
    naming = (meta.get("naming") or {}).get("requirements") or {}
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


def matches_scheme(new_id: str, meta: dict) -> str | None:
    """Reason *new_id* does not fit the project's naming scheme, or None.

    Deliberately permissive: the scheme describes what generated ids look like,
    not a law every hand-written id must obey — projects migrating from another
    tool carry legacy ids that would never round-trip through a strict check.
    Only the shape that would break the suffix arithmetic is refused.
    """
    naming = (meta.get("naming") or {}).get("requirements") or {}
    separator = naming.get("separator", "")
    suffix_type = naming.get("suffix_type", "numeric")

    if separator and separator not in new_id:
        return f"Expected '{separator}' between the prefix and the number"

    tail = new_id.split(separator)[-1] if separator else new_id
    if suffix_type == "numeric":
        digits = re.search(r"(\d+)$", tail)
        if not digits:
            return "Expected the id to end in a number"
    return None


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
