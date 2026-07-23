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
  lastTimestamp: 0,

  push: (entry) => {
    set((s) => ({
      undoStack: [...s.undoStack.slice(-(MAX_STACK - 1)), entry],
      redoStack: [],
      lastDescription: entry.description,
      lastTimestamp: Date.now(),
    }));
  },

  undo: async () => {
    const { undoStack } = get();
    if (undoStack.length === 0) return;
    const entry = undoStack[undoStack.length - 1];
    await entry.undo();
    set((s) => ({
      undoStack: s.undoStack.slice(0, -1),
      redoStack: [...s.redoStack, entry],
      lastDescription: `Undid: ${entry.description}`,
      lastTimestamp: Date.now(),
    }));
    _bumpVersions();
  },

  redo: async () => {
    const { redoStack } = get();
    if (redoStack.length === 0) return;
    const entry = redoStack[redoStack.length - 1];
    await entry.redo();
    set((s) => ({
      redoStack: s.redoStack.slice(0, -1),
      undoStack: [...s.undoStack, entry],
      lastDescription: `Redid: ${entry.description}`,
      lastTimestamp: Date.now(),
    }));
    _bumpVersions();
  },

  clear: () => set({ undoStack: [], redoStack: [], lastDescription: null, lastTimestamp: 0 }),

  canUndo: () => get().undoStack.length > 0,
  canRedo: () => get().redoStack.length > 0,
}));
