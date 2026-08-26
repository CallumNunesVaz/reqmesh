import { describe, it, expect } from 'vitest';
import { useStore } from '../src/store';

/**
 * Density gate — store setting and the CSS marker contract.
 *
 * The `applyDensity` DOM behaviour is covered in `density.dom.test.ts` (jsdom);
 * this file stays in the default node environment so it can read `index.css`
 * via `import.meta.url`, the same trick as `tests/selectChevron.test.ts`.
 *
 * `rt-row` must be a marker only: `index.css` has no `.rt-row` rule outside a
 * `[data-density="compact"]` selector, which is what guarantees the marker
 * cannot silently change the default appearance. The tsconfig sets
 * `"types": []` so `fs` is declared rather than typed.
 */
declare function require(id: string): { readFileSync(p: string, enc: string): string };
const { readFileSync } = require('fs');

const css: string = readFileSync(new URL('../src/styles/index.css', import.meta.url).pathname, 'utf-8');

/** Every top-level selector that mentions `needle`, extracted from `source`. */
function selectorsFor(needle: string, source: string): string[] {
  const stripped = source.replace(/\/\*[\s\S]*?\*\//g, '');
  const out: string[] = [];
  let idx = stripped.indexOf(needle);
  while (idx !== -1) {
    const open = stripped.indexOf('{', idx);
    const prevClose = stripped.lastIndexOf('}', idx);
    const selector = stripped.slice(prevClose + 1, open === -1 ? stripped.length : open).trim();
    out.push(selector);
    idx = open === -1 ? -1 : stripped.indexOf(needle, open + 1);
  }
  return out;
}

describe('density store setting', () => {
  it('defaults to comfortable', () => {
    expect(useStore.getState().density).toBe('comfortable');
  });

  it('round-trips through compact and back', () => {
    const { setDensity } = useStore.getState();
    setDensity('compact');
    expect(useStore.getState().density).toBe('compact');
    setDensity('comfortable');
    expect(useStore.getState().density).toBe('comfortable');
  });
});

describe('rt-row is a marker only', () => {
  it('every .rt-row rule lives under a [data-density="compact"] selector', () => {
    const selectors = selectorsFor('.rt-row', css);
    expect(selectors.length).toBeGreaterThan(0);
    for (const selector of selectors) {
      expect(selector).toContain('[data-density="compact"]');
    }
  });
});
