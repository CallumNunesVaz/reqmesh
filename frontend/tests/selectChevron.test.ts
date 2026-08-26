import { describe, it, expect } from 'vitest';

/**
 * Dropdown-affordance gate for `.select`.
 *
 * `.select` is `@apply input appearance-none cursor-pointer`, and
 * `appearance-none` strips the native dropdown arrow — historically nothing
 * redrew it, so the 33 selects on that class rendered as bare text boxes. The
 * fix draws a chevron as a CSS background image plus a `padding-right` that
 * reserves its room. There is no CSS unit-test harness, so this test parses
 * `index.css` directly (the same trick as `src/lib/__tests__/canvasContrast.test.ts`)
 * and fails if a future edit reinstates `appearance-none` alone.
 *
 * Node's built-ins are declared rather than typed for the same reason as
 * `tests/navDocs.test.ts`: the tsconfig sets `"types": []` so server-only APIs
 * cannot leak into `src/`.
 */
declare function require(id: string): { readFileSync(p: string, enc: string): string };
const { readFileSync } = require('fs');

const css = readFileSync(new URL('../src/styles/index.css', import.meta.url).pathname, 'utf-8');

function extractBlock(source: string, selector: string): string {
  const open = source.indexOf(`${selector} {`);
  if (open === -1) throw new Error(`did not find a "${selector} {" block in index.css`);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  throw new Error(`unterminated "${selector}" block in index.css`);
}

const select = extractBlock(css, '.select');

describe('.select dropdown affordance', () => {
  it('declares a background-image chevron', () => {
    expect(select).toMatch(/background-image\s*:/);
  });

  it('reserves right-side padding so a long label never runs under the arrow', () => {
    expect(select).toMatch(/padding-right\s*:/);
  });

  it('draws the chevron in currentColor so it re-steps with the theme', () => {
    expect(select).toContain('currentColor');
  });
});
