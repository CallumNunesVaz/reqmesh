import { describe, it, expect, vi } from 'vitest'
import { bulkDeleteUndo, bulkUpdateUndo } from '../src/lib/bulkUndo'

describe('bulkDeleteUndo', () => {
  it('undo calls recreate once per saved item in order', async () => {
    const saved = [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }]
    const recreate = vi.fn().mockResolvedValue(undefined)
    const remove = vi.fn()
    const idOf = (item: { id: string }) => item.id

    const entry = bulkDeleteUndo({
      label: '2 items',
      saved,
      recreate,
      remove,
      idOf,
    })

    await entry.undo()
    expect(recreate).toHaveBeenCalledTimes(2)
    expect(recreate).toHaveBeenNthCalledWith(1, saved[0])
    expect(recreate).toHaveBeenNthCalledWith(2, saved[1])
  })

  it('redo calls remove once with all ids', async () => {
    const saved = [{ id: 'a' }, { id: 'b' }]
    const recreate = vi.fn()
    const remove = vi.fn().mockResolvedValue(undefined)
    const idOf = (item: { id: string }) => item.id

    const entry = bulkDeleteUndo({
      label: '2 items',
      saved,
      recreate,
      remove,
      idOf,
    })

    await entry.redo()
    expect(remove).toHaveBeenCalledTimes(1)
    expect(remove).toHaveBeenCalledWith(['a', 'b'])
  })

  it('description carries the (partial undo) suffix', () => {
    const saved = [{ id: 'a' }]
    const recreate = vi.fn()
    const remove = vi.fn()
    const idOf = (item: { id: string }) => item.id

    const entry = bulkDeleteUndo({
      label: '3 risks',
      saved,
      recreate,
      remove,
      idOf,
    })

    expect(entry.description).toBe('Delete 3 risks (partial undo)')
  })

  it('a rejecting recreate propagates out of undo()', async () => {
    const saved = [{ id: 'a' }]
    const error = new Error('create failed')
    const recreate = vi.fn().mockRejectedValue(error)
    const remove = vi.fn()
    const idOf = (item: { id: string }) => item.id

    const entry = bulkDeleteUndo({
      label: '1 item',
      saved,
      recreate,
      remove,
      idOf,
    })

    await expect(entry.undo()).rejects.toThrow('create failed')
  })

  it('empty saved list produces an entry whose undo/redo make no calls', async () => {
    const recreate = vi.fn()
    const remove = vi.fn()
    const idOf = (item: { id: string }) => item.id

    const entry = bulkDeleteUndo({
      label: '0 items',
      saved: [],
      recreate,
      remove,
      idOf,
    })

    await entry.undo()
    expect(recreate).not.toHaveBeenCalled()
    await entry.redo()
    expect(remove).toHaveBeenCalledWith([])
  })
})

describe('bulkUpdateUndo', () => {
  it('undo calls applyOne once per id with that ids own prior values', async () => {
    const before: Record<string, Record<string, unknown>> = {
      'a': { status: 'open', priority: 'high' },
      'b': { status: 'closed', priority: 'low' },
    }
    const apply = vi.fn()
    const applyOne = vi.fn().mockResolvedValue(undefined)

    const entry = bulkUpdateUndo({
      label: 'status on 2 items',
      before,
      updates: { status: 'in_review' },
      apply,
      applyOne,
    })

    await entry.undo()
    expect(applyOne).toHaveBeenCalledTimes(2)
    expect(applyOne).toHaveBeenCalledWith('a', { status: 'open', priority: 'high' })
    expect(applyOne).toHaveBeenCalledWith('b', { status: 'closed', priority: 'low' })
  })

  it('redo calls apply once with all ids and original updates', async () => {
    const before: Record<string, Record<string, unknown>> = {
      'a': { status: 'open' },
      'b': { status: 'closed' },
    }
    const apply = vi.fn().mockResolvedValue(undefined)
    const applyOne = vi.fn()

    const entry = bulkUpdateUndo({
      label: 'status on 2 items',
      before,
      updates: { status: 'in_review' },
      apply,
      applyOne,
    })

    await entry.redo()
    expect(apply).toHaveBeenCalledTimes(1)
    expect(apply).toHaveBeenCalledWith(['a', 'b'], { status: 'in_review' })
  })

  it('a rejecting apply propagates out of undo()', async () => {
    const before: Record<string, Record<string, unknown>> = {
      'a': { status: 'open' },
    }
    const apply = vi.fn()
    const error = new Error('update failed')
    const applyOne = vi.fn().mockRejectedValue(error)

    const entry = bulkUpdateUndo({
      label: 'status on 1 item',
      before,
      updates: { status: 'closed' },
      apply,
      applyOne,
    })

    await expect(entry.undo()).rejects.toThrow('update failed')
  })

  it('empty before map produces an entry whose undo/redo make no calls', async () => {
    const apply = vi.fn()
    const applyOne = vi.fn()

    const entry = bulkUpdateUndo({
      label: 'status',
      before: {},
      updates: { status: 'closed' },
      apply,
      applyOne,
    })

    await entry.undo()
    expect(applyOne).not.toHaveBeenCalled()
    await entry.redo()
    expect(apply).toHaveBeenCalledWith([], { status: 'closed' })
  })

  it('description is "Set <label>"', () => {
    const before: Record<string, Record<string, unknown>> = { a: {} }
    const apply = vi.fn()
    const applyOne = vi.fn()

    const entry = bulkUpdateUndo({
      label: 'status on 3 risks',
      before,
      updates: { status: 'closed' },
      apply,
      applyOne,
    })

    expect(entry.description).toBe('Set status on 3 risks')
  })
})
