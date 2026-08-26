/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';
import Reveal from '../src/components/Reveal';

afterEach(cleanup);

/** A controllable `prefers-reduced-motion` so the live-change path is testable
 *  — that is the part most likely to be written as a one-shot read. */
function stubMatchMedia(initial: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  let matches = initial;
  const mq = {
    get matches() { return matches; },
    media: '(prefers-reduced-motion: reduce)',
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => { listeners.add(cb); },
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => { listeners.delete(cb); },
    // framer-motion reads prefers-reduced-motion through the *legacy*
    // addListener/removeListener API, so a stub with only the modern one
    // crashes on mount rather than failing an assertion.
    addListener: (cb: (e: MediaQueryListEvent) => void) => { listeners.add(cb); },
    removeListener: (cb: (e: MediaQueryListEvent) => void) => { listeners.delete(cb); },
    onchange: null,
    dispatchEvent: () => true,
  };
  window.matchMedia = vi.fn().mockReturnValue(mq) as unknown as typeof window.matchMedia;
  return {
    set(next: boolean) {
      matches = next;
      act(() => { listeners.forEach((cb) => cb({ matches: next } as MediaQueryListEvent)); });
    },
  };
}

beforeEach(() => { stubMatchMedia(false); });

describe('Reveal', () => {
  it('renders its children and passes className through', () => {
    render(<Reveal className="card p-5"><p>body</p></Reveal>);
    expect(screen.getByText('body')).toBeTruthy();
    expect(document.querySelector('.card.p-5')).toBeTruthy();
  });

  it('animates when motion is allowed', () => {
    render(<Reveal className="x"><p>body</p></Reveal>);
    // framer-motion applies the initial state inline before animating.
    const el = document.querySelector('.x') as HTMLElement;
    expect(el.style.opacity).not.toBe('');
  });

  it('renders no animation at all when reduced motion is preferred', () => {
    stubMatchMedia(true);
    render(<Reveal className="y"><p>body</p></Reveal>);
    const el = document.querySelector('.y') as HTMLElement;
    // "Reduce" means remove: no opacity ramp and no transform, not a faster one.
    expect(el.style.opacity).toBe('');
    expect(el.style.transform).toBe('');
  });

  it('reacts to the setting changing while mounted', () => {
    const mq = stubMatchMedia(false);
    render(<Reveal className="z"><p>body</p></Reveal>);
    expect((document.querySelector('.z') as HTMLElement).style.opacity).not.toBe('');
    mq.set(true);
    expect((document.querySelector('.z') as HTMLElement).style.opacity).toBe('');
  });
});
