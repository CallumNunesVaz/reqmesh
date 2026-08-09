import { useCallback } from 'react'
import { useConfirm } from '../components/ConfirmDialog'
import { useToasts } from '../components/Toast'
import { useStore } from '../store'
import { useUndoStore } from '../store/undo'
import { bulkDeleteUndo, bulkUpdateUndo } from '../lib/bulkUndo'

export function useBulkActions(opts: {
  clearSelection: () => void
  reload: () => void
}) {
  const showConfirm = useConfirm()
  const { addToast } = useToasts()
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion)
  const bumpDataVersion = useStore((s) => s.bumpDataVersion)
  const { clearSelection, reload } = opts

  const runBulkDelete = useCallback(
    async <T>(args: {
      noun: string
      ids: string[]
      saved: T[]
      idOf: (item: T) => string
      remove: (ids: string[]) => Promise<unknown>
      recreate: (item: T) => Promise<unknown>
    }) => {
      const s = args.ids.length === 1 ? '' : 's'
      const ok = await showConfirm(
        `Delete ${args.ids.length} ${args.noun}${s}? Undo restores the records themselves; links pointing at them from other records are not restored.`,
        'Bulk Delete',
      )
      if (!ok) return

      try {
        await args.remove(args.ids)
        useUndoStore.getState().push(
          bulkDeleteUndo({
            label: `${args.ids.length} ${args.noun}${s}`,
            saved: args.saved,
            recreate: args.recreate,
            remove: args.remove,
            idOf: args.idOf,
          }),
        )
        bumpGraphVersion()
        bumpDataVersion()
        clearSelection()
        reload()
      } catch (e: any) {
        addToast('error', e?.message || 'Bulk delete failed')
      }
    },
    [showConfirm, addToast, bumpGraphVersion, bumpDataVersion, clearSelection, reload],
  )

  const runBulkUpdate = useCallback(
    async (args: {
      label: string
      ids: string[]
      before: Record<string, Record<string, unknown>>
      updates: Record<string, unknown>
      apply: (ids: string[], updates: Record<string, unknown>) => Promise<unknown>
      applyOne: (id: string, updates: Record<string, unknown>) => Promise<unknown>
    }) => {
      try {
        await args.apply(args.ids, args.updates)
        useUndoStore.getState().push(
          bulkUpdateUndo({
            label: args.label,
            before: args.before,
            updates: args.updates,
            apply: args.apply,
            applyOne: args.applyOne,
          }),
        )
        bumpGraphVersion()
        bumpDataVersion()
        clearSelection()
        reload()
      } catch (e: any) {
        addToast('error', e?.message || 'Bulk update failed')
      }
    },
    [addToast, bumpGraphVersion, bumpDataVersion, clearSelection, reload],
  )

  return { runBulkDelete, runBulkUpdate }
}
