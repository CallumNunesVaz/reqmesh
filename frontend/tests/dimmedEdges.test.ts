import { describe, it, expect } from 'vitest';
import type { Edge } from '@xyflow/react';
import { dimEdges, type EdgeDimEntry, type EdgeDimOptions } from '../src/lib/dimmedEdges';

function edge(id: string, source: string, target: string): Edge {
  return {
    id,
    source,
    target,
    type: 'floating',
    data: { color: '#000', label: 'refines' },
    style: { stroke: '#000', strokeWidth: 1.2, strokeDasharray: 'none', opacity: 0.45 },
  };
}

function opts(connectedIds: string[]): EdgeDimOptions {
  return {
    hasSelection: true,
    connectedIds: new Set(connectedIds),
    focusDist: new Map(),
    linkDir: 'both',
    showAllLinks: false,
    perfMode: false,
    derivationActive: true,
  };
}

describe('dimEdges', () => {
  const e1 = edge('e1', 'A', 'B');
  const e2 = edge('e2', 'B', 'C');
  const e3 = edge('e3', 'D', 'E');

  it('returns referentially identical objects for edges whose state did not change', () => {
    const first = dimEdges([e1, e2, e3], new Map<string, EdgeDimEntry>(), opts(['A', 'B']));
    const second = dimEdges([e1, e2, e3], first.prev, opts(['B', 'C']));

    // e3 is dimmed in both passes (neither endpoint ever highlighted).
    expect(second.edges[2]).toBe(first.edges[2]);
    // e1 went connected → dimmed, e2 went dimmed → connected.
    expect(second.edges[0]).not.toBe(first.edges[0]);
    expect(second.edges[1]).not.toBe(first.edges[1]);
  });

  it('preserves identity across more than two consecutive selections', () => {
    const pass1 = dimEdges([e1, e2, e3], new Map(), opts(['A', 'B']));
    const pass2 = dimEdges([e1, e2, e3], pass1.prev, opts(['B', 'C']));
    const pass3 = dimEdges([e1, e2, e3], pass2.prev, opts(['A', 'B']));

    // e3 unchanged the whole way through.
    expect(pass3.edges[2]).toBe(pass2.edges[2]);
    expect(pass3.edges[2]).toBe(pass1.edges[2]);
    // e1 flips back to connected, so it gets a new object.
    expect(pass3.edges[0]).not.toBe(pass2.edges[0]);
  });

  it('does not reuse a stale object when the underlying edge changes', () => {
    const pass1 = dimEdges([e1], new Map(), opts(['A', 'B']));
    // Same id, different style (new object) — must not reuse pass1's object.
    const e1b = { ...e1, style: { ...e1.style, stroke: '#f00' } };
    const pass2 = dimEdges([e1b], pass1.prev, opts(['A', 'B']));
    expect(pass2.edges[0]).not.toBe(pass1.edges[0]);
    expect((pass2.edges[0].style as any).stroke).toBe('#f00');
  });

  it('applies the dimmed/connected styling to the computed values', () => {
    const res = dimEdges([e1, e2], new Map(), opts(['A', 'B']));
    // e1 connected, e2 dimmed.
    expect((res.edges[0].style as any).opacity).toBeGreaterThanOrEqual(0.9);
    expect((res.edges[0].data as any).showLabel).toBe(true);
    expect((res.edges[1].style as any).opacity).toBe(0.04);
    expect((res.edges[1].data as any).showLabel).toBe(false);
  });

  it('returns the input edges untouched when there is no selection', () => {
    const edges = [e1, e2, e3];
    const res = dimEdges(edges, new Map(), { ...opts([]), hasSelection: false });
    expect(res.edges).toBe(edges);
  });
});

describe('dimEdges — hoisted badge dim state', () => {
  const connected = edge('c', 'A', 'B');
  const unrelated = edge('u', 'D', 'E');

  it('marks an unconnected edge dimmed so its ×N badge can recede', () => {
    const { edges } = dimEdges([connected, unrelated], new Map<string, EdgeDimEntry>(), opts(['A', 'B']));
    expect((edges[0].data as Record<string, unknown>).dimmed).toBe(false);
    expect((edges[1].data as Record<string, unknown>).dimmed).toBe(true);
  });

  it('leaves `dimmed` absent when nothing is selected, so the badge stays full strength', () => {
    // The badge is deliberately visible with no selection — it says "this line
    // is really N relations". Regression guard for the bug where it also stayed
    // full strength while the rest of the canvas faded out.
    const { edges } = dimEdges([connected, unrelated], new Map<string, EdgeDimEntry>(), {
      ...opts([]),
      hasSelection: false,
    });
    for (const e of edges) {
      expect((e.data as Record<string, unknown>)?.dimmed).toBeUndefined();
    }
  });

  it('keeps `dimmed` the inverse of `showLabel` while a selection is active', () => {
    const { edges } = dimEdges([connected, unrelated], new Map<string, EdgeDimEntry>(), opts(['A', 'B']));
    for (const e of edges) {
      const d = e.data as Record<string, unknown>;
      expect(d.dimmed).toBe(!d.showLabel);
    }
  });
});
