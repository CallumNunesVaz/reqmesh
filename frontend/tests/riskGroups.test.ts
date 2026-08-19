import { describe, it, expect } from 'vitest';
import { subtreeIds, riskInGroup, flattenTree, type TreeNode } from '../src/lib/riskGroups';
import type { Risk } from '../src/api/client';

function mkRisk(overrides: Partial<Risk> = {}): Risk {
  return {
    id: 'RSK-1',
    title: '',
    failure_mode: '',
    effect: '',
    cause: '',
    description: '',
    severity: 'medium',
    likelihood: 'possible',
    probability: '',
    impact: '',
    mitigation: '',
    detection: '',
    linked_requirements: [],
    mitigating_requirements: [],
    linked_components: [],
    mitigating_components: [],
    status: 'open',
    created: '',
    modified: '',
    ...overrides,
  };
}

describe('subtreeIds', () => {
  //        root
  //        /   \
  //       a     d
  //      / \
  //     b   c
  const tree: TreeNode[] = [
    {
      id: 'root',
      children: [
        { id: 'a', children: [{ id: 'b', children: [] }, { id: 'c', children: [] }] },
        { id: 'd', children: [] },
      ],
    },
  ];

  it('returns a node and all of its descendants', () => {
    expect(subtreeIds(tree, 'a')).toEqual(new Set(['a', 'b', 'c']));
    expect(subtreeIds(tree, 'root')).toEqual(new Set(['root', 'a', 'b', 'c', 'd']));
  });

  it('returns just itself for a leaf', () => {
    expect(subtreeIds(tree, 'b')).toEqual(new Set(['b']));
  });

  it('returns empty for an unknown id', () => {
    expect(subtreeIds(tree, 'nope')).toEqual(new Set());
  });
});

describe('riskInGroup', () => {
  const subtree = new Set(['group', 'child', 'grandchild']);

  it('matches via linked_components', () => {
    expect(riskInGroup(mkRisk({ linked_components: ['child'] }), subtree)).toBe(true);
  });

  it('matches via mitigating_components', () => {
    expect(riskInGroup(mkRisk({ mitigating_components: ['grandchild'] }), subtree)).toBe(true);
  });

  it('matches via linked_requirements', () => {
    expect(riskInGroup(mkRisk({ linked_requirements: ['child'] }), subtree)).toBe(true);
  });

  it('matches via mitigating_requirements', () => {
    expect(riskInGroup(mkRisk({ mitigating_requirements: ['grandchild'] }), subtree)).toBe(true);
  });

  it('does not match a risk linked only outside the subtree', () => {
    expect(riskInGroup(mkRisk({ linked_components: ['outside'] }), subtree)).toBe(false);
    expect(riskInGroup(mkRisk(), subtree)).toBe(false);
  });
});

describe('flattenTree', () => {
  it('emits every node in depth-first order with a depth', () => {
    const nodes = [
      { id: 'r', name: 'Root', children: [{ id: 'c', name: 'Child', children: [] }] },
    ];
    expect(flattenTree(nodes)).toEqual([
      { id: 'r', name: 'Root', depth: 0 },
      { id: 'c', name: 'Child', depth: 1 },
    ]);
  });
});
