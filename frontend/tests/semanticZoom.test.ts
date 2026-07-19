import { describe, it, expect } from 'vitest';
import { zoomLevel, labelScale, LEVEL_THRESHOLDS, LEVEL_LABELS } from '../src/components/semanticZoom';

describe('semantic zoom levels', () => {
  it('buckets the full zoom range into the five levels', () => {
    expect(zoomLevel(0.15)).toBe(1);
    expect(zoomLevel(0.4)).toBe(2);
    expect(zoomLevel(0.75)).toBe(3);
    expect(zoomLevel(1.0)).toBe(4);
    expect(zoomLevel(2.0)).toBe(5);
  });

  it('assigns each threshold to the level above it', () => {
    expect(zoomLevel(LEVEL_THRESHOLDS[0])).toBe(2);
    expect(zoomLevel(LEVEL_THRESHOLDS[1])).toBe(3);
    expect(zoomLevel(LEVEL_THRESHOLDS[2])).toBe(4);
    expect(zoomLevel(LEVEL_THRESHOLDS[3])).toBe(5);
  });

  it('is monotonic in zoom', () => {
    let prev = 0;
    for (let z = 0.05; z <= 3; z += 0.05) {
      const level = zoomLevel(z);
      expect(level).toBeGreaterThanOrEqual(prev);
      prev = level;
    }
  });

  it('labels every level', () => {
    for (const level of [1, 2, 3, 4, 5] as const) {
      expect(LEVEL_LABELS[level]).toBeTruthy();
    }
  });
});

describe('map-label scale', () => {
  it('does not scale at reading zoom', () => {
    expect(labelScale(0.6)).toBe(1);
    expect(labelScale(1.5)).toBe(1);
  });

  it('grows inversely with distance, clamped', () => {
    expect(labelScale(0.4)).toBeGreaterThan(1);
    expect(labelScale(0.1)).toBe(2.5);
    expect(labelScale(0.1, 3)).toBe(3);
  });

  it('is quantised to quarter steps', () => {
    for (const z of [0.12, 0.2, 0.33, 0.45, 0.55]) {
      expect((labelScale(z) * 4) % 1).toBe(0);
    }
  });
});
