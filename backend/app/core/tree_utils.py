from __future__ import annotations

from typing import Callable, Optional


def build_flat_tree(
    items: list[dict],
    parent_field: str = "parent",
    children_key: str = "children",
    project: Optional[Callable[[dict], dict]] = None,
) -> list[dict]:
    """Convert a flat list of items with parent references into a nested tree.

    ``project`` maps each item to the node dict emitted for it; when omitted the
    full item is shallow-copied. Callers pass a projection to keep the response
    to a curated field set (and its defaults) rather than leaking whole records.

    Every item is emitted exactly once. Two cases used to silently drop items:

    * an item whose ``parent`` names something that no longer exists (delete a
      parent and its children vanished from the nav while still existing on
      disk — indistinguishable from corruption). Those surface as roots.
    * a parent cycle (A→B→A), which took the whole subtree with it. Cycles are
      broken by tracking what's already been emitted, and whatever is left over
      is appended as roots so nothing disappears.
    """
    ids = {item.get("id") for item in items}
    by_parent: dict[object, list[dict]] = {}
    for item in items:
        parent = item.get(parent_field)
        # An unknown (or missing) parent makes this a root.
        key = parent if parent in ids and parent is not None else None
        by_parent.setdefault(key, []).append(item)

    emitted: set = set()

    def _build(parent_id) -> list[dict]:
        nodes: list[dict] = []
        for item in by_parent.get(parent_id, []):
            item_id = item.get("id")
            if item_id in emitted:
                continue  # cycle, or a duplicate id
            emitted.add(item_id)
            node = project(item) if project else dict(item)
            node[children_key] = _build(item_id)
            nodes.append(node)
        return nodes

    tree = _build(None)

    # Anything unreachable from a root (i.e. inside a parent cycle) is still
    # real data, so surface it rather than letting it disappear.
    for item in items:
        if item.get("id") not in emitted:
            emitted.add(item.get("id"))
            node = project(item) if project else dict(item)
            node[children_key] = _build(item.get("id"))
            tree.append(node)

    return tree
