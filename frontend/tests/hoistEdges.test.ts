import { describe, it, expect } from 'vitest';
import { hoistEdges, type RelationRef } from '../src/lib/hoistEdges';

describe('hoistEdges', () => {
  it('leaves an edge between two visible nodes exactly as-is', () => {
    const visible = new Set(['A', 'B']);
    const parentOf = new Map<string, string | null>([
      ['A', null],
      ['B', null],
    ]);
    const relations: RelationRef[] = [{ source: 'A', target: 'B', type: 'refines' }];
    const out = hoistEdges(relations, visible, parentOf);
    expect(out).toEqual([
      { source: 'A', target: 'B', type: 'refines', hoisted: false, count: 1 },
    ]);
  });

  it('redirects a hidden endpoint to its nearest visible ancestor', () => {
    // G is visible and collapsed; its child X is hidden.
    const visible = new Set(['A', 'G']);
    const parentOf = new Map<string, string | null>([
      ['A', null],
      ['G', null],
      ['X', 'G'],
    ]);
    const relations: RelationRef[] = [{ source: 'A', target: 'X', type: 'depends' }];
    const out = hoistEdges(relations, visible, parentOf);
    expect(out).toEqual([
      { source: 'A', target: 'G', type: 'depends', hoisted: true, count: 1 },
    ]);
  });

  it('drops an edge whose two endpoints hoist to the same ancestor', () => {
    // X and Y are both children of G, which is collapsed (hidden children).
    const visible = new Set(['G']);
    const parentOf = new Map<string, string | null>([
      ['G', null],
      ['X', 'G'],
      ['Y', 'G'],
    ]);
    const relations: RelationRef[] = [{ source: 'X', target: 'Y', type: 'refines' }];
    expect(hoistEdges(relations, visible, parentOf)).toEqual([]);
  });

  it('merges multiple relations collapsing onto the same ancestor pair, with a count', () => {
    const visible = new Set(['A', 'G']);
    const parentOf = new Map<string, string | null>([
      ['A', null],
      ['G', null],
      ['X', 'G'],
      ['Y', 'G'],
    ]);
    const relations: RelationRef[] = [
      { source: 'A', target: 'X', type: 'refines' },
      { source: 'A', target: 'Y', type: 'refines' },
    ];
    const out = hoistEdges(relations, visible, parentOf);
    expect(out).toEqual([
      { source: 'A', target: 'G', type: 'refines', hoisted: true, count: 2 },
    ]);
  });

  it('keeps different relation types on the same ancestor pair as distinct edges', () => {
    const visible = new Set(['A', 'G']);
    const parentOf = new Map<string, string | null>([
      ['A', null],
      ['G', null],
      ['X', 'G'],
      ['Y', 'G'],
    ]);
    const relations: RelationRef[] = [
      { source: 'A', target: 'X', type: 'refines' },
      { source: 'A', target: 'Y', type: 'satisfies' },
    ];
    const out = hoistEdges(relations, visible, parentOf);
    expect(out).toHaveLength(2);
    expect(out.map((e) => e.type).sort()).toEqual(['refines', 'satisfies']);
  });

  it('walks several collapsed ancestors up to the first visible one', () => {
    const visible = new Set(['A', 'ROOT']);
    const parentOf = new Map<string, string | null>([
      ['A', null],
      ['ROOT', null],
      ['MID', 'ROOT'],
      ['LEAF', 'MID'],
    ]);
    const relations: RelationRef[] = [{ source: 'A', target: 'LEAF', type: 'derives' }];
    const out = hoistEdges(relations, visible, parentOf);
    expect(out).toEqual([
      { source: 'A', target: 'ROOT', type: 'derives', hoisted: true, count: 1 },
    ]);
  });

  it('drops edges to ids absent from the tree entirely', () => {
    const visible = new Set(['A']);
    const parentOf = new Map<string, string | null>([['A', null]]);
    const relations: RelationRef[] = [{ source: 'A', target: 'GHOST', type: 'refines' }];
    expect(hoistEdges(relations, visible, parentOf)).toEqual([]);
  });
});
