import { describe, it, expect } from 'vitest';
import { layoutNodeHeight } from '../src/components/GraphPane';

describe('layoutNodeHeight', () => {
  it('returns 118 for the empty case', () => {
    expect(
      layoutNodeHeight({ maxFan: 0, paramCount: 0, constraintCount: 0, hasDescription: false }),
    ).toBe(118);
  });

  it('keeps the fan-derived height for a fan-heavy, content-light node', () => {
    const h = layoutNodeHeight({ maxFan: 40, paramCount: 0, constraintCount: 0, hasDescription: false });
    expect(h).toBe(Math.round(40 * 8 + 52));
    expect(h).toBeGreaterThan(118);
  });

  it('grows past the old 118 floor for a content-heavy, fan-light node', () => {
    const h = layoutNodeHeight({ maxFan: 0, paramCount: 8, constraintCount: 3, hasDescription: true });
    expect(h).toBeGreaterThan(118);
  });

  it('is monotonic in paramCount', () => {
    let prev = 0;
    for (let p = 0; p <= 20; p++) {
      const h = layoutNodeHeight({ maxFan: 0, paramCount: p, constraintCount: 0, hasDescription: false });
      expect(h).toBeGreaterThanOrEqual(prev);
      prev = h;
    }
  });

  it('is monotonic in constraintCount', () => {
    let prev = 0;
    for (let c = 0; c <= 20; c++) {
      const h = layoutNodeHeight({ maxFan: 0, paramCount: 0, constraintCount: c, hasDescription: false });
      expect(h).toBeGreaterThanOrEqual(prev);
      prev = h;
    }
  });

  it('caps the parameter contribution at 8 rows', () => {
    const h8 = layoutNodeHeight({ maxFan: 0, paramCount: 8, constraintCount: 0, hasDescription: false });
    const h9 = layoutNodeHeight({ maxFan: 0, paramCount: 9, constraintCount: 0, hasDescription: false });
    const h50 = layoutNodeHeight({ maxFan: 0, paramCount: 50, constraintCount: 0, hasDescription: false });
    expect(h9).toBe(h50);
    expect(h9).toBeGreaterThan(h8);
    expect(h50 - h8).toBeLessThan(20);
  });
});
