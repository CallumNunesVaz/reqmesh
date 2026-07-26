import { describe, it, expect } from 'vitest';
import { removeTraceLink } from '../src/lib/traceLinks';
import type { TraceLink } from '../src/api/client';

const mk = (source: string, target: string, type = 'satisfies'): TraceLink =>
  ({ source, target, type });

describe('removeTraceLink', () => {
  it('removes the clicked link and leaves the rest untouched', () => {
    const links = [mk('A', '1'), mk('B', '2'), mk('C', '3')];
    const next = removeTraceLink(links, links[1]);
    expect(next).toEqual([links[0], links[2]]);
    expect(links).toHaveLength(3); // input not mutated
  });

  it('removes the right link when the view is filtered (the BUG-3 regression)', () => {
    // The table renders a filtered subset but used to hand back the *view's*
    // row index, which indexes a different element of the full array.
    const links = [
      mk('A', '1', 'satisfies'),
      mk('B', '2', 'satisfies'),
      mk('C', '3', 'verifies'),
      mk('D', '4', 'satisfies'),
      mk('E', '5', 'verifies'),
    ];
    const filtered = links.filter((l) => l.type === 'verifies'); // [C->3, E->5]
    const clicked = filtered[1]; // the user clicks E->5

    // What the old index-based code did: filtered index 1 -> links[1] = B->2.
    const byIndex = links.filter((_, i) => i !== 1);
    expect(byIndex).toContain(clicked);           // the clicked row survived
    expect(byIndex).not.toContain(links[1]);      // an unrelated link died

    // Identity-based removal deletes exactly what was clicked.
    const next = removeTraceLink(links, clicked);
    expect(next).not.toContain(clicked);
    expect(next).toContain(links[1]);
    expect(next.map((l) => l.target)).toEqual(['1', '2', '3', '4']);
  });

  it('removes only one row when a duplicate pair exists', () => {
    const dupA = mk('A', '1');
    const dupB = mk('A', '1'); // same values, different object
    const links = [dupA, dupB];
    const next = removeTraceLink(links, dupB);
    expect(next).toEqual([dupA]);
    expect(next[0]).toBe(dupA);
  });

  it('returns the original array when the link is not present', () => {
    const links = [mk('A', '1')];
    expect(removeTraceLink(links, mk('A', '1'))).toBe(links); // equal but not identical
    expect(removeTraceLink(links, mk('Z', '9'))).toBe(links);
  });
});
