export interface UndoEntry {
  description: string
  undo: () => Promise<void>
  redo: () => Promise<void>
}

export function bulkDeleteUndo<T>(args: {
  label: string
  saved: T[]
  recreate: (item: T) => Promise<unknown>
  remove: (ids: string[]) => Promise<unknown>
  idOf: (item: T) => string
}): UndoEntry {
  const ids = args.saved.map(args.idOf)
  return {
    description: `Delete ${args.label} (partial undo)`,
    undo: async () => {
      for (const item of args.saved) {
        await args.recreate(item)
      }
    },
    redo: async () => {
      await args.remove(ids)
    },
  }
}

export function bulkUpdateUndo(args: {
  label: string
  before: Record<string, Record<string, unknown>>
  updates: Record<string, unknown>
  apply: (ids: string[], updates: Record<string, unknown>) => Promise<unknown>
  applyOne: (id: string, updates: Record<string, unknown>) => Promise<unknown>
}): UndoEntry {
  const ids = Object.keys(args.before)
  return {
    description: `Set ${args.label}`,
    undo: async () => {
      for (const [id, prior] of Object.entries(args.before)) {
        await args.applyOne(id, prior)
      }
    },
    redo: async () => {
      await args.apply(ids, args.updates)
    },
  }
}
