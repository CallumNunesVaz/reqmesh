// Semantic zoom for the diagram canvas: detail scales with altitude, so the
// diagram is readable at every zoom instead of one fixed drawing. Five levels,
// from far-out structure to full SysML block detail.

export type ZoomLevel = 1 | 2 | 3 | 4 | 5;

/** Zoom thresholds between levels; index i is the minimum zoom for level i+2. */
export const LEVEL_THRESHOLDS = [0.35, 0.6, 0.9, 1.35] as const;

export const LEVEL_LABELS: Record<ZoomLevel, string> = {
  1: 'Structure',
  2: 'Blocks',
  3: 'Typed',
  4: 'Parameters',
  5: 'Full detail',
};

/** Bucket a canvas zoom factor into one of the five semantic levels. */
export function zoomLevel(zoom: number): ZoomLevel {
  if (zoom < LEVEL_THRESHOLDS[0]) return 1;
  if (zoom < LEVEL_THRESHOLDS[1]) return 2;
  if (zoom < LEVEL_THRESHOLDS[2]) return 3;
  if (zoom < LEVEL_THRESHOLDS[3]) return 4;
  return 5;
}

/**
 * Map-label scale for far-out altitudes: text grows inversely with zoom so
 * names stay readable at any distance. Quantised to quarter steps so node
 * re-renders happen on scale changes, not on every wheel tick.
 */
export function labelScale(zoom: number, max = 2.5): number {
  if (zoom >= 0.6) return 1;
  return Math.min(max, Math.max(1, Math.round((0.5 / zoom) * 4) / 4));
}
