import { describe, it, expect } from 'vitest';
import { ACTIVITY_KIND_ORDER } from '../src/api/client';

describe('ACTIVITY_KIND_ORDER', () => {
  it('matches the documented CVD-validated stacking order', () => {
    // This is the order from the task spec.  Sorting this alphabetically
    // would silently void the CVD separation guarantee (adjacent segments
    // must never leave a deuteranope or protanope unable to tell them apart
    // in either theme).  If this test fails, the order was changed without
    // re-running the palette validation.
    expect(ACTIVITY_KIND_ORDER).toEqual([
      'verification',
      'change',
      'specification',
      'requirement',
      'component',
      'decision',
      'risk',
    ]);
  });

  it('contains exactly seven kinds (one per entity)', () => {
    expect(ACTIVITY_KIND_ORDER).toHaveLength(7);
  });

  it('has no duplicate kinds', () => {
    expect(new Set(ACTIVITY_KIND_ORDER).size).toBe(ACTIVITY_KIND_ORDER.length);
  });
});
