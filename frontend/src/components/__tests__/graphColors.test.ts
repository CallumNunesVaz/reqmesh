import { describe, it, expect } from 'vitest';
import {
  glow,
  statusColors,
  priorityColors,
  constraintColors,
  edgeColors,
} from '../graphColors';
import { statusMinimapColors } from '../GraphPane';

// The canvas palette must be token-based end to end: every colour is an
// `hsl(var(--cs-*))` token so it re-steps for the light theme, never a
// hardcoded literal that freezes at its dark-mode value.
const TOKEN_RE = /^hsl\(var\(--cs-[a-z]+\)\)$/;

function assertTokenValues(map: Record<string, string | { fill: string; text: string }>, label: string) {
  for (const [key, value] of Object.entries(map)) {
    if (typeof value === 'string') {
      expect(value, `${label}.${key} = ${value}`).toMatch(TOKEN_RE);
    } else {
      expect(value.fill, `${label}.${key}.fill = ${value.fill}`).toMatch(TOKEN_RE);
      expect(value.text, `${label}.${key}.text = ${value.text}`).toMatch(TOKEN_RE);
    }
  }
}

describe('glow', () => {
  it('turns a comma-hsl colour into hsla with the given alpha', () => {
    expect(glow('hsl(210, 90%, 60%)', 0.5)).toBe('hsla(210, 90%, 60%, 0.5)');
  });

  it('only rewrites the trailing paren, so nested content survives', () => {
    expect(glow('hsl(0, 0%, 0%)', 1)).toBe('hsla(0, 0%, 0%, 1)');
  });

  it('turns a token colour into slash-alpha hsl, not mixed comma/space syntax', () => {
    expect(glow('hsl(var(--cs-blue))', 0.4)).toBe('hsl(var(--cs-blue) / 0.4)');
  });

  it('passes through a colour it cannot parse', () => {
    expect(glow('#ff0000', 0.5)).toBe('#ff0000');
  });
});

describe('canvas palette maps', () => {
  it('statusColors values are all --cs-* tokens', () => {
    assertTokenValues(statusColors, 'statusColors');
  });

  it('priorityColors values are all --cs-* tokens', () => {
    assertTokenValues(priorityColors, 'priorityColors');
  });

  it('constraintColors values are all --cs-* tokens', () => {
    assertTokenValues(constraintColors, 'constraintColors');
  });

  it('edgeColors values are all --cs-* tokens', () => {
    assertTokenValues(edgeColors, 'edgeColors');
  });

  it('statusMinimapColors shares statusColors key set', () => {
    expect(Object.keys(statusMinimapColors).sort()).toEqual(Object.keys(statusColors).sort());
  });
});

describe('shiftLightness removal', () => {
  it('is no longer exported from graphColors', async () => {
    const mod = await import('../graphColors');
    expect(Object.keys(mod)).not.toContain('shiftLightness');
  });
});
