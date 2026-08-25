import { describe, it, expect } from 'vitest';
import { searchParameters } from '../src/components/mentions';
import {
  overlayLocalParams, resolveParam, type ParameterRef, type ParameterValue,
} from '../src/components/parameterIndex';
import type { Parameter } from '../src/api/client';

const ref = (entityId: string, name: string, value: number | null, unit = '', derived = false): ParameterRef =>
  ({ ref: `${entityId}.${name}`, entityId, name, unit, value, derived });

const index = [
  ref('REQM0002', 'temp_max', 30, '°C'),
  ref('REQM0002', 'temp_min', -5, '°C'),
  ref('AFRM0000', 'empty_mass', 767, 'kg'),
];

describe('searchParameters', () => {
  it('offers the holder’s own parameters by bare name', () => {
    const r = searchParameters(index, 'REQM0002', 'temp');
    expect(r[0]).toEqual({
      type: 'param', ref: 'REQM0002.temp_max', name: 'temp_max', unit: '°C', value: 30, own: true,
    });
  });

  it('offers other entities’ parameters as ID.param', () => {
    const r = searchParameters(index, 'REQM0002', 'empty');
    expect(r[0]).toEqual({
      type: 'param', ref: 'AFRM0000.empty_mass', name: 'AFRM0000.empty_mass', unit: 'kg', value: 767, own: false,
    });
  });

  it('stores an own pick fully qualified even though it is shown by bare name', () => {
    // The display name is the bare `temp_max`, but the ref that gets written is
    // `REQM0002.temp_max` — an unqualified name has no meaning outside its owner.
    const r = searchParameters(index, 'REQM0002', 'temp_max');
    expect(r[0].name).toBe('temp_max');
    expect(r[0].ref).toBe('REQM0002.temp_max');
  });

  it('returns own parameters before others when browsing', () => {
    const r = searchParameters(index, 'REQM0002', '');
    expect(r.filter((o) => o.own).length).toBe(2);
    expect(r[0].own).toBe(true);
  });
});

describe('resolveParam', () => {
  const values = new Map<string, ParameterValue>([
    ['REQM0002.temp_max', { value: 30, unit: '°C' }],
  ]);

  it('resolves a parameter to value + unit', () => {
    expect(resolveParam('REQM0002.temp_max', values)).toEqual({ kind: 'value', text: '30 °C' });
  });

  it('resolves a parameter with no unit to the bare value', () => {
    const v = new Map<string, ParameterValue>([['X.mass', { value: 88, unit: '' }]]);
    expect(resolveParam('X.mass', v)).toEqual({ kind: 'value', text: '88' });
  });

  it('renders a missing parameter broken, not empty and not a crash', () => {
    expect(resolveParam('REQM0002.deleted', values)).toEqual({ kind: 'broken' });
  });

  it('renders a valueless parameter broken', () => {
    const v = new Map<string, ParameterValue>([['REQM0002.temp_max', { value: null, unit: '°C' }]]);
    expect(resolveParam('REQM0002.temp_max', v)).toEqual({ kind: 'broken' });
  });
});

describe('overlayLocalParams', () => {
  // The regression this exists for: a parameter added to the parametrics card
  // lives in the page's draft state until the requirement is saved, so the
  // server-built index cannot know about it and the `@`-picker could not
  // mention it without a full page reload.
  const draft = (name: string, value: number | null, unit = '', expr: string | null = null): Parameter =>
    ({ name, value, unit, expr } as Parameter);

  it('offers a parameter that has been added but not yet saved', () => {
    const out = overlayLocalParams(index, 'REQM0002', [
      draft('temp_max', 30, '°C'), draft('temp_min', -5, '°C'), draft('pressure', 101, 'kPa'),
    ]);
    expect(out.map((r) => r.ref)).toContain('REQM0002.pressure');
    expect(searchParameters(out, 'REQM0002', 'pressure')[0]).toEqual({
      type: 'param', ref: 'REQM0002.pressure', name: 'pressure', unit: 'kPa', value: 101, own: true,
    });
  });

  it('prefers the draft value and unit over the saved ones', () => {
    const out = overlayLocalParams(index, 'REQM0002', [draft('temp_max', 45, 'K')]);
    const hit = out.find((r) => r.ref === 'REQM0002.temp_max');
    expect(hit).toMatchObject({ value: 45, unit: 'K' });
    expect(out.filter((r) => r.ref === 'REQM0002.temp_max')).toHaveLength(1);
  });

  it('drops a saved parameter the draft has removed', () => {
    const out = overlayLocalParams(index, 'REQM0002', [draft('temp_max', 30, '°C')]);
    expect(out.map((r) => r.ref)).not.toContain('REQM0002.temp_min');
  });

  it('leaves every other entity’s parameters untouched', () => {
    const out = overlayLocalParams(index, 'REQM0002', [draft('temp_max', 30, '°C')]);
    expect(out.find((r) => r.ref === 'AFRM0000.empty_mass')).toEqual(index[2]);
  });

  it('marks a derived draft parameter valueless — the server has not evaluated it yet', () => {
    const out = overlayLocalParams(index, 'REQM0002', [draft('span', null, 'm', 'temp_max * 2')]);
    expect(out.find((r) => r.ref === 'REQM0002.span')).toMatchObject({ value: null, derived: true });
  });

  it('ignores a half-typed row with no name', () => {
    const out = overlayLocalParams(index, 'REQM0002', [draft('  ', 5)]);
    expect(out).toBe(index);
  });

  it('passes the index straight through with no holder or no draft', () => {
    expect(overlayLocalParams(index, undefined, [draft('x', 1)])).toBe(index);
    expect(overlayLocalParams(index, 'REQM0002', [])).toBe(index);
    expect(overlayLocalParams(index, 'REQM0002', undefined)).toBe(index);
  });
});
