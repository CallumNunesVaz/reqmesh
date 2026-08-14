import { describe, it, expect } from 'vitest';
import { rollupQuantities } from '../src/lib/quantityRollup';

const q = (id: string, parent: string | null = null, quantity = 1) => ({ id, parent, quantity });

describe('rollupQuantities', () => {
  it('multiplies own quantity by every ancestor up to the root', () => {
    // A (3×) → B (5×) → C (2×): A is 3×, B is 15×, C is 30×.
    const comps = [q('A', null, 3), q('B', 'A', 5), q('C', 'B', 2)];
    const r = rollupQuantities(comps);
    expect(r.get('A')).toBe(3);
    expect(r.get('B')).toBe(15);
    expect(r.get('C')).toBe(30);
  });

  it('a parent cycle terminates rather than hanging', () => {
    // A → B → A. The walk revisits A and stops there, so B folds its own
    // quantity and A folds B once — finite and deterministic, never a hang.
    const comps = [q('A', 'B', 2), q('B', 'A', 3)];
    const r = rollupQuantities(comps);
    expect([...r.keys()].sort()).toEqual(['A', 'B']);
    expect(r.get('B')).toBe(3);
    expect(r.get('A')).toBe(6);
  });

  it('a self-parent terminates rather than hanging', () => {
    const comps = [q('A', 'A', 4)];
    const r = rollupQuantities(comps);
    expect(r.get('A')).toBe(4);
  });

  it('a parent pointing at nothing terminates the walk', () => {
    // A's parent does not exist, so A is its own root (2×), and B under it is 6×.
    const comps = [q('A', 'MISSING', 2), q('B', 'A', 3)];
    const r = rollupQuantities(comps);
    expect(r.get('A')).toBe(2);
    expect(r.get('B')).toBe(6);
  });

  it('treats zero, missing and negative quantity as 1, not 0', () => {
    // A (3×) → Z (0) → M (missing) → N (−4): every degenerate quantity folds as
    // 1, so the whole subtree is 3× and never silently annihilated to 0.
    const comps = [
      q('A', null, 3),
      q('Z', 'A', 0),
      { id: 'M', parent: 'Z', quantity: undefined as unknown as number },
      q('N', 'M', -4),
    ];
    const r = rollupQuantities(comps);
    expect(r.get('Z')).toBe(3);
    expect(r.get('M')).toBe(3);
    expect(r.get('N')).toBe(3);
  });

  it('a forest with multiple roots rolls each one up independently', () => {
    const comps = [
      q('A', null, 2),
      q('A1', 'A', 3),
      q('B', null, 5),
      q('B1', 'B', 7),
    ];
    const r = rollupQuantities(comps);
    expect(r.get('A')).toBe(2);
    expect(r.get('A1')).toBe(6);
    expect(r.get('B')).toBe(5);
    expect(r.get('B1')).toBe(35);
  });
});
