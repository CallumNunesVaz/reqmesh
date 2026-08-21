import { describe, it, expect } from 'vitest';
import { computeVisibleNodeIds } from '../src/lib/visibleNodes';

interface ReqLike { id: string; parent: string | null }

function buildIndex(reqs: ReqLike[]) {
  const childrenByParent = new Map<string | null, string[]>();
  for (const r of reqs) {
    const p = r.parent || null;
    if (!childrenByParent.has(p)) childrenByParent.set(p, []);
    childrenByParent.get(p)!.push(r.id);
  }
  const parentIds = new Set<string>();
  for (const r of reqs) { if (r.parent) parentIds.add(r.parent); }
  return { childrenByParent, parentIds };
}

// The pre-indexing O(N²) scan, kept only to prove the indexed version returns
// the identical set. Deliberately the old logic: no cycle guard, full reqs scan
// per node — so it is only used for the acyclic equivalence cases.
function scanVisibleNodeIds(
  reqs: ReqLike[],
  collapsed: Set<string>,
  groupsOnly: Set<string>,
  parentIds: Set<string>,
): Set<string> {
  const visible = new Set<string>();
  function collect(id: string) {
    visible.add(id);
    if (collapsed.has(id)) return;
    const gOnly = groupsOnly.has(id);
    for (const r of reqs) {
      if (r.parent !== id) continue;
      if (gOnly && !parentIds.has(r.id)) continue;
      collect(r.id);
    }
  }
  for (const r of reqs) { if (!r.parent) collect(r.id); }
  if (visible.size === 0) reqs.forEach((r) => visible.add(r.id));
  return visible;
}

function indexed(reqs: ReqLike[], collapsed: Set<string>, groupsOnly: Set<string>) {
  const { childrenByParent, parentIds } = buildIndex(reqs);
  return computeVisibleNodeIds({
    childrenByParent,
    parentIds,
    collapsed,
    groupsOnly,
    allIds: reqs.map((r) => r.id),
  });
}

const TREE: ReqLike[] = [
  { id: 'A', parent: null },
  { id: 'B', parent: 'A' },
  { id: 'C', parent: 'A' },
  { id: 'D', parent: 'B' },
  { id: 'E', parent: 'B' },
  { id: 'F', parent: 'C' },
];

describe('computeVisibleNodeIds', () => {
  it('matches the scan with nothing collapsed', () => {
    const { parentIds } = buildIndex(TREE);
    expect(indexed(TREE, new Set(), new Set()))
      .toEqual(scanVisibleNodeIds(TREE, new Set(), new Set(), parentIds));
    expect(indexed(TREE, new Set(), new Set()))
      .toEqual(new Set(['A', 'B', 'C', 'D', 'E', 'F']));
  });

  it('matches the scan with some collapsed', () => {
    const collapsed = new Set(['B']);
    const { parentIds } = buildIndex(TREE);
    expect(indexed(TREE, collapsed, new Set()))
      .toEqual(scanVisibleNodeIds(TREE, collapsed, new Set(), parentIds));
    // B itself still shows (with its expand button); D and E are hidden.
    expect(indexed(TREE, collapsed, new Set()))
      .toEqual(new Set(['A', 'B', 'C', 'F']));
  });

  it('matches the scan in groups-only mode', () => {
    // A (groups-only) reveals only the children that are parents (B), hiding
    // the leaf child C. B is not groups-only, so its own child D shows.
    const reqs: ReqLike[] = [
      { id: 'A', parent: null },
      { id: 'B', parent: 'A' },
      { id: 'C', parent: 'A' },
      { id: 'D', parent: 'B' },
    ];
    const groupsOnly = new Set(['A']);
    const { parentIds } = buildIndex(reqs);
    expect(indexed(reqs, new Set(), groupsOnly))
      .toEqual(scanVisibleNodeIds(reqs, new Set(), groupsOnly, parentIds));
    expect(indexed(reqs, new Set(), groupsOnly))
      .toEqual(new Set(['A', 'B', 'D']));
  });

  it('matches the scan for an orphan whose parent id does not exist', () => {
    const reqs: ReqLike[] = [
      { id: 'A', parent: null },
      { id: 'B', parent: 'A' },
      { id: 'ORPHAN', parent: 'GHOST' },
    ];
    const { parentIds } = buildIndex(reqs);
    expect(indexed(reqs, new Set(), new Set()))
      .toEqual(scanVisibleNodeIds(reqs, new Set(), new Set(), parentIds));
    // ORPHAN is unreachable from any root and so not visible.
    expect(indexed(reqs, new Set(), new Set()))
      .toEqual(new Set(['A', 'B']));
  });

  it('does not hang on a parent cycle', () => {
    const reqs: ReqLike[] = [
      { id: 'A', parent: 'B' },
      { id: 'B', parent: 'A' },
      { id: 'ROOT', parent: null },
      { id: 'C', parent: 'ROOT' },
    ];
    // If the recursion hangs this test times out rather than returning.
    const result = indexed(reqs, new Set(), new Set());
    expect(result.has('ROOT')).toBe(true);
    expect(result.has('C')).toBe(true);
  });

  it('falls back to every id when there are no roots', () => {
    const reqs: ReqLike[] = [
      { id: 'A', parent: 'B' },
      { id: 'B', parent: 'A' },
    ];
    expect(indexed(reqs, new Set(), new Set()))
      .toEqual(new Set(['A', 'B']));
  });
});
