import { describe, it, expect } from 'vitest';
import {
  branchIds, subtreeOf, validParents, isValidDrop, dragPayload, topLevelOf,
  depthFirstOrder,
} from '../src/lib/hierarchy';

/** A → B → C, plus an unrelated X. */
const tree = [
  { id: 'A', parent: null },
  { id: 'B', parent: 'A' },
  { id: 'C', parent: 'B' },
  { id: 'X', parent: null },
];

describe('branchIds', () => {
  it('collects a node and everything beneath it', () => {
    expect([...branchIds(tree, 'A')].sort()).toEqual(['A', 'B', 'C']);
    expect([...branchIds(tree, 'B')].sort()).toEqual(['B', 'C']);
    expect([...branchIds(tree, 'C')]).toEqual(['C']);
  });

  it('terminates on a corrupt parent cycle rather than recursing forever', () => {
    // The YAML store is hand-editable and arrives by git pull, so this shape
    // can genuinely exist on disk.
    const cyclic = [
      { id: 'P', parent: 'Q' },
      { id: 'Q', parent: 'P' },
    ];
    expect([...branchIds(cyclic, 'P')].sort()).toEqual(['P', 'Q']);
  });

  it('returns just the root when the id is unknown', () => {
    expect([...branchIds(tree, 'NOPE')]).toEqual(['NOPE']);
  });
});

describe('subtreeOf', () => {
  it('unions several branches', () => {
    expect([...subtreeOf(tree, ['B', 'X'])].sort()).toEqual(['B', 'C', 'X']);
  });

  it('is empty for no roots', () => {
    expect([...subtreeOf(tree, [])]).toEqual([]);
  });
});

describe('validParents', () => {
  it('excludes the moving row and its whole branch', () => {
    expect(validParents(tree, ['B']).map((n) => n.id)).toEqual(['A', 'X']);
  });

  it('excludes every moving branch for a multi-row move', () => {
    expect(validParents(tree, ['B', 'X']).map((n) => n.id)).toEqual(['A']);
  });

  it('sorts by id, matching the tree display order', () => {
    const shuffled = [
      { id: 'Z', parent: null },
      { id: 'M', parent: null },
      { id: 'A', parent: null },
    ];
    expect(validParents(shuffled, []).map((n) => n.id)).toEqual(['A', 'M', 'Z']);
  });
});

describe('isValidDrop', () => {
  it('refuses dropping a row onto itself', () => {
    expect(isValidDrop(tree, ['B'], 'B')).toBe(false);
  });

  it('refuses dropping a row into its own descendant', () => {
    expect(isValidDrop(tree, ['A'], 'C')).toBe(false);
  });

  it('allows an unrelated target', () => {
    expect(isValidDrop(tree, ['B'], 'X')).toBe(true);
  });

  it('refuses a drop onto the row that is already the parent', () => {
    expect(isValidDrop(tree, ['B'], 'A')).toBe(false);
  });

  it('allows make-top-level only when something is not already top level', () => {
    expect(isValidDrop(tree, ['B'], null)).toBe(true);
    expect(isValidDrop(tree, ['X'], null)).toBe(false);
  });

  it('refuses an empty move', () => {
    expect(isValidDrop(tree, [], 'A')).toBe(false);
  });
});

describe('dragPayload', () => {
  it('moves the whole selection when the dragged row is part of it', () => {
    expect(dragPayload(new Set(['A', 'B']), 'A').sort()).toEqual(['A', 'B']);
  });

  it('moves only the dragged row when it is not selected', () => {
    expect(dragPayload(new Set(['A', 'B']), 'X')).toEqual(['X']);
  });

  it('moves only the dragged row when nothing is selected', () => {
    expect(dragPayload(new Set(), 'X')).toEqual(['X']);
  });
});

describe('topLevelOf', () => {
  it('drops rows whose ancestor is also moving, so a parent moves once', () => {
    expect(topLevelOf(tree, ['A', 'B', 'C'])).toEqual(['A']);
  });

  it('keeps siblings that are independent', () => {
    expect(topLevelOf(tree, ['B', 'X'])).toEqual(['B', 'X']);
  });

  it('terminates on a corrupt cycle', () => {
    const cyclic = [
      { id: 'P', parent: 'Q' },
      { id: 'Q', parent: 'P' },
    ];
    expect(topLevelOf(cyclic, ['P']).length).toBeLessThanOrEqual(1);
  });
});

describe('depthFirstOrder', () => {
  it('walks a three-level tree parents-first with correct depths', () => {
    const three = [
      { id: 'C', parent: 'B' },
      { id: 'A', parent: null },
      { id: 'B', parent: 'A' },
      { id: 'D', parent: 'A' },
    ];
    // Input is shuffled; the order comes from the tree, not the array.
    expect(depthFirstOrder(three)).toEqual([
      { id: 'A', depth: 0 },
      { id: 'B', depth: 1 },
      { id: 'C', depth: 2 },
      { id: 'D', depth: 1 },
    ]);
  });

  it('shows an orphan whose parent is not present at depth 0', () => {
    const orphaned = [
      { id: 'A', parent: null },
      { id: 'O', parent: 'MISSING' },
    ];
    expect(depthFirstOrder(orphaned)).toEqual([
      { id: 'A', depth: 0 },
      { id: 'O', depth: 0 },
    ]);
  });

  it('terminates on a parent cycle and still emits every member', () => {
    const cyclic = [
      { id: 'P', parent: 'Q' },
      { id: 'Q', parent: 'P' },
    ];
    const result = depthFirstOrder(cyclic);
    expect(result.map((n) => n.id).sort()).toEqual(['P', 'Q']);
    expect(result[0].depth).toBe(0);
  });
});
