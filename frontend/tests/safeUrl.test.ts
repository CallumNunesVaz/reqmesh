import { describe, it, expect } from 'vitest';
import { isSafeExternalUrl } from '../src/lib/safeUrl';

describe('isSafeExternalUrl', () => {
  it.each([
    ['https://example.com/spec.pdf', true],
    ['http://intranet/doc', true],
    ['mailto:eng@example.com', true],
    ['docs/spec.pdf', true],
    ['javascript:alert(1)', false],
    ['JaVaScRiPt:alert(1)', false],
    ['java\tscript:alert(1)', false],
    ['  javascript:alert(1)', false],
    ['data:text/html,<script>', false],
    ['file:///etc/passwd', false],
    ['//evil.com', false],
    ['', false],
  ])('%s → %s', (url, expected) => {
    expect(isSafeExternalUrl(url)).toBe(expected);
  });

  it('returns false for null', () => {
    expect(isSafeExternalUrl(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isSafeExternalUrl(undefined)).toBe(false);
  });
});
