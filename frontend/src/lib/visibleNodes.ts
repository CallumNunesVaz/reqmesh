// Which requirement ids are actually on the canvas given the collapse state.
//
// The graph is a composition tree. A collapsed node is still shown (with its
// expand button) but its descendants are hidden, and in "groups-only" mode a
// node reveals only the children that are themselves parents. This computes the
// visible set by walking the tree through a pre-built `childrenByParent` index
// instead of rescanning the whole requirement list per node — which is what
// made the walk O(N²) — and guards the recursion so a parent cycle in
// hand-editable YAML terminates instead of hanging.

export interface VisibleNodeIdsInput {
  childrenByParent: ReadonlyMap<string | null, readonly string[]>;
  parentIds: ReadonlySet<string>;
  collapsed: ReadonlySet<string>;
  groupsOnly: ReadonlySet<string>;
  allIds: readonly string[];
}

export function computeVisibleNodeIds({
  childrenByParent,
  parentIds,
  collapsed,
  groupsOnly,
  allIds,
}: VisibleNodeIdsInput): Set<string> {
  const visible = new Set<string>();
  const collect = (id: string) => {
    // A collapsed node is still shown (with its expand button); only its
    // descendants are hidden. So add it first, then stop recursing.
    if (visible.has(id)) return; // parent cycle / shared ancestor guard
    visible.add(id);
    if (collapsed.has(id)) return;
    // In groups-only mode, reveal only the children that are parents; leaf
    // children stay hidden until the node is fully expanded.
    const gOnly = groupsOnly.has(id);
    for (const childId of childrenByParent.get(id) || []) {
      if (gOnly && !parentIds.has(childId)) continue;
      collect(childId);
    }
  };
  for (const rootId of childrenByParent.get(null) || []) collect(rootId);
  if (visible.size === 0) for (const id of allIds) visible.add(id);
  return visible;
}
