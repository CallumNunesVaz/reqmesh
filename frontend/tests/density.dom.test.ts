/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach } from 'vitest';
import { applyDensity } from '../src/components/DensityProvider';

/**
 * `applyDensity` is what turns the store's `density` into the `data-density`
 * attribute on `<html>`. `compact` sets it; `comfortable` *removes* it rather
 * than setting it to a value, so the CSS only ever matches the one non-default
 * state.
 */
describe('data-density attribute', () => {
  afterEach(() => {
    delete document.documentElement.dataset.density;
  });

  it('sets the attribute for compact', () => {
    applyDensity(document.documentElement, 'compact');
    expect(document.documentElement.getAttribute('data-density')).toBe('compact');
  });

  it('removes the attribute for comfortable rather than setting it', () => {
    document.documentElement.dataset.density = 'compact';
    applyDensity(document.documentElement, 'comfortable');
    expect(document.documentElement.hasAttribute('data-density')).toBe(false);
  });
});
