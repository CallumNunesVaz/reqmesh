import { useCallback } from 'react';
import { useUndoStore } from '../store/undo';

/**
 * Return a function that wraps an async mutation, automatically pushing an
 * undo/redo command pair onto the global undo stack.
 *
 * Usage:
 *   const pushUndo = useUndoableMutation();
 *   await pushUndo({
 *     description: `Delete requirement ${id}`,
 *     undo: () => api.createRequirement(projectId, savedBefore),
 *     redo: () => api.deleteRequirement(projectId, id),
 *   });
 */
export function useUndoableMutation() {
  const push = useUndoStore((s) => s.push);

  return useCallback(
    async (entry: { description: string; undo: () => Promise<void>; redo: () => Promise<void> }) => {
      push(entry);
    },
    [push],
  );
}
