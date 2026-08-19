import { describe, it, expect } from 'vitest';
import {
  buildParameterReferences,
  filterReferences,
  identifierFragment,
  resolveParameterEdit,
  type ParamReference,
} from '../src/lib/parametrics';
import type { Parameter } from '../src/api/client';

const refsOf = (refs: ParamReference[]) => refs.map((r) => r.ref);

describe('resolveParameterEdit', () => {
  it('round-trips every field when only the unit is edited', () => {
    const original: Parameter = {
      name: 'margin',
      value: null,
      unit: 'm',
      expr: null,
      kind: 'MOE',
      value_type: 'LengthValue',
      calc_def: 'MARGIN',
      bindings: { actual: 'REQM0001.span' },
    };
    const next = resolveParameterEdit(original, { name: 'margin', value: '', unit: 'm2', expr: '' });
    // The full object handed to onSave: only `unit` changed, nothing else lost.
    expect(next).toEqual({
      name: 'margin',
      value: null,
      unit: 'm2',
      expr: null,
      kind: 'MOE',
      value_type: 'LengthValue',
      calc_def: 'MARGIN',
      bindings: { actual: 'REQM0001.span' },
    });
  });

  it('preserves kind and value_type when editing a literal parameter', () => {
    const original: Parameter = {
      name: 'mass', value: 767, unit: 'kg', expr: null, kind: 'TPM', value_type: 'MassValue',
    };
    const next = resolveParameterEdit(original, { name: 'mass', value: '768', unit: 'kg', expr: '' });
    expect(next).toEqual({
      name: 'mass', value: 768, unit: 'kg', expr: null, kind: 'TPM', value_type: 'MassValue',
      calc_def: undefined, bindings: undefined,
    });
  });

  it('switching a literal parameter to an expression nulls value', () => {
    const original: Parameter = { name: 'x', value: 5, unit: 'kg', expr: null };
    const next = resolveParameterEdit(original, { name: 'x', value: '5', unit: 'kg', expr: 'a * b' });
    expect(next.value).toBeNull();
    expect(next.expr).toBe('a * b');
  });

  it('switching an expression parameter back to a literal nulls expr', () => {
    const original: Parameter = { name: 'x', value: null, unit: 'kg', expr: 'a * b' };
    const next = resolveParameterEdit(original, { name: 'x', value: '7', unit: 'kg', expr: '' });
    expect(next.value).toBe(7);
    expect(next.expr).toBeNull();
  });
});

describe('buildParameterReferences', () => {
  const base = {
    ownId: 'REQM0001',
    ownParameters: [{ name: 'temp_max', value: 100, unit: 'C' }] as Parameter[],
    others: [
      { id: 'REQM0002', parameters: [{ name: 'min', value: 0, unit: 'C' }] as Parameter[] },
      { id: 'WING01', parameters: [{ name: 'mass', value: 55, unit: 'kg' }] as Parameter[] },
    ],
    definitions: [],
  };

  it('offers own parameters by bare name', () => {
    const refs = refsOf(buildParameterReferences(base));
    expect(refs).toContain('temp_max');
    expect(refs).not.toContain('REQM0001.temp_max');
  });

  it("offers another requirement's parameter as ID.param", () => {
    const refs = refsOf(buildParameterReferences(base));
    expect(refs).toContain('REQM0002.min');
    expect(refs).toContain('WING01.mass');
  });

  it('offers the rollup helper and its label documents the tree sum', () => {
    const refs = buildParameterReferences(base);
    const rollup = refs.find((r) => r.ref === "rollup('', '')");
    expect(rollup).toBeDefined();
    expect(rollup!.label).toContain('rollup');
    expect(rollup!.label).toContain('component tree');
  });

  it('shows the current value alongside the reference', () => {
    const refs = buildParameterReferences({ ...base, evalValues: new Map([['REQM0002.min', 3.5]]) });
    const entry = refs.find((r) => r.ref === 'REQM0002.min');
    expect(entry!.label).toContain('3.5');
  });
});

describe('filterReferences', () => {
  const refs = buildParameterReferences({
    ownId: 'REQM0001',
    ownParameters: [{ name: 'temp_max', value: 100, unit: 'C' }],
    others: [
      { id: 'REQM0002', parameters: [{ name: 'min', value: 0, unit: 'C' }] },
      { id: 'REQM0003', parameters: [{ name: 'min', value: 0, unit: 'C' }] },
    ],
    definitions: [],
  });

  it('filters after REQM0002. to just that requirement\'s params', () => {
    const hits = refsOf(filterReferences(refs, 'REQM0002.'));
    expect(hits).toContain('REQM0002.min');
    expect(hits).not.toContain('REQM0003.min');
    expect(hits).not.toContain('temp_max');
  });

  it('lets a bare min fragment surface the qualified reference', () => {
    const hits = refsOf(filterReferences(refs, 'min'));
    expect(hits).toContain('REQM0002.min');
    expect(hits).toContain('REQM0003.min');
  });

  it('returns everything for an empty fragment', () => {
    expect(refsOf(filterReferences(refs, ''))).toEqual(refsOf(refs));
  });
});

describe('identifierFragment', () => {
  it('captures the identifier under the caret, including a trailing dot', () => {
    const text = 'REQM0002.';
    expect(identifierFragment(text, text.length)).toBe('REQM0002.');
  });

  it('stops at operators and whitespace', () => {
    const text = 'a * REQM0002.mi';
    expect(identifierFragment(text, text.length)).toBe('REQM0002.mi');
  });
});
