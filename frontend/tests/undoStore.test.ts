import { describe, it, expect, beforeEach } from 'vitest';
import { useUndoStore } from '../src/store/undo';

const ok = (log: string[], name: string) => ({
  description: name,
  undo: async () => { log.push(`undo:${name}`); },
  redo: async () => { log.push(`redo:${name}`); },
});

const failing = (name: string, message = 'server said no') => ({
  description: name,
  undo: async () => { throw new Error(message); },
  redo: async () => { throw new Error(message); },
});

describe('undo store', () => {
  beforeEach(() => useUndoStore.getState().clear());

  it('undoes and redoes in order', async () => {
    const log: string[] = [];
    const s = useUndoStore.getState();
    s.push(ok(log, 'first'));
    s.push(ok(log, 'second'));

    await useUndoStore.getState().undo();
    expect(log).toEqual(['undo:second']);
    expect(useUndoStore.getState().canRedo()).toBe(true);

    await useUndoStore.getState().redo();
    expect(log).toEqual(['undo:second', 'redo:second']);
  });

  // BUG-7: a throwing entry was never popped, so every later press retried the
  // same doomed entry and all older history became permanently unreachable.
  it('pops a failed undo instead of wedging the stack', async () => {
    const log: string[] = [];
    const s = useUndoStore.getState();
    s.push(ok(log, 'older'));
    s.push(failing('doomed'));

    await useUndoStore.getState().undo();          // fails
    expect(useUndoStore.getState().undoStack).toHaveLength(1);
    expect(useUndoStore.getState().lastError).toMatch(/server said no/);

    await useUndoStore.getState().undo();          // must reach the older entry
    expect(log).toEqual(['undo:older']);
    expect(useUndoStore.getState().canUndo()).toBe(false);
  });

  it('does not offer a failed undo for redo', async () => {
    useUndoStore.getState().push(failing('doomed'));
    await useUndoStore.getState().undo();
    expect(useUndoStore.getState().canRedo()).toBe(false);
  });

  it('pops a failed redo too', async () => {
    const log: string[] = [];
    const s = useUndoStore.getState();
    s.push(ok(log, 'a'));
    await useUndoStore.getState().undo();

    // Swap in an entry whose redo throws.
    useUndoStore.setState({ redoStack: [failing('boom')] });
    await useUndoStore.getState().redo();
    expect(useUndoStore.getState().redoStack).toHaveLength(0);
    expect(useUndoStore.getState().lastError).toBeTruthy();
  });

  it('clears the error on the next successful action', async () => {
    const log: string[] = [];
    const s = useUndoStore.getState();
    s.push(failing('doomed'));
    await useUndoStore.getState().undo();
    expect(useUndoStore.getState().lastError).toBeTruthy();

    useUndoStore.getState().push(ok(log, 'fresh'));
    expect(useUndoStore.getState().lastError).toBeNull();
  });

  it('reports the failure through lastDescription', async () => {
    useUndoStore.getState().push(failing('Delete REQ-001'));
    await useUndoStore.getState().undo();
    expect(useUndoStore.getState().lastDescription).toContain('Delete REQ-001');
    expect(useUndoStore.getState().lastDescription).toMatch(/could not/i);
  });
});
