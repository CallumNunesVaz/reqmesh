import { useCallback } from 'react';
import { Link, useNavigate, type LinkProps, type To } from 'react-router-dom';
import { useStore } from '../store';

/**
 * A `navigate()` that first consults the registered unsaved-changes guard
 * (see `store.navGuard`) and aborts if the user chooses to keep editing.
 * Falls straight through to a normal navigate when no guard is registered.
 */
export function useGuardedNavigate() {
  const navigate = useNavigate();
  const navGuard = useStore((s) => s.navGuard);
  return useCallback(async (to: To) => {
    if (navGuard) {
      const ok = await navGuard();
      if (!ok) return;
    }
    navigate(to);
  }, [navGuard, navigate]);
}

/**
 * Drop-in replacement for react-router's `<Link>` that routes its click
 * through the unsaved-changes guard. Modified clicks (open in new tab/window,
 * middle-click) pass through untouched so they keep their native behaviour.
 */
export function GuardedLink({ to, onClick, replace, state, ...rest }: LinkProps) {
  const navigate = useNavigate();
  const navGuard = useStore((s) => s.navGuard);
  return (
    <Link
      to={to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
        if (!navGuard) return;
        e.preventDefault();
        Promise.resolve(navGuard()).then((ok) => { if (ok) navigate(to, { replace, state }); });
      }}
      {...rest}
    />
  );
}
