import { useEffect, useState } from 'react';

/**
 * Whether the user has asked their OS for reduced motion.
 *
 * The app honoured this in exactly two places (`Toast`, `GraphPane`) while 55
 * page-entry animations ignored it, so asking for reduced motion still bought
 * you a staggered slide-in on every page. This is the one implementation those
 * call sites share.
 *
 * The listener matters: a one-shot read at mount means a user toggling the
 * setting while the app is open keeps whatever was true when the component
 * mounted, which for a long-lived SPA can be the whole session.
 */
const QUERY = '(prefers-reduced-motion: reduce)';

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    // Guarded for the node test environment, where matchMedia is absent.
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(QUERY).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    // Re-read on mount: the value can have changed between the initial state
    // and the effect running.
    setReduced(mq.matches);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  return reduced;
}
