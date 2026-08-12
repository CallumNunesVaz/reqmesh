import { useCallback, useEffect, useState } from 'react';

/**
 * A moving keyboard cursor over a flat list of ids, for the list-page
 * shortcuts (j/k, Enter, Escape) that `useKeyboardShortcuts` dispatches.
 *
 * The list pages opt in by passing the returned callbacks as the matching
 * `onList*` handler props; this hook owns only the cursor, not the keys.
 *
 * `onOpen` is the page's notion of "open the selected item" — expanding an
 * accordion card on some pages, opening the editor on others.
 */
export function useListSelection(ids: readonly string[], onOpen: (id: string) => void) {
  const [focusId, setFocusId] = useState<string | null>(null);

  const index = focusId ? ids.indexOf(focusId) : -1;

  const onListDown = useCallback(() => {
    if (ids.length === 0) return;
    const next = index < 0 ? 0 : Math.min(index + 1, ids.length - 1);
    setFocusId(ids[next]);
  }, [ids, index]);

  const onListUp = useCallback(() => {
    if (ids.length === 0) return;
    const next = index < 0 ? ids.length - 1 : Math.max(index - 1, 0);
    setFocusId(ids[next]);
  }, [ids, index]);

  const onListOpen = useCallback(() => {
    if (focusId) onOpen(focusId);
  }, [focusId, onOpen]);

  const onListEscape = useCallback(() => setFocusId(null), []);

  // Keep the cursor on screen as j/k move it.
  useEffect(() => {
    if (!focusId) return;
    document.getElementById(`entity-${focusId}`)?.scrollIntoView({ block: 'nearest' });
  }, [focusId]);

  return { focusId, onListDown, onListUp, onListOpen, onListEscape };
}
