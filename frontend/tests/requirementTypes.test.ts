import { describe, expect, it } from 'vitest';
import {
  REQUIREMENT_TYPES,
  REQUIREMENT_TYPE_META,
  formatReqType,
  reqTypeClass,
  reqTypeMeta,
  typeOptionsFor,
} from '../src/lib/requirementTypes';

/**
 * The type vocabulary used to be copied into six files and had drifted — the
 * allocation matrix offered five of the sixteen. `e2e/inventory.spec.ts` checks
 * this list still matches the backend enum; these cover the behaviour around it,
 * which needs no running app.
 */

describe('the type table', () => {
  it('has metadata for every listed type', () => {
    for (const t of REQUIREMENT_TYPES) {
      const meta = REQUIREMENT_TYPE_META[t];
      expect(meta, t).toBeTruthy();
      expect(meta.label.length, t).toBeGreaterThan(0);
      expect(meta.token, t).toMatch(/^[a-z]+$/);
    }
  });

  it('gives every type a distinct label, so no two are indistinguishable in a dropdown', () => {
    const labels = REQUIREMENT_TYPES.map((t) => REQUIREMENT_TYPE_META[t].label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('keeps the non-functional variants distinguishable', () => {
    // The allocation matrix used to label `non_functional_performance` as plain
    // "Non-Functional", so filtering by it looked like it covered all seven
    // variants while excluding six of them.
    const nf = REQUIREMENT_TYPES.filter((t) => t.startsWith('non_functional'));
    expect(nf.length).toBeGreaterThan(1);
    for (const t of nf) {
      expect(REQUIREMENT_TYPE_META[t].label).toMatch(/^Non-Functional – .+/);
    }
  });
});

describe('unrecognised types', () => {
  // Projects imported from other tools, and older reqmesh data, carry types
  // outside the current enum.
  it('are not silently relabelled as a real type', () => {
    expect(reqTypeMeta('design').label).toBe('Design');
    expect(reqTypeMeta('constraint').label).toBe('Constraint');
    expect(reqTypeClass('design')).toBe('text-cs-grey');
  });

  it('are kept as a selectable option so a save cannot drop them', () => {
    // A <select> whose value matches no <option> displays the first one, so
    // without this the stored value is replaced by whatever leads the list.
    const opts = typeOptionsFor('design');
    expect(opts[0]).toBe('design');
    expect(opts).toHaveLength(REQUIREMENT_TYPES.length + 1);
  });

  it('do not add an option when the type is a known one', () => {
    expect(typeOptionsFor('functional')).toEqual(REQUIREMENT_TYPES);
    expect(typeOptionsFor('')).toEqual(REQUIREMENT_TYPES);
    expect(typeOptionsFor(undefined)).toEqual(REQUIREMENT_TYPES);
  });
});

describe('formatReqType', () => {
  it('uses the declared label for known types', () => {
    expect(formatReqType('regulatory_compliance')).toBe('Regulatory/Compliance');
    expect(formatReqType('non_functional_security')).toBe('Non-Functional – Security');
  });

  it('humanises unknown types rather than showing a raw key', () => {
    expect(formatReqType('some_future_type')).toBe('Some Future Type');
    expect(formatReqType('non_functional_future')).toBe('Non-Functional – Future');
  });
});
