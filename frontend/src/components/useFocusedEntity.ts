import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Deep-linking for the list pages.
 *
 * Verification cases, components and specifications have no detail route, so a
 * reference to one navigates to its list page with `?focus=<id>`. This reads
 * that id back, and scrolls the matching row into view once the data has
 * loaded (the row does not exist on the first render, so `ready` gates it).
 *
 * @param ready  true once the list has rendered the row
 * @param onFocus  called once per focused id — select it, expand its ancestors
 */
export function useFocusedEntity(ready: boolean, onFocus?: (id: string) => void) {
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get('focus');
  const handled = useRef<string | null>(null);

  useEffect(() => {
    if (!focusId || !ready || handled.current === focusId) return;
    handled.current = focusId;
    onFocus?.(focusId);
    // Let the callback's state change paint before scrolling to the row.
    requestAnimationFrame(() => {
      document.getElementById(`entity-${focusId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }, [focusId, ready, onFocus]);

  return focusId;
}
