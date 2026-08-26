import { describe, it, expect } from 'vitest';

/**
 * An empty-state action must not be labelled like the page's header button.
 *
 * v0.4.0 shipped exactly that: an empty risks page rendered "New Risk" twice —
 * once in the header, once as the empty-state action. Twenty e2e specs broke
 * with `strict mode violation: ... resolved to 2 elements`, but the test
 * breakage was the symptom. The defect is that a screen reader announces
 * "New Risk button" twice with nothing to distinguish them.
 *
 * This is a static check rather than an e2e one on purpose. Reproducing it in
 * the browser needs a *genuinely empty* list — the seeded demo has risks, so
 * the empty state never renders there, and an e2e guard against the demo
 * project passes while the bug is present. That was verified: reintroducing
 * the bad label did not fail such a test.
 */
declare function require(id: string): {
  readFileSync(p: string, enc: string): string;
  readdirSync(p: string): string[];
};
const { readFileSync, readdirSync } = require('fs');

const PAGES_DIR = new URL('../src/pages', import.meta.url).pathname;

describe('empty-state action labels', () => {
  it('never reuse a "New X" header-button label', () => {
    const offenders: string[] = [];
    for (const file of readdirSync(PAGES_DIR).filter((f) => f.endsWith('.tsx'))) {
      const src = readFileSync(`${PAGES_DIR}/${file}`, 'utf8');
      // `action={... { label: '…' …}}` is only ever an EmptyState action.
      for (const m of src.matchAll(/action=\{[^}]*label:\s*'([^']+)'/g)) {
        if (/^New\s/.test(m[1])) offenders.push(`${file}: "${m[1]}"`);
      }
    }
    expect(offenders, 'empty-state actions duplicating a header button label').toEqual([]);
  });
});
