import { create } from 'zustand';
import { useStore } from './index';

interface UndoEntry {
  description: string;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

interface UndoState {
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];
  lastDescription: string | null;
  /** Set when the most recent undo/redo failed; cleared on the next success. */
  lastError: string | null;
  lastTimestamp: number;
  push: (entry: UndoEntry) => void;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  clear: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

const MAX_STACK = 100;

function _bumpVersions() {
  useStore.getState().bumpGraphVersion();
  useStore.getState().bumpDataVersion();
}

export const useUndoStore = create<UndoState>((set, get) => ({
  undoStack: [],
  redoStack: [],
  lastDescription: null,
  lastError: null,
  lastTimestamp: 0,

  push: (entry) => {
    set((s) => ({
      undoStack: [...s.undoStack.slice(-(MAX_STACK - 1)), entry],
      redoStack: [],
      lastDescription: entry.description,
      lastError: null,
      lastTimestamp: Date.now(),
    }));
  },

  // Both directions pop the entry even when it fails. Leaving a failed entry
  // on top wedged the stack: the next press retried the same doomed entry, so
  // all older history became permanently unreachable — silently, because the
  // rejection was an unhandled promise with no UI feedback. A failure is
  // reported through `lastError` and the entry is discarded, since it can no
  // longer be applied to the server's current state.
  undo: async () => {
    const { undoStack } = get();
    if (undoStack.length === 0) return;
    const entry = undoStack[undoStack.length - 1];
    let failure: string | null = null;
    try {
      await entry.undo();
    } catch (err: any) {
      failure = err?.message || 'Undo failed';
    }
    set((s) => ({
      undoStack: s.undoStack.slice(0, -1),
      redoStack: failure ? s.redoStack : [...s.redoStack, entry],
      lastDescription: failure ? `Could not undo: ${entry.description}` : `Undid: ${entry.description}`,
      lastError: failure,
      lastTimestamp: Date.now(),
    }));
    _bumpVersions();
  },

  redo: async () => {
    const { redoStack } = get();
    if (redoStack.length === 0) return;
    const entry = redoStack[redoStack.length - 1];
    let failure: string | null = null;
    try {
      await entry.redo();
    } catch (err: any) {
      failure = err?.message || 'Redo failed';
    }
    set((s) => ({
      redoStack: s.redoStack.slice(0, -1),
      undoStack: failure ? s.undoStack : [...s.undoStack, entry],
      lastDescription: failure ? `Could not redo: ${entry.description}` : `Redid: ${entry.description}`,
      lastError: failure,
      lastTimestamp: Date.now(),
    }));
    _bumpVersions();
  },

  clear: () => set({ undoStack: [], redoStack: [], lastDescription: null, lastError: null, lastTimestamp: 0 }),

  canUndo: () => get().undoStack.length > 0,
  canRedo: () => get().redoStack.length > 0,
}));
