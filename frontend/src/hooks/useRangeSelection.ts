import { useCallback, useRef, useState } from 'react';
import { nextAnchor, nextSelection, type SelectionModifiers } from '../lib/rangeSelection';

/**
 * Set-based list selection with Shift-range and Ctrl/Cmd-toggle.
 *
 * A thin wrapper over the pure helpers in `lib/rangeSelection` — the semantics
 * (and the reasoning behind them) live there, and are tested without a DOM.
 */
export interface RangeSelection {
  selectedIds: Set<string>;
  /** Handle a click on a row, honouring Shift / Ctrl / Cmd. */
  select: (id: string, event?: SelectionModifiers) => void;
  /** Replace the selection outright — select-all, or a filtered subset. */
  setSelectedIds: (ids: Set<string>) => void;
  clear: () => void;
}

/** `orderedIds` must be the ids in display order, after filtering/collapsing. */
export function useRangeSelection(orderedIds: readonly string[]): RangeSelection {
  const [selectedIds, setSelected] = useState<Set<string>>(new Set());
  const anchorRef = useRef<string | null>(null);

  const select = useCallback((id: string, event?: SelectionModifiers) => {
    setSelected((prev) => nextSelection(orderedIds, prev, id, anchorRef.current, event));
    anchorRef.current = nextAnchor(id, anchorRef.current, event);
  }, [orderedIds]);

  const setSelectedIds = useCallback((ids: Set<string>) => {
    setSelected(ids);
    if (ids.size === 0) anchorRef.current = null;
  }, []);

  const clear = useCallback(() => {
    setSelected(new Set());
    anchorRef.current = null;
  }, []);

  return { selectedIds, select, setSelectedIds, clear };
}
