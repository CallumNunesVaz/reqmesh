import { describe, it, expect } from 'vitest';

/**
 * Gate for the sub-`xs` type scale.
 *
 * Three named steps sit below `text-xs` (12px) and are what hundreds of call
 * sites rely on for the app's smallest text: `text-2xs` (11px), `text-3xs`
 * (10px) and `text-4xs` (9px). They were introduced to replace a pile of
 * bespoke arbitrary pixel sizes, so the only thing keeping a future edit from
 * deleting a step (or re-collapsing it back into ad-hoc pixel classes) is
 * this test. It reads the actual `fontSize` block out of `tailwind.config.js`
 * and asserts each step's pixel size, so a regression fails here before it ships.
 */

// See navDocs.test.ts for why Node's built-ins are declared rather than typed:
// the project tsconfig sets `"types": []` so server-only APIs cannot leak into
// `src/`. The path is resolved against this file, never hardcoded.
declare function require(id: string): { readFileSync(p: string, enc: string): string };
const { readFileSync } = require('fs');

const config = readFileSync(new URL('../../../tailwind.config.js', import.meta.url).pathname, 'utf-8');

// Pulls the `fontSize` block and returns a map of step name -> [size, lineHeight].
function parseFontSize(): Record<string, [string, string]> {
  const open = config.indexOf('fontSize: {');
  if (open === -1) throw new Error('did not find a "fontSize: {" block in tailwind.config.js');
  const start = config.indexOf('{', open);
  let depth = 0;
  for (let i = start; i < config.length; i += 1) {
    const ch = config[i];
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        const block = config.slice(start + 1, i);
        const steps: Record<string, [string, string]> = {};
        const re = /'([a-z0-9-]+)':\s*\[\s*'([^']+)'\s*,\s*'([^']+)'\s*\]/g;
        let m: RegExpExecArray | null;
        while ((m = re.exec(block)) !== null) {
          steps[m[1]] = [m[2], m[3]];
        }
        return steps;
      }
    }
  }
  throw new Error('unterminated "fontSize" block in tailwind.config.js');
}

const steps = parseFontSize();

describe('sub-xs type scale', () => {
  it('defines text-2xs at 11px', () => {
    expect(steps['2xs']?.[0], 'text-2xs should be 11px').toBe('11px');
  });

  it('defines text-3xs at 10px', () => {
    expect(steps['3xs']?.[0], 'text-3xs should be 10px').toBe('10px');
  });

  it('defines text-4xs at 9px', () => {
    expect(steps['4xs']?.[0], 'text-4xs should be 9px').toBe('9px');
  });

  it('gives every step a line-height so the classes render, not just a bare size', () => {
    for (const name of ['2xs', '3xs', '4xs']) {
      expect(steps[name]?.[1], `${name} should carry a lineHeight`).toBeTruthy();
    }
  });
});
