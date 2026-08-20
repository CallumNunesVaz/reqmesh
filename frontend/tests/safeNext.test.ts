import { describe, it, expect } from 'vitest';
import { safeNext } from '../src/lib/safeNext';

const BASE = 'https://good.example';

/** True if a value resolves to the good.example origin — the property every
 *  accepted redirect must preserve, regardless of how the string looks. */
function resolvesSameOrigin(value: string): boolean {
  try {
    return new URL(value, BASE).origin === BASE;
  } catch {
    return false;
  }
}

describe('safeNext', () => {
  it.each(['/', '/requirements', '/requirements?status=open#frag'])(
    'accepts %s unchanged and on-origin',
    (value) => {
      const result = safeNext(value);
      expect(result).toBe(value);
      expect(resolvesSameOrigin(result!)).toBe(true);
    },
  );

  it.each([
    '//host',
    '/\\host',
    'https://example.com',
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'example.com',
    '/requirements\\evil.com',
  ])('rejects %j', (value) => {
    expect(safeNext(value)).toBeNull();
  });

  it('rejects null', () => {
    expect(safeNext(null)).toBeNull();
  });

  it('rejects undefined', () => {
    expect(safeNext(undefined)).toBeNull();
  });

  it('rejects the empty string', () => {
    expect(safeNext('')).toBeNull();
  });

  describe('leading whitespace and control characters are stripped first', () => {
    const DANGEROUS = [
      '//host',
      '/\\host',
      'https://example.com',
      'javascript:alert(1)',
      'JaVaScRiPt:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      'example.com',
      '/requirements\\evil.com',
    ];
    const PREFIXES = [' ', '\t', '\n', '\r', ' \t', '\n\t', '\x00'];

    it.each(
      DANGEROUS.flatMap((value) => PREFIXES.map((prefix) => `${prefix}${value}`)),
    )('rejects %j when preceded by whitespace or control', (value) => {
      expect(safeNext(value)).toBeNull();
    });
  });

  describe('interior tab, line feed and carriage return are stripped everywhere', () => {
    // A tab/LF/CR between the two leading slashes hides `//evil.example` from
    // the prefix checks, but the browser strips it and resolves off-origin.
    it.each([
      ['/\n/evil.example', '//evil.example'],
      ['/\t/evil.example', '//evil.example'],
      ['/\r/evil.example', '//evil.example'],
    ])('%j resolves to %j in the browser and is rejected', (input, resolved) => {
      expect(new URL(resolved, BASE).origin).not.toBe(BASE);
      expect(safeNext(input)).toBeNull();
    });

    // The browser strips an interior newline and lands on `/foobar`, so the
    // sanitised value preserves that same-origin destination rather than
    // dropping a legitimate redirect. Accepting it is only safe because the
    // returned value is the sanitised one.
    it('accepts an interior newline only as the sanitised path', () => {
      const result = safeNext('/foo\nbar');
      expect(result).toBe('/foobar');
      expect(resolvesSameOrigin(result!)).toBe(true);
    });

    it('an interior tab is sanitised out of a legitimate path', () => {
      const result = safeNext('/foo\tbar');
      expect(result).toBe('/foobar');
      expect(resolvesSameOrigin(result!)).toBe(true);
    });
  });
});
