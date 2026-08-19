import { describe, it, expect } from 'vitest';
import { searchParameters } from '../src/components/mentions';
import { resolveParam, type ParameterRef, type ParameterValue } from '../src/components/parameterIndex';

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
