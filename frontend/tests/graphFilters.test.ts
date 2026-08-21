import { describe, it, expect } from 'vitest';
import {
  hiddenAncestors,
  effectiveHiddenComponents,
  filterableComponentIds,
  isReqHiddenByComponents,
  isReqHiddenByComponentsIndexed,
  buildSatisfyingIndex,
  isReqHiddenByBaselines,
  migrateLegacyFilterList,
  requirementsRevealed,
  pruneUnknownIds,
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

// ── buildSatisfyingIndex + indexed lookup ──────────────────────────────────

describe('buildSatisfyingIndex / isReqHiddenByComponentsIndexed', () => {
  const mc = (id: string, satisfies?: string[]): SatisfyingComponent => ({ id, satisfies });

  // Every case the indexed lookup must agree with the scanning implementation.
  const CASES: { name: string; comps: SatisfyingComponent[]; reqId: string; hidden: string[] }[] = [
    { name: 'no satisfying component', comps: [mc('C1', ['R2'])], reqId: 'R1', hidden: ['C1'] },
    { name: 'one hidden', comps: [mc('C1', ['R1'])], reqId: 'R1', hidden: ['C1'] },
    { name: 'one visible one hidden', comps: [mc('C1', ['R1']), mc('C2', ['R1'])], reqId: 'R1', hidden: ['C1'] },
    { name: 'all hidden', comps: [mc('C1', ['R1']), mc('C2', ['R1'])], reqId: 'R1', hidden: ['C1', 'C2'] },
    { name: 'empty hidden set', comps: [mc('C1', ['R1'])], reqId: 'R1', hidden: [] },
    { name: 'component without satisfies', comps: [mc('C1', ['R1']), { id: 'C2' }], reqId: 'R1', hidden: ['C1'] },
  ];

  for (const c of CASES) {
    it(`agrees with the scan for: ${c.name}`, () => {
      const effective = new Set(c.hidden);
      const indexed = isReqHiddenByComponentsIndexed(
        buildSatisfyingIndex(c.comps), c.reqId, effective);
      expect(indexed).toBe(isReqHiddenByComponents(c.reqId, c.comps, effective));
    });
  }

  it('indexes each requirement to its satisfying components', () => {
    const index = buildSatisfyingIndex([
      mc('C1', ['R1', 'R2']),
      mc('C2', ['R2']),
      mc('C3'),
    ]);
    expect(index.get('R1')).toEqual(['C1']);
    expect(index.get('R2')).toEqual(['C1', 'C2']);
    expect(index.get('R3')).toBeUndefined();
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

// ── requirementsRevealed ────────────────────────────────────────────────────

describe('requirementsRevealed', () => {
  type TestComp = ComponentNode & SatisfyingComponent;

  it('revealing a component whose requirement is also satisfied by a still-hidden component reveals that requirement', () => {
    // C1 (hidden) satisfies R1; C2 (also hidden) also satisfies R1.
    // Revealing only C1: R1 is still hidden by C2, so nothing revealed.
    // Wait — the spec says the opposite. Let me re-read.
    // "Revealing a component whose requirement is also satisfied by a still-hidden
    //  component reveals that requirement."
    // Hmm, but isReqHiddenByComponents hides only when EVERY satisfying component
    // is hidden. If C1 is revealed but C2 is still hidden, R1 is visible (one
    // visible component is enough). So revealing C1 should reveal R1.
    //
    // Previously: C1 hidden, C2 hidden → R1 hidden
    // Now: C1 visible, C2 hidden → R1 visible
    // So R1 IS revealed. ✓
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R1'] },
      { id: 'C2', satisfies: ['R1'] },
    ];
    const result = requirementsRevealed(comps, ['C1', 'C2'], ['C2'], ['R1']);
    expect(result).toEqual(['R1']);
  });

  it('revealing one of two satisfying components where the other was already visible reveals nothing', () => {
    // C1 visible, C2 hidden → R1 is already visible (satisfied by C1).
    // Hiding C2 changes nothing because C1 still satisfies R1.
    // So revealing C2 (which was hidden) — wait, this is about "revealing one
    // of two satisfying components where the other was already visible".
    // Prev: C2 hidden, C1 visible → R1 visible
    // Next: nothing hidden → R1 still visible
    // No reveal. ✓
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R1'] },
      { id: 'C2', satisfies: ['R1'] },
    ];
    const result = requirementsRevealed(comps, ['C2'], [], ['R1']);
    expect(result).toEqual([]);
  });

  it('revealing a parent reveals requirements satisfied only by its descendants', () => {
    // A (assembly, hidden) → B (child of A, satisfies ['R1'])
    // Prev: A hidden → B (descendant) is in effectiveHidden → R1 hidden
    // Next: nothing hidden → R1 visible
    const comps: TestComp[] = [
      { id: 'A' },
      { id: 'B', parent: 'A', satisfies: ['R1'] },
    ];
    const result = requirementsRevealed(comps, ['A'], [], ['R1']);
    expect(result).toEqual(['R1']);
  });

  it('a hide returns an empty array', () => {
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R1'] },
    ];
    // Hiding C1: requirements go from visible to hidden, not revealed.
    const result = requirementsRevealed(comps, [], ['C1'], ['R1']);
    expect(result).toEqual([]);
  });

  it('a requirement satisfied by no component is never returned', () => {
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R2'] },
    ];
    // R1 is satisfied by no component → never hidden → revealing changes nothing.
    const result = requirementsRevealed(comps, ['C1'], [], ['R1', 'R2']);
    expect(result).toEqual(['R2']);
  });

  it('results are sorted, with no duplicates when several components are revealed at once', () => {
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R3', 'R1'] },
      { id: 'C2', satisfies: ['R2', 'R3'] },
    ];
    // Both hidden → both revealed. R3 appears in both — should only be listed once.
    const result = requirementsRevealed(comps, ['C1', 'C2'], [], ['R1', 'R2', 'R3']);
    expect(result).toEqual(['R1', 'R2', 'R3']);
  });

  it('empty hidden lists both before and after return empty', () => {
    const comps: TestComp[] = [
      { id: 'C1', satisfies: ['R1'] },
    ];
    expect(requirementsRevealed(comps, [], [], ['R1'])).toEqual([]);
  });
});

// ── pruneUnknownIds ─────────────────────────────────────────────────────────

describe('pruneUnknownIds', () => {
  it('drops ids not in the known list', () => {
    const result = pruneUnknownIds(['A', 'B', 'GHOST'], ['A', 'B']);
    expect(result).toEqual(['A', 'B']);
  });

  it('returns the same array instance when everything is known', () => {
    const hidden = ['A', 'B'];
    const result = pruneUnknownIds(hidden, ['A', 'B', 'C']);
    expect(result).toBe(hidden); // identity check — no-loop guarantee
  });

  it('an empty hidden list returns the same empty instance', () => {
    const hidden: string[] = [];
    const result = pruneUnknownIds(hidden, ['A', 'B']);
    expect(result).toBe(hidden); // identity check
  });

  it('returns the same empty array instance when known list is also empty', () => {
    const hidden: string[] = [];
    const result = pruneUnknownIds(hidden, []);
    expect(result).toBe(hidden);
  });

  it('all ids unknown returns an empty array', () => {
    const result = pruneUnknownIds(['X', 'Y'], ['A', 'B']);
    expect(result).toEqual([]);
  });
});

describe('hiddenAncestors', () => {
  const tree = [
    { id: 'ROOT' },
    { id: 'MID', parent: 'ROOT' },
    { id: 'LEAF', parent: 'MID' },
  ];

  it('returns the hidden ancestors nearest first', () => {
    expect(hiddenAncestors(tree, ['ROOT', 'MID'], 'LEAF')).toEqual(['MID', 'ROOT']);
  });

  it('ignores ancestors that are not hidden', () => {
    expect(hiddenAncestors(tree, ['ROOT'], 'LEAF')).toEqual(['ROOT']);
  });

  it('is empty when nothing above is hidden', () => {
    expect(hiddenAncestors(tree, ['LEAF'], 'LEAF')).toEqual([]);
  });

  it('terminates on a parent cycle', () => {
    const cyclic = [{ id: 'A', parent: 'B' }, { id: 'B', parent: 'A' }];
    expect(hiddenAncestors(cyclic, ['B'], 'A')).toEqual(['B']);
  });

  it('terminates on a self-parent', () => {
    expect(hiddenAncestors([{ id: 'S', parent: 'S' }], ['S'], 'S')).toEqual([]);
  });
});
