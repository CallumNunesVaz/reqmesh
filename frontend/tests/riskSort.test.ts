import { describe, it, expect } from 'vitest';
import { bandOrder, compareRisks, sortRisks } from '../src/lib/riskSort';
import type { Risk, RiskBand } from '../src/api/client';

const BANDS: RiskBand[] = [
  { key: 'low', label: 'Low', color: '#22c55e' },
  { key: 'medium', label: 'Medium', color: '#eab308' },
  { key: 'high', label: 'High', color: '#f97316' },
  { key: 'extreme', label: 'Extreme', color: '#ef4444' },
];

function mkRisk(overrides: Partial<Risk> = {}): Risk {
  return {
    id: 'RSK-1',
    title: '',
    failure_mode: '',
    effect: '',
    cause: '',
    description: '',
    severity: 'medium',
    likelihood: 'possible',
    probability: '',
    impact: '',
    mitigation: '',
    detection: '',
    linked_requirements: [],
    mitigating_requirements: [],
    linked_components: [],
    mitigating_components: [],
    status: 'open',
    created: '',
    modified: '',
    ...overrides,
  };
}

const rated = (id: string, band: string): Risk =>
  mkRisk({ id, rating: { band, label: band, color: '', severity: 'medium', likelihood: 'possible', unrated_reason: null } });

describe('bandOrder', () => {
  it('maps a rated band to its position in the matrix order', () => {
    expect(bandOrder(rated('a', 'low'), BANDS)).toBe(0);
    expect(bandOrder(rated('a', 'extreme'), BANDS)).toBe(3);
  });

  it('sorts an unrated risk after every rated band', () => {
    expect(bandOrder(mkRisk({ severity: 'severe', rating: { band: null, label: null, color: null, severity: 'severe', likelihood: null, unrated_reason: 'severity not a level' } }), BANDS))
      .toBe(BANDS.length);
  });

  it('sorts a risk whose band key the matrix no longer defines after every band', () => {
    expect(bandOrder(rated('a', 'defunct'), BANDS)).toBe(BANDS.length);
  });
});

describe('sortRisks', () => {
  const risks: Risk[] = [
    rated('RSK-LOW', 'low'),
    rated('RSK-EXTREME', 'extreme'),
    rated('RSK-HIGH', 'high'),
    // Severity/likelihood levels the matrix does not define — the model
    // tolerates these, so the sort must place them without throwing.
    mkRisk({ id: 'RSK-UNRATED', severity: 'catastrophic', likelihood: 'somehow' }),
    rated('RSK-MEDIUM', 'medium'),
  ];

  it('orders by band, least to most serious, unrated last', () => {
    const ordered = sortRisks(risks, 'band', 'asc', BANDS).map((r) => r.id);
    expect(ordered).toEqual(['RSK-LOW', 'RSK-MEDIUM', 'RSK-HIGH', 'RSK-EXTREME', 'RSK-UNRATED']);
  });

  it('orders descending, most serious first, with unrated first', () => {
    const ordered = sortRisks(risks, 'band', 'desc', BANDS).map((r) => r.id);
    expect(ordered).toEqual(['RSK-UNRATED', 'RSK-EXTREME', 'RSK-HIGH', 'RSK-MEDIUM', 'RSK-LOW']);
  });
});

describe('compareRisks', () => {
  it('sorts text columns case-insensitively', () => {
    const a = mkRisk({ id: 'RSK-1', status: 'closed' });
    const b = mkRisk({ id: 'RSK-2', status: 'OPEN' });
    expect(compareRisks(a, b, 'status', 'asc', BANDS)).toBeLessThan(0);
  });

  it('sorts by link count', () => {
    const many = mkRisk({ id: 'a', linked_requirements: ['x', 'y'], linked_components: ['c'] });
    const few = mkRisk({ id: 'b', linked_components: ['c'] });
    expect(compareRisks(many, few, 'links', 'asc', BANDS)).toBeGreaterThan(0);
  });
});
