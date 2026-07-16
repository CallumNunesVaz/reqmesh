import { describe, it, expect } from 'vitest';
import { glow, shiftLightness } from '../src/components/graphColors';

describe('glow', () => {
  it('turns a comma-hsl colour into hsla with the given alpha', () => {
    expect(glow('hsl(210, 90%, 60%)', 0.5)).toBe('hsla(210, 90%, 60%, 0.5)');
  });

  it('only rewrites the trailing paren, so nested content survives', () => {
    expect(glow('hsl(0, 0%, 0%)', 1)).toBe('hsla(0, 0%, 0%, 1)');
  });

  it('passes through a colour it cannot parse', () => {
    expect(glow('#ff0000', 0.5)).toBe('#ff0000');
  });
});

describe('shiftLightness', () => {
  it('lightens and darkens by percentage points', () => {
    expect(shiftLightness('hsl(145,55%,42%)', 12)).toBe('hsl(145,55%,54%)');
    expect(shiftLightness('hsl(145,55%,42%)', -10)).toBe('hsl(145,55%,32%)');
  });

  it('clamps to the 0–100 range instead of emitting invalid css', () => {
    expect(shiftLightness('hsl(0,84%,68%)', 50)).toBe('hsl(0,84%,100%)');
    expect(shiftLightness('hsl(0,84%,10%)', -50)).toBe('hsl(0,84%,0%)');
  });

  it('tolerates whitespace and decimals in the source colour', () => {
    expect(shiftLightness('hsl(207, 90%, 63.5%)', 0.5)).toBe('hsl(207,90%,64%)');
  });

  it('passes through a colour it cannot parse', () => {
    expect(shiftLightness('#ff0000', 10)).toBe('#ff0000');
    expect(shiftLightness('hsl(var(--foreground))', 10)).toBe('hsl(var(--foreground))');
  });
});
