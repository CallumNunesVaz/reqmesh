// Redirecting hidden edge endpoints to their nearest visible ancestor.
//
// When a group is collapsed its descendants leave the graph, and with them
// every relationship line into or out of them — which makes a collapsed graph
// quietly misleading: the relationship still exists, it just stops being
// drawn. This module redraws each such edge to the nearest *visible* ancestor
// of the hidden endpoint, so the line lands on the group standing in for what
// is inside it.

export interface RelationRef {
  source: string;
  target: string;
  type: string;
}

export interface HoistedEdge {
  source: string;
  target: string;
  type: string;
  /** True when either endpoint was redirected to a visible ancestor. */
  hoisted: boolean;
  /** Number of raw relations merged into this edge (>= 1). */
  count: number;
}

/**
 * Given the visible set, a parent map and the raw relations, produce the edge
 * list to draw. A relation whose endpoint is hidden is redirected to its
 * nearest visible ancestor; a relation whose two endpoints hoist to the same
 * ancestor is internal to that group and is dropped rather than drawn as a
 * self-loop. Relations between two visible nodes pass through untouched.
 * Relations that collapse onto the same (source, target, type) triple are
 * merged into one edge carrying a count.
 */
export function hoistEdges(
  relations: RelationRef[],
  visible: Set<string>,
  parentOf: Map<string, string | null>,
): HoistedEdge[] {
  const resolve = (id: string): string | null => {
    let cur: string | null = id;
    const guard = new Set<string>();
    while (cur !== null && !visible.has(cur)) {
      // A malformed tree should not turn this into an infinite walk.
      if (guard.has(cur)) return null;
      guard.add(cur);
      cur = parentOf.get(cur) ?? null;
    }
    return cur;
  };

  const merged = new Map<string, HoistedEdge>();
  for (const rel of relations) {
    const source = resolve(rel.source);
    const target = resolve(rel.target);
    if (source == null || target == null) continue;
    if (source === target) continue;
    const key = `${source}\u0000${target}\u0000${rel.type}`;
    const existing = merged.get(key);
    if (existing) {
      existing.count += 1;
      existing.hoisted = existing.hoisted || source !== rel.source || target !== rel.target;
      continue;
    }
    merged.set(key, {
      source,
      target,
      type: rel.type,
      hoisted: source !== rel.source || target !== rel.target,
      count: 1,
    });
  }
  return [...merged.values()];
}
