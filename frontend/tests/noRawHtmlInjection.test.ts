import { describe, it, expect } from 'vitest';

/**
 * `dangerouslySetInnerHTML` is banned in `src/`.
 *
 * Semgrep's react-dangerouslysetinnerhtml rule already blocks it, but only in
 * the release workflow — one use in BaselinesPage failed a GitHub release long
 * after it was written and merged. This puts the same rule in `npm test`, where
 * it costs nothing and fires before the push.
 *
 * The app has a read-only renderer for stored rich text, `AutoLinkHtml`, which
 * parses to React through a tag whitelist and drops every attribute. Anywhere
 * that needs to display saved HTML should use it. If a case ever genuinely
 * needs raw injection, this test is the place to record why.
 */

// See navDocs.test.ts for why Node's built-ins are declared rather than typed:
// the project tsconfig sets `"types": []` so server-only APIs cannot leak into
// `src/`.
declare function require(id: string): {
  readdirSync(p: string, o: { withFileTypes: true }): { name: string; isDirectory(): boolean }[];
  readFileSync(p: string, enc: string): string;
};
const { readdirSync, readFileSync } = require('fs');

const SRC = new URL('../src', import.meta.url).pathname;

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = `${dir}/${entry.name}`;
    if (entry.isDirectory()) found.push(...sourceFiles(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) found.push(full);
  }
  return found;
}

describe('raw HTML injection', () => {
  it('no source file uses dangerouslySetInnerHTML', () => {
    const offenders = sourceFiles(SRC).filter((file) =>
      readFileSync(file, 'utf-8').includes('dangerouslySetInnerHTML'),
    );

    expect(offenders.map((f) => f.slice(SRC.length + 1))).toEqual([]);
  });

  it('finds the files it is meant to be scanning', () => {
    // A guard on the guard: a wrong path would make the check above pass by
    // reading nothing at all.
    const files = sourceFiles(SRC);
    expect(files.length).toBeGreaterThan(50);
    expect(files.some((f) => f.endsWith('pages/BaselinesPage.tsx'))).toBe(true);
  });
});
