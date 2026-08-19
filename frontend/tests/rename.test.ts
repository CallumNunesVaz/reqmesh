import { describe, it, expect } from 'vitest';
import { CASCADE_OPTIONS, formatRenames } from '../src/lib/rename';

describe('CASCADE_OPTIONS', () => {
  it('offers the three modes in order, self first', () => {
    expect(CASCADE_OPTIONS.map((o) => o.value)).toEqual(['self', 'children', 'descendants']);
  });

  it('defaults to self — today\'s behaviour', () => {
    expect(CASCADE_OPTIONS[0].value).toBe('self');
  });

  it('labels every mode', () => {
    for (const option of CASCADE_OPTIONS) {
      expect(option.label.trim()).not.toBe('');
      expect(option.hint.trim()).not.toBe('');
    }
  });
});

describe('formatRenames', () => {
  it('renders a single rename', () => {
    expect(formatRenames([{ from: 'REQ0001', to: 'SYS0001' }])).toBe('REQ0001 → SYS0001');
  });

  it('joins multiple renames one per line', () => {
    expect(formatRenames([
      { from: 'REQ0001', to: 'SYS0001' },
      { from: 'REQ0002', to: 'SYS0002' },
    ])).toBe('REQ0001 → SYS0001\nREQ0002 → SYS0002');
  });

  it('is empty when nothing is renamed', () => {
    expect(formatRenames([])).toBe('');
  });
});
