import { describe, it, expect, vi, beforeEach } from 'vitest';

// `getElk()` memoises its engine in module state and only ever constructs it
// once per page load, so each test starts from a freshly imported module to
// keep the singleton (and its one-time fallback warning) isolated.
async function importGetElk() {
  const { getElk } = await import('../src/components/GraphPane');
  return getElk;
}

const smallGraph = {
  id: 'root',
  layoutOptions: { 'elk.algorithm': 'layered' },
  children: [
    { id: 'a', width: 100, height: 50 },
    { id: 'b', width: 100, height: 50 },
    { id: 'c', width: 100, height: 50 },
  ],
  edges: [
    { id: 'e1', sources: ['a'], targets: ['b'] },
    { id: 'e2', sources: ['b'], targets: ['c'] },
  ],
};

describe('getElk', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('returns the same instance when called twice', async () => {
    const getElk = await importGetElk();
    const first = await getElk();
    const second = await getElk();
    expect(first).toBe(second);
  });

  it('lays out a small graph and returns positions for every node', async () => {
    const getElk = await importGetElk();
    const elk = await getElk();
    const res = await elk.layout(smallGraph);
    const placed = new Map<string, { x: number; y: number }>();
    for (const child of res.children ?? []) {
      placed.set(child.id, { x: child.x, y: child.y });
    }
    expect([...placed.keys()].sort()).toEqual(['a', 'b', 'c']);
    for (const id of ['a', 'b', 'c']) {
      expect(Number.isFinite(placed.get(id)?.x)).toBe(true);
      expect(Number.isFinite(placed.get(id)?.y)).toBe(true);
    }
  });

  it('falls back to the in-process engine when the worker cannot start, logging once', async () => {
    const getElk = await importGetElk();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      // No real Worker exists in this test environment, so worker construction
      // throws and the fallback branch must produce a working engine.
      const elk = await getElk();
      const res = await elk.layout(smallGraph);
      expect((res.children ?? []).map((c: { id: string }) => c.id).sort()).toEqual(['a', 'b', 'c']);

      // Re-requesting the engine must not re-attempt worker construction, so
      // the fallback is logged once, not once per layout.
      await getElk();
      expect(warn).toHaveBeenCalledTimes(1);
    } finally {
      warn.mockRestore();
    }
  });
});
