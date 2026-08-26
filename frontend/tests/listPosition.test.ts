import { describe, it, expect, beforeEach } from 'vitest';
import {
  listPathFor, readLastEntity, readScroll, saveLastEntity, saveScroll,
} from '../src/lib/listPosition';

/** sessionStorage does not exist in the node test env; this is the smallest
 *  thing that behaves like it, including the throwing case the module guards. */
class MemoryStorage {
  private map = new Map<string, string>();
  private failing = false;
  fail(on: boolean) { this.failing = on; }
  getItem(k: string) { if (this.failing) throw new Error('denied'); return this.map.get(k) ?? null; }
  setItem(k: string, v: string) { if (this.failing) throw new Error('denied'); this.map.set(k, v); }
  clear() { this.map.clear(); }
}

const store = new MemoryStorage();
(globalThis as any).sessionStorage = store;

beforeEach(() => { store.fail(false); store.clear(); });

describe('listPathFor', () => {
  it('maps a requirement detail route back to its list and id', () => {
    expect(listPathFor('/project/cessna-172/requirements/REQM0001')).toEqual({
      listPath: '/project/cessna-172/requirements', id: 'REQM0001',
    });
  });

  it('handles the other two detail routes', () => {
    expect(listPathFor('/project/p/components/COMP0002')?.id).toBe('COMP0002');
    expect(listPathFor('/project/p/risks/RISK0003')?.id).toBe('RISK0003');
  });

  it('returns null for the list route itself', () => {
    expect(listPathFor('/project/cessna-172/requirements')).toBeNull();
  });

  it('returns null for a nested route that is not an entity detail', () => {
    // The guard that stops every two-segment tail being read as an id.
    expect(listPathFor('/project/p/settings/git')).toBeNull();
    expect(listPathFor('/project/p/traces')).toBeNull();
  });

  it('ignores a trailing slash rather than reading it as an empty id', () => {
    expect(listPathFor('/project/p/requirements/')).toBeNull();
  });
});

describe('scroll and entity memory', () => {
  it('round-trips a scroll offset', () => {
    saveScroll('/project/p/requirements', 842.6);
    expect(readScroll('/project/p/requirements')).toBe(843);
  });

  it('distinguishes "at the top" from "never visited"', () => {
    // 0 must survive: falling back to a row scroll for a list the user had
    // deliberately scrolled to the top would move the view for no reason.
    saveScroll('/a', 0);
    expect(readScroll('/a')).toBe(0);
    expect(readScroll('/never-seen')).toBeNull();
  });

  it('keeps offsets and entities per route', () => {
    saveScroll('/project/p/requirements', 100);
    saveScroll('/project/p/risks', 250);
    saveLastEntity('/project/p/requirements', 'REQM0001');
    saveLastEntity('/project/p/risks', 'RISK0009');
    expect(readScroll('/project/p/requirements')).toBe(100);
    expect(readScroll('/project/p/risks')).toBe(250);
    expect(readLastEntity('/project/p/requirements')).toBe('REQM0001');
    expect(readLastEntity('/project/p/risks')).toBe('RISK0009');
  });

  it('survives storage that throws, rather than taking the list down with it', () => {
    // Safari private mode throws on write; failing to remember a scroll offset
    // must never stop a list rendering.
    store.fail(true);
    expect(() => saveScroll('/a', 10)).not.toThrow();
    expect(() => saveLastEntity('/a', 'X')).not.toThrow();
    expect(readScroll('/a')).toBeNull();
    expect(readLastEntity('/a')).toBeNull();
  });

  it('treats a corrupt stored offset as absent', () => {
    saveScroll('/a', 10);
    (globalThis as any).sessionStorage.setItem('reqmesh.listScroll./a', 'not-a-number');
    expect(readScroll('/a')).toBeNull();
  });
});
