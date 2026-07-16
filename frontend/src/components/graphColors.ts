// Colour helpers for the graph nodes. Status/priority colours are authored as
// legacy comma-separated `hsl(h,s%,l%)`, which these keep working with.

/** Turn an `hsl(h,s%,l%)` status colour into a translucent glow colour so nodes
 *  can cast a soft, status-tinted bloom. Legacy comma-hsl in → hsla out. */
export function glow(hslColor: string, alpha: number): string {
  return hslColor.replace('hsl(', 'hsla(').replace(/\)$/, `, ${alpha})`);
}

const HSL_RE = /^hsl\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)$/;

/** Shift an `hsl()` colour's lightness by `delta` percentage points, clamped to
 *  0–100. Used to derive the highlight/shade stops of a node's fill gradient
 *  from its single status colour. Unparseable colours pass through. */
export function shiftLightness(hslColor: string, delta: number): string {
  const m = hslColor.match(HSL_RE);
  if (!m) return hslColor;
  const [, h, s, l] = m;
  const lightness = Math.min(100, Math.max(0, Number(l) + delta));
  return `hsl(${h},${s}%,${lightness}%)`;
}
