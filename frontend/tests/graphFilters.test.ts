import { describe, it, expect } from 'vitest';
import {
  effectiveHiddenComponents,
  filterableComponentIds,
  isReqHiddenByComponents,
  isReqHiddenByBaselines,
  migrateLegacyFilterList,
} from '../src/lib/graphFilters';
import type { ComponentNode, SatisfyingComponent } from '../src/lib/graphFilters';

// ── effectiveHiddenComponents ──────────────────────────────────────────────

describe('effectiveHiddenComponents', () => {
  const mk = (id: string, parent?: string | null): ComponentNode => ({ id, parent });

  it('empty hidden set → empty result', () => {
    const comps = [mk('A'), mk('B', 'A'), mk('C', 'B')];
    expect(effectiveHiddenComponents(comps, [])).toEqual(new Set());
  });

  it('hiding a parent includes its children and grandchildren', () => {
    //  A (hidden)
    //  ├── B
    //  │   └── D
    //  └── C
    const comps = [mk('A'), mk('B', 'A'), mk('C', 'A'), mk('D', 'B')];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
    expect(result.has('C')).toBe(true);
    expect(result.has('D')).toBe(true);
  });

  it('hiding a leaf includes only that leaf', () => {
    const comps = [mk('A'), mk('B', 'A'), mk('C', 'B')];
    const result = effectiveHiddenComponents(comps, ['C']);
    expect(result.has('C')).toBe(true);
    expect(result.has('A')).toBe(false);
    expect(result.has('B')).toBe(false);
  });

  it('a sibling subtree is untouched', () => {
    //  A (hidden)
    //  ├── B
    //  └── C
    //  X
    //  └── Y
    const comps = [mk('A'), mk('B', 'A'), mk('C', 'A'), mk('X'), mk('Y', 'X')];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
    expect(result.has('C')).toBe(true);
    expect(result.has('X')).toBe(false);
    expect(result.has('Y')).toBe(false);
  });

  it('an id in hiddenComponents that matches no component still appears in the result', () => {
    const comps = [mk('A')];
    const result = effectiveHiddenComponents(comps, ['GHOST']);
    expect(result.has('GHOST')).toBe(true);
  });

  it('handles parent: null as top-level', () => {
    const comps = [mk('A', null), mk('B', 'A')];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
  });

  it('handles parent undefined as top-level', () => {
    const comps = [mk('A'), mk('B', 'A')];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
  });

  // ── cycle safety ──
  it('two-node cycle terminates with A hidden', () => {
    // A.parent = B, B.parent = A
    const comps = [
      { id: 'A', parent: 'B' },
      { id: 'B', parent: 'A' },
    ];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
    // If we got here, it didn't hang
  });

  it('self-parent cycle terminates', () => {
    const comps = [
      { id: 'A', parent: 'A' },
    ];
    const result = effectiveHiddenComponents(comps, ['A']);
    expect(result.has('A')).toBe(true);
    // If we got here, it didn't hang
  });
});

// ── isReqHiddenByComponents ────────────────────────────────────────────────

describe('isReqHiddenByComponents', () => {
  const mc = (id: string, satisfies?: string[]): SatisfyingComponent => ({ id, satisfies });

  it('requirement satisfied by no component → false, even with non-empty hidden set', () => {
    const comps = [mc('C1', ['R2'])];
    expect(isReqHiddenByComponents('R1', comps, new Set(['C1']))).toBe(false);
  });

  it('satisfied only by hidden components → true', () => {
    const comps = [mc('C1', ['R1'])];
    expect(isReqHiddenByComponents('R1', comps, new Set(['C1']))).toBe(true);
  });

  it('satisfied by one hidden and one visible → false', () => {
    const comps = [mc('C1', ['R1']), mc('C2', ['R1'])];
    // C1 hidden, C2 visible
    expect(isReqHiddenByComponents('R1', comps, new Set(['C1']))).toBe(false);
  });

  it('empty hidden set → false', () => {
    const comps = [mc('C1', ['R1'])];
    expect(isReqHiddenByComponents('R1', comps, new Set())).toBe(false);
  });

  it('a component whose satisfies is undefined does not throw', () => {
    const comps = [mc('C1', ['R1']), { id: 'C2' }];
    expect(isReqHiddenByComponents('R1', comps, new Set(['C1']))).toBe(true);
  });

  it('effective set from parent hide: requirement satisfied only by child of hidden assembly → hidden', () => {
    // Components: A (assembly, hidden), B (child of A, satisfies R1)
    const comps: ComponentNode[] = [
      { id: 'A' },
      { id: 'B', parent: 'A' },
    ];
    const effective = effectiveHiddenComponents(comps, ['A']);
    const satisfying: SatisfyingComponent[] = [
      { id: 'B', satisfies: ['R1'] },
    ];
    expect(isReqHiddenByComponents('R1', satisfying, effective)).toBe(true);
  });
});

// ── isReqHiddenByBaselines ─────────────────────────────────────────────────

describe('isReqHiddenByBaselines', () => {
  it('undefined → false', () => {
    expect(isReqHiddenByBaselines(undefined, ['B1'])).toBe(false);
  });

  it('[] → false', () => {
    expect(isReqHiddenByBaselines([], ['B1'])).toBe(false);
  });

  it('all baselines hidden → true', () => {
    expect(isReqHiddenByBaselines(['B1', 'B2'], ['B1', 'B2'])).toBe(true);
  });

  it('one of two hidden → false', () => {
    expect(isReqHiddenByBaselines(['B1', 'B2'], ['B1'])).toBe(false);
  });
});

// ── migrateLegacyFilterList ────────────────────────────────────────────────

describe('migrateLegacyFilterList', () => {
  it('undefined → []', () => {
    expect(migrateLegacyFilterList(undefined, ['A', 'B', 'C'])).toEqual([]);
  });

  it('[] → [] (the critical case that would otherwise blank the graph)', () => {
    expect(migrateLegacyFilterList([], ['A', 'B', 'C'])).toEqual([]);
  });

  it('partial include-list → complement in allIds order', () => {
    const allIds = ['A', 'B', 'C', 'D'];
    expect(migrateLegacyFilterList(['A', 'C'], allIds)).toEqual(['B', 'D']);
  });

  it('include-list naming every id → []', () => {
    const allIds = ['A', 'B', 'C'];
    expect(migrateLegacyFilterList(['A', 'B', 'C'], allIds)).toEqual([]);
  });

  it('include-list naming an id absent from allIds does not throw', () => {
    const allIds = ['A', 'B'];
    expect(migrateLegacyFilterList(['A', 'X'], allIds)).toEqual(['B']);
  });
});

// ── filterableComponentIds ──────────────────────────────────────────────────

describe('filterableComponentIds', () => {
  type TestComponent = ComponentNode & { satisfies?: string[] };

  it('only components with a non-empty satisfies are returned when nothing is hidden', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: ['R1'] },
      { id: 'C2' }, // satisfies nothing
      { id: 'C3', satisfies: ['R2'] },
    ];
    const result = filterableComponentIds(comps, []);
    expect(result).toEqual(['C1', 'C3']);
  });

  it('a satisfy-nothing component that is in hiddenComponents is returned', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: ['R1'] },
      { id: 'C2' }, // satisfies nothing, but explicitly hidden
    ];
    const result = filterableComponentIds(comps, ['C2']);
    expect(result).toEqual(['C1', 'C2']);
  });

  it('a component that both satisfies and is hidden appears exactly once', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: ['R1'] },
    ];
    const result = filterableComponentIds(comps, ['C1']);
    expect(result).toEqual(['C1']);
  });

  it('the result is sorted ascending', () => {
    const comps: TestComponent[] = [
      { id: 'C3', satisfies: ['R1'] },
      { id: 'C1', satisfies: ['R2'] },
      { id: 'C2', satisfies: ['R3'] },
    ];
    const result = filterableComponentIds(comps, []);
    expect(result).toEqual(['C1', 'C2', 'C3']);
  });

  it('an id in hiddenComponents matching no component is not returned', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: ['R1'] },
    ];
    const result = filterableComponentIds(comps, ['GHOST']);
    expect(result).toEqual(['C1']);
  });

  it('satisfies: undefined is treated as satisfying nothing and does not throw', () => {
    const comps: TestComponent[] = [
      { id: 'C1' }, // satisfies undefined
      { id: 'C2', satisfies: ['R1'] },
    ];
    const result = filterableComponentIds(comps, []);
    expect(result).toEqual(['C2']);
  });

  it('satisfies: [] is treated as satisfying nothing and does not throw', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: [] },
      { id: 'C2', satisfies: ['R1'] },
    ];
    const result = filterableComponentIds(comps, []);
    expect(result).toEqual(['C2']);
  });

  it('empty hiddenComponents does not change the empty satisfies behaviour', () => {
    const comps: TestComponent[] = [
      { id: 'C1', satisfies: [] },
      { id: 'C2', satisfies: undefined },
    ];
    const result = filterableComponentIds(comps, []);
    expect(result).toEqual([]);
  });
});
