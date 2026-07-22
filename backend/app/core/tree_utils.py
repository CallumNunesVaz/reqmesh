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
    """
    def _build(parent_id: str | None) -> list[dict]:
        children: list[dict] = []
        for item in items:
            if item.get(parent_field) == parent_id:
                node = project(item) if project else dict(item)
                node[children_key] = _build(item.get("id"))
                children.append(node)
        return children
    return _build(None)
