import { describe, it, expect } from 'vitest';
import {
  filterSuggestions,
  comboboxKeyDown,
  type Suggestion,
} from '../src/components/AutocompleteInput';
import { availableOptions } from '../src/components/LinkEditor';

const suggestions: Suggestion[] = [
  { id: 'AFRM0001', label: 'Fuel pressure must be monitored' },
  { id: 'RSK-001', label: 'Engine overheat' },
  { id: 'VC-042', label: 'Fuel pressure test' },
];

describe('filterSuggestions', () => {
  it('narrows by a fragment of a name, case-insensitively', () => {
    expect(filterSuggestions('overheat', suggestions).map((s) => s.id)).toEqual(['RSK-001']);
    expect(filterSuggestions('FUEL PRESSURE', suggestions).map((s) => s.id)).toEqual([
      'AFRM0001',
      'VC-042',
    ]);
  });

  it('narrows by a fragment of an id, case-insensitively', () => {
    expect(filterSuggestions('frm0', suggestions).map((s) => s.id)).toEqual(['AFRM0001']);
    expect(filterSuggestions('042', suggestions).map((s) => s.id)).toEqual(['VC-042']);
  });

  it('returns every suggestion for an empty query', () => {
    expect(filterSuggestions('', suggestions)).toHaveLength(3);
  });
});

describe('comboboxKeyDown', () => {
  it('Enter on the highlighted row commits that id', () => {
    const next = comboboxKeyDown({ open: true, highlight: 1 }, 'Enter', suggestions);
    expect(next.selectId).toBe('RSK-001');
    expect(next.open).toBe(false);
    expect(next.highlight).toBe(0);
  });

  it('Enter with nothing visible commits nothing', () => {
    const next = comboboxKeyDown({ open: true, highlight: 0 }, 'Enter', []);
    expect(next.selectId).toBeUndefined();
  });

  it('Escape closes without committing', () => {
    const next = comboboxKeyDown({ open: true, highlight: 0 }, 'Escape', suggestions);
    expect(next.selectId).toBeUndefined();
    expect(next.open).toBe(false);
  });

  it('ArrowDown and ArrowUp move the highlight, clamped at the ends', () => {
    expect(comboboxKeyDown({ open: true, highlight: 0 }, 'ArrowDown', suggestions).highlight).toBe(1);
    expect(comboboxKeyDown({ open: true, highlight: 1 }, 'ArrowUp', suggestions).highlight).toBe(0);
    expect(comboboxKeyDown({ open: true, highlight: 2 }, 'ArrowDown', suggestions).highlight).toBe(2);
    expect(comboboxKeyDown({ open: true, highlight: 0 }, 'ArrowUp', suggestions).highlight).toBe(0);
  });

  it('ArrowDown from closed opens without skipping the first row', () => {
    const next = comboboxKeyDown({ open: false, highlight: 0 }, 'ArrowDown', suggestions);
    expect(next.open).toBe(true);
    expect(next.highlight).toBe(0);
    expect(next.selectId).toBeUndefined();
  });
});

describe('availableOptions', () => {
  const options = [
    { id: 'A', name: 'Alpha' },
    { id: 'B', name: 'Bravo' },
    { id: 'C', name: 'Charlie' },
  ];

  it('excludes every already-linked id', () => {
    expect(availableOptions(options, ['B']).map((o) => o.id)).toEqual(['A', 'C']);
  });

  it('returns everything when nothing is linked', () => {
    expect(availableOptions(options, [])).toHaveLength(3);
  });

  it('returns nothing when everything is linked', () => {
    expect(availableOptions(options, ['A', 'B', 'C'])).toHaveLength(0);
  });
});
