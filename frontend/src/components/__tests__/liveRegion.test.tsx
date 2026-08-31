/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import { render, act } from '@testing-library/react';
import { LiveRegionProvider, useAnnounce, type Politeness } from '../LiveRegion';

let announce: (message: string, politeness?: Politeness) => void = () => {};

function Grabber() {
  announce = useAnnounce();
  return null;
}

function renderRegion() {
  return render(
    <LiveRegionProvider>
      <Grabber />
    </LiveRegionProvider>,
  );
}

function polite(container: HTMLElement): HTMLElement {
  return container.querySelector('[data-live-region="polite"]') as HTMLElement;
}

function assertive(container: HTMLElement): HTMLElement {
  return container.querySelector('[data-live-region="assertive"]') as HTMLElement;
}

describe('LiveRegionProvider', () => {
  it('renders both regions on first render, before anything is announced', () => {
    const { container } = renderRegion();
    const p = polite(container);
    const a = assertive(container);
    expect(p).not.toBeNull();
    expect(a).not.toBeNull();
    expect(p.textContent).toBe('');
    expect(a.textContent).toBe('');
  });

  it('puts a polite announce in the polite node and an assertive one in the assertive node', () => {
    const { container } = renderRegion();
    act(() => announce('x'));
    expect(polite(container).textContent).toBe('x');
    expect(assertive(container).textContent).toBe('');

    act(() => announce('y', 'assertive'));
    expect(assertive(container).textContent).toBe('y');
    expect(polite(container).textContent).toBe('x');
  });

  it('marks the polite node aria-live=polite and aria-atomic=true', () => {
    const { container } = renderRegion();
    const p = polite(container);
    expect(p.getAttribute('aria-live')).toBe('polite');
    expect(p.getAttribute('aria-atomic')).toBe('true');
    expect(p.tagName).toBe('OUTPUT');
    expect(assertive(container).getAttribute('aria-live')).toBe('assertive');
    // Deliberately NOT role="alert": the node is always mounted, so the role
    // would make `[role=alert]` match permanently. The app reserves that for
    // toasts, and four e2e specs assert on alert counts.
    expect(assertive(container).getAttribute('role')).toBeNull();
  });

  it('announces the same string twice by disambiguating the repeat', () => {
    const { container } = renderRegion();
    act(() => announce('x'));
    expect(polite(container).textContent).toBe('x');
    act(() => announce('x'));
    expect(polite(container).textContent).not.toBe('x');
  });

  it('ignores an empty announce', () => {
    const { container } = renderRegion();
    act(() => announce(''));
    expect(polite(container).textContent).toBe('');
    expect(assertive(container).textContent).toBe('');
  });

  it('hides the regions with sr-only, not display:none or hidden', () => {
    const { container } = renderRegion();
    for (const node of [polite(container), assertive(container)]) {
      expect(node.className).toContain('sr-only');
      expect(node.className).not.toContain('hidden');
      expect(node.getAttribute('hidden')).toBeNull();
      expect(node.style.display).not.toBe('none');
    }
  });
});
