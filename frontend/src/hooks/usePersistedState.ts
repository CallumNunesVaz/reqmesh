import { useEffect, useRef, useState } from 'react';

/**
 * useState whose value survives navigating away and back — and a reload —
 * scoped to `key`. The app already did this ad hoc in a handful of places
 * (Layout's nav width and canvas/inspector split, GraphPane's per-project view
 * settings); this factors it out because the same reset was about to be fixed
 * five times over: every list page's filters and collapsed/expanded tree state
 * lived in a plain `useState`, so navigating off a configured list and back
 * silently dropped it back to nothing.
 *
 * `key` should already be unique per project where the value is project-scoped
 * — callers interpolate the id themselves, matching every other `rt-*` key in
 * this codebase (e.g. `` `rt-reqs-collapsed-${projectId}` ``). Pass `null` to
 * opt out of persistence for one render (an id not loaded yet); the state
 * still works, it just isn't written anywhere.
 *
 * `codec` is only needed for values `JSON.stringify` cannot round-trip as-is —
 * a `Set`, most commonly. See `setCodec` below.
 */
export function usePersistedState<T>(
  key: string | null,
  initial: T,
  codec?: { toJSON: (value: T) => unknown; fromJSON: (value: any) => T },
): [T, (value: T | ((prev: T) => T)) => void] {
  const toJSON = codec?.toJSON ?? ((v: T) => v as unknown);
  const fromJSON = codec?.fromJSON ?? ((v: any) => v as T);

  const read = (k: string | null): T => {
    if (!k) return initial;
    try {
      const raw = localStorage.getItem(k);
      return raw === null ? initial : fromJSON(JSON.parse(raw));
    } catch {
      // Either localStorage is unavailable (private-browsing edge cases in
      // some browsers) or the stored value predates a shape change — either
      // way, falling back to `initial` is correct and not worth surfacing.
      return initial;
    }
  };

  const [value, setValue] = useState<T>(() => read(key));

  // `key` changes when the operator switches project; re-read rather than
  // carry one project's filters/collapse-state onto another's id space.
  const prevKey = useRef(key);
  useEffect(() => {
    if (prevKey.current === key) return;
    prevKey.current = key;
    setValue(read(key));
    // `read`/`fromJSON` are recreated each render from the caller's codec, so
    // including them would re-run this on every render regardless of `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = (v: T | ((prev: T) => T)) => {
    setValue((prev) => {
      const next = typeof v === 'function' ? (v as (p: T) => T)(prev) : v;
      if (key) {
        try { localStorage.setItem(key, JSON.stringify(toJSON(next))); } catch { /* storage full/unavailable */ }
      }
      return next;
    });
  };

  return [value, set];
}

/** Codec for `usePersistedState<Set<T>>` — JSON has no native Set. */
export function setCodec<T>() {
  return {
    toJSON: (v: Set<T>) => Array.from(v),
    fromJSON: (v: T[]) => new Set(Array.isArray(v) ? v : []),
  };
}
