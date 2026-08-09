/** Undo entries for bulk actions.
 *
 *  Pure on purpose — the caller injects the API calls, so this is testable with
 *  fakes under the node-environment vitest setup, which has no jsdom and cannot
 *  render a hook or a component.
 */

export interface UndoEntry {
  description: string;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

/**
 * Undo for a bulk delete.
 *
 * The `(partial undo)` suffix is not decoration. Recreating the records cannot
 * restore the links other records had pointing at them, because the delete does
 * not rewrite referring rows — so the description has to say so, since it is
 * what the undo toast shows.
 */
export function bulkDeleteUndo<T>(args: {
  label: string;
  saved: T[];
  recreate: (item: T) => Promise<unknown>;
  remove: (ids: string[]) => Promise<unknown>;
  idOf: (item: T) => string;
}): UndoEntry {
  const ids = args.saved.map(args.idOf);
  return {
    description: `Delete ${args.label} (partial undo)`,
    undo: async () => {
      // Sequential, in the original order: a parent recreated after its child
      // would leave the child dangling for the duration of the replay.
      for (const item of args.saved) {
        await args.recreate(item);
      }
    },
    redo: async () => {
      await args.remove(ids);
    },
  };
}

/**
 * Undo for a bulk field update.
 *
 * `undo` replays per id from that id's own prior values. A single batched
 * restore would set every row to whichever prior value happened to be first,
 * silently rewriting the rows that differed — which is exactly the class of bug
 * this whole change exists to remove.
 */
export function bulkUpdateUndo(args: {
  label: string;
  before: Record<string, Record<string, unknown>>;
  updates: Record<string, unknown>;
  apply: (ids: string[], updates: Record<string, unknown>) => Promise<unknown>;
  applyOne: (id: string, updates: Record<string, unknown>) => Promise<unknown>;
}): UndoEntry {
  const ids = Object.keys(args.before);
  return {
    description: `Set ${args.label}`,
    undo: async () => {
      for (const [id, prior] of Object.entries(args.before)) {
        await args.applyOne(id, prior);
      }
    },
    redo: async () => {
      await args.apply(ids, args.updates);
    },
  };
}
