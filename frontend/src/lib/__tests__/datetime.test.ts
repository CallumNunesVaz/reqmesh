import { describe, it, expect } from 'vitest';
import { formatDate, formatDateTime } from '../datetime';

describe('datetime helpers', () => {
  it('returns an empty string for empty input', () => {
    expect(formatDateTime('')).toBe('');
    expect(formatDateTime(null)).toBe('');
    expect(formatDateTime(undefined)).toBe('');
    expect(formatDate('')).toBe('');
  });

  it('returns the raw value for an unparseable date', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date');
  });

  it('renders a real timestamp with its year', () => {
    const out = formatDateTime('2026-09-13T12:34:56Z');
    expect(out).toContain('2026');
    expect(out.length).toBeGreaterThan(8);
  });
});
