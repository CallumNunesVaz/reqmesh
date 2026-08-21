import { describe, it, expect } from 'vitest';
import type { Node } from '@xyflow/react';
import { applySelectionToNodes } from '../src/lib/selectionRestyle';

function node(id: string, data: Record<string, unknown> = {}): Node {
  return { id, type: 'requirementNode', position: { x: 0, y: 0 }, data };
}

describe('applySelectionToNodes', () => {
  it('flags the selected node and dims the unconnected ones', () => {
    const nodes = [node('A'), node('B'), node('C')];
    const out = applySelectionToNodes(nodes, {
      selectedReqId: 'A',
      hasSelection: true,
      connectedIds: new Set(['A', 'B']),
    });
    expect(out[0].data).toMatchObject({ isSelected: true, dimmed: false });
    expect(out[1].data).toMatchObject({ isSelected: false, dimmed: false });
    expect(out[2].data).toMatchObject({ isSelected: false, dimmed: true });
  });

  it('returns unchanged nodes by reference so memo can bail out', () => {
    const a = node('A', { isSelected: false, dimmed: true });
    const b = node('B', { isSelected: false, dimmed: true });
    const out = applySelectionToNodes([a, b], {
      selectedReqId: 'A',
      hasSelection: true,
      connectedIds: new Set(['A']),
    });
    // A flipped (now selected, not dimmed) → new object.
    expect(out[0]).not.toBe(a);
    // B unchanged → same reference.
    expect(out[1]).toBe(b);
  });

  it('returns the same array when nothing changes', () => {
    const a = node('A', { isSelected: true, dimmed: false });
    const b = node('B', { isSelected: false, dimmed: true });
    const nodes = [a, b];
    const out = applySelectionToNodes(nodes, {
      selectedReqId: 'A',
      hasSelection: true,
      connectedIds: new Set(['A']),
    });
    expect(out).toBe(nodes);
  });

  it('selecting an unrelated node leaves a node untouched by reference', () => {
    // Simulates two consecutive selections: B is never connected/selected, so
    // its data object is identical across both passes.
    const b = node('B', { isSelected: false, dimmed: true });
    const first = applySelectionToNodes([node('A'), b], {
      selectedReqId: 'A',
      hasSelection: true,
      connectedIds: new Set(['A']),
    });
    const second = applySelectionToNodes([node('A'), b], {
      selectedReqId: 'A',
      hasSelection: true,
      connectedIds: new Set(['A']),
    });
    expect(second[1]).toBe(first[1]);
    expect(second[1]).toBe(b);
  });

  it('clears dimming and selection when nothing is selected', () => {
    const a = node('A', { isSelected: true, dimmed: false });
    const out = applySelectionToNodes([a], {
      selectedReqId: null,
      hasSelection: false,
      connectedIds: new Set(),
    });
    expect(out[0].data).toMatchObject({ isSelected: false, dimmed: false });
  });
});
