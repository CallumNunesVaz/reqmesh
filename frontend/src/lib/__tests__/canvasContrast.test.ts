import { describe, it, expect } from 'vitest';

/**
 * Contrast gate for the canvas surface ramp.
 *
 * The graph canvas is deliberately recessed below `--background` so that nodes
 * read as cards sitting *on* a surface rather than a flat field. That recess is
 * pure colour: same nodes, edges, layout and dim/highlight logic as before, so
 * the only thing keeping the ramp from silently regressing back to the old
 * 1.06:1 node-on-canvas mush is this test. It reads the actual `--graph-*`
 * tokens out of `index.css` and re-derives the WCAG ratios the values were
 * chosen against, so a future re-tune has to fail here before it ships.
 */

// See navDocs.test.ts for why Node's built-ins are declared rather than typed:
// the project tsconfig sets `"types": []` so server-only APIs cannot leak into
// `src/`. The path is resolved against this file, never hardcoded.
declare function require(id: string): { readFileSync(p: string, enc: string): string };
const { readFileSync } = require('fs');

type Hsl = [h: number, s: number, l: number];
type Rgb = [r: number, g: number, b: number];

function extractBlock(css: string, selector: string): string {
  const open = css.indexOf(`${selector} {`);
  if (open === -1) throw new Error(`did not find a "${selector} {" block in index.css`);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    const ch = css[i];
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return css.slice(open, i + 1);
    }
  }
  throw new Error(`unterminated "${selector}" block in index.css`);
}

// Pulls every `--name: H S% L%` triple out of a theme block. The chart palette
// is hex, so it is naturally skipped; `--background` and the whole `--graph-*`
// family come through as HSL.
function parseHslTokens(block: string): Record<string, Hsl> {
  const tokens: Record<string, Hsl> = {};
  const re = /--([a-z0-9-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block)) !== null) {
    tokens[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])];
  }
  return tokens;
}

function hslToRgb(h: number, s: number, l: number): Rgb {
  const sn = s / 100;
  const ln = l / 100;
  const c = (1 - Math.abs(2 * ln - 1)) * sn;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let rgb: Rgb;
  if (hp < 1) rgb = [c, x, 0];
  else if (hp < 2) rgb = [x, c, 0];
  else if (hp < 3) rgb = [0, c, x];
  else if (hp < 4) rgb = [0, x, c];
  else if (hp < 5) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  const m = ln - c / 2;
  return [rgb[0] + m, rgb[1] + m, rgb[2] + m];
}

// WCAG 2.1 relative luminance: linearise each channel, then the standard
// 0.2126 / 0.7152 / 0.0722 weighting.
function linearize(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgb): number {
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

// Straight alpha compositing of one sRGB colour over another.
function over(fg: Rgb, bg: Rgb, alpha: number): Rgb {
  return [
    fg[0] * alpha + bg[0] * (1 - alpha),
    fg[1] * alpha + bg[1] * (1 - alpha),
    fg[2] * alpha + bg[2] * (1 - alpha),
  ];
}

const css = readFileSync(new URL('../../styles/index.css', import.meta.url).pathname, 'utf-8');
const dark = parseHslTokens(extractBlock(css, '.dark'));
const light = parseHslTokens(extractBlock(css, '.light'));

function token(theme: Record<string, Hsl>, name: string): Rgb {
  const triple = theme[name];
  if (!triple) throw new Error(`--${name} is missing from index.css`);
  return hslToRgb(triple[0], triple[1], triple[2]);
}

// Asserts a floor and, on failure, names the pair and prints the actual ratio
// so a regression is self-describing rather than a bare "expected ≥ 2.0".
function expectContrast(pair: string, fg: Rgb, bg: Rgb, floor: number): void {
  const ratio = contrast(fg, bg);
  expect(ratio, `${pair}: ${ratio.toFixed(3)}:1 — need ≥ ${floor}:1`).toBeGreaterThanOrEqual(floor);
}

describe('canvas surface ramp — dark theme', () => {
  const canvas = token(dark, 'graph-canvas');
  const node = token(dark, 'graph-node');
  const nodeBorder = token(dark, 'graph-node-border');
  const grid = token(dark, 'graph-grid');
  const panelBorder = token(dark, 'graph-panel-border');

  it('node fill sits 1.20:1 above the canvas', () => {
    expectContrast('--graph-node vs --graph-canvas', node, canvas, 1.2);
  });

  it('node border sits 2.00:1 above the canvas', () => {
    expectContrast('--graph-node-border vs --graph-canvas', nodeBorder, canvas, 2.0);
  });

  it('node border sits 1.70:1 above the node fill', () => {
    expectContrast('--graph-node-border vs --graph-node', nodeBorder, node, 1.7);
  });

  it('dot grid (0.45 over canvas) sits 1.30:1 above the canvas', () => {
    expectContrast('--graph-grid @0.45 vs --graph-canvas', over(grid, canvas, 0.45), canvas, 1.3);
  });

  it('panel border sits 2.00:1 above the canvas', () => {
    expectContrast('--graph-panel-border vs --graph-canvas', panelBorder, canvas, 2.0);
  });
});

describe('canvas surface ramp — light theme', () => {
  const canvas = token(light, 'graph-canvas');
  const node = token(light, 'graph-node');
  const nodeBorder = token(light, 'graph-node-border');
  const grid = token(light, 'graph-grid');

  // Light mode recesses white cards onto an off-white (94%) canvas, so the
  // node↔canvas recess tops out near 1.15:1 by design — the node *border* is
  // what carries light-mode contrast. The floor is 1.10, not 1.20.
  it('node fill sits 1.10:1 above the canvas', () => {
    expectContrast('--graph-node vs --graph-canvas', node, canvas, 1.1);
  });

  it('node border sits 1.70:1 above the canvas', () => {
    expectContrast('--graph-node-border vs --graph-canvas', nodeBorder, canvas, 1.7);
  });

  it('node border sits 1.70:1 above the node fill', () => {
    expectContrast('--graph-node-border vs --graph-node', nodeBorder, node, 1.7);
  });

  it('dot grid (0.55 over canvas) sits 1.30:1 above the canvas', () => {
    expectContrast('--graph-grid @0.55 vs --graph-canvas', over(grid, canvas, 0.55), canvas, 1.3);
  });
});

describe('canvas surface ramp — recess below the page background', () => {
  it('recesses the canvas below --background in both themes', () => {
    for (const [label, theme] of [['dark', dark], ['light', light]] as const) {
      const canvas = token(theme, 'graph-canvas');
      const background = token(theme, 'background');
      expect(
        luminance(canvas),
        `${label}: --graph-canvas should be darker than --background, got ${luminance(canvas).toFixed(3)} vs ${luminance(background).toFixed(3)}`,
      ).toBeLessThan(luminance(background));
    }
  });
});

describe('app surface ramp — cards must read as raised off the page', () => {
  // The same defect the canvas ramp fixed existed on every other screen: a card
  // sat 1.059:1 above the page in dark and 1.045:1 in light, which is below the
  // threshold where an edge reads as depth rather than as a rendering artefact.
  // On a dark ground elevation is carried by surface lightness, not by shadow,
  // so these floors are the only thing keeping cards from flattening again.
  it('raises --card above --background in both themes', () => {
    expectContrast('dark: --card vs --background', token(dark, 'card'), token(dark, 'background'), 1.12);
    expectContrast('light: --card vs --background', token(light, 'card'), token(light, 'background'), 1.10);
  });

  it('raises --popover above --card, so layered surfaces stay distinguishable', () => {
    // Light deliberately leaves both white — a popover there is separated by its
    // shadow and border, which do read on a light ground.
    expectContrast('dark: --popover vs --card', token(dark, 'popover'), token(dark, 'card'), 1.05);
  });

  it('keeps the sidebar recessed below the page in both themes', () => {
    for (const [label, theme] of [['dark', dark], ['light', light]] as const) {
      expect(
        luminance(token(theme, 'sidebar')),
        `${label}: --sidebar should be darker than --background`,
      ).toBeLessThan(luminance(token(theme, 'background')));
    }
  });
});
