import { describe, it, expect } from 'vitest';
import { nextAnchor, nextSelection } from '../src/lib/rangeSelection';

const IDS = ['A', 'B', 'C', 'D', 'E'];

/** Replay a sequence of clicks the way the hook does, and return the result. */
function clicks(
  orderedIds: readonly string[],
  seq: [string, { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }?][],
): string[] {
  let selected = new Set<string>();
  let anchor: string | null = null;
  for (const [id, mods] of seq) {
    selected = nextSelection(orderedIds, selected, id, anchor, mods);
    anchor = nextAnchor(id, anchor, mods);
  }
  return [...selected].sort();
}

describe('rangeSelection', () => {
  it('toggles a single row on a plain click', () => {
    expect(clicks(IDS, [['B']])).toEqual(['B']);
    expect(clicks(IDS, [['B'], ['B']])).toEqual([]);
  });

  it('keeps earlier selections on a plain click — these are checkboxes', () => {
    expect(clicks(IDS, [['A'], ['D']])).toEqual(['A', 'D']);
  });

  it('selects the inclusive range on shift+click', () => {
    expect(clicks(IDS, [['B'], ['D', { shiftKey: true }]])).toEqual(['B', 'C', 'D']);
  });

  it('ranges backwards as well as forwards', () => {
    expect(clicks(IDS, [['D'], ['B', { shiftKey: true }]])).toEqual(['B', 'C', 'D']);
  });

  it('sweeps a range off when the clicked row was already selected', () => {
    // A..E selected, then shift-click E again (still selected) clears the range.
    expect(clicks(IDS, [
      ['A'], ['E', { shiftKey: true }], ['E', { shiftKey: true }],
    ])).toEqual([]);
  });

  it('does not move the anchor on shift+click, so ranges re-sweep', () => {
    expect(clicks(IDS, [
      ['A'], ['C', { shiftKey: true }], ['E', { shiftKey: true }],
    ])).toEqual(['A', 'B', 'C', 'D', 'E']);
  });

  it('treats ctrl and cmd as a plain toggle', () => {
    expect(clicks(IDS, [['A'], ['C', { ctrlKey: true }]])).toEqual(['A', 'C']);
    expect(clicks(IDS, [['A'], ['C', { ctrlKey: true }], ['C', { metaKey: true }]])).toEqual(['A']);
  });

  it('falls back to a toggle when the anchor is no longer visible', () => {
    // The anchor was clicked while visible, then filtered out of the list.
    const selected = nextSelection(IDS, new Set(['X']), 'C', 'X', { shiftKey: true });
    expect([...selected].sort()).toEqual(['C', 'X']);
  });

  it('shift+click with no anchor is a plain toggle', () => {
    expect(clicks(IDS, [['C', { shiftKey: true }]])).toEqual(['C']);
  });

  it('shift+click on the anchor itself just toggles it', () => {
    expect(clicks(IDS, [['B'], ['B', { shiftKey: true }]])).toEqual([]);
  });

  it('keeps the anchor on shift, moves it otherwise', () => {
    expect(nextAnchor('C', 'A', { shiftKey: true })).toBe('A');
    expect(nextAnchor('C', 'A', {})).toBe('C');
    expect(nextAnchor('C', 'A', { ctrlKey: true })).toBe('C');
  });
});
