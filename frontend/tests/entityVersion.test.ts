/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStore, useEntityVersion } from '../src/store';

describe('entity-scoped invalidation', () => {
  it('bumps only the named collection', () => {
    const before = useStore.getState().entityVersions;
    act(() => { useStore.getState().bumpEntityVersion('risks'); });
    const after = useStore.getState().entityVersions;
    expect(after.risks).toBe((before.risks ?? 0) + 1);
    expect(after.requirements ?? 0).toBe(before.requirements ?? 0);
  });

  it('useEntityVersion changes for a subscribed collection and not for others', () => {
    const { result } = renderHook(() => useEntityVersion('requirements'));
    const initial = result.current;

    act(() => { useStore.getState().bumpEntityVersion('risks'); });
    expect(result.current).toBe(initial);

    act(() => { useStore.getState().bumpEntityVersion('requirements'); });
    expect(result.current).toBe(initial + 1);
  });

  it('still observes the global dataVersion (local mutations / unattributed changes)', () => {
    const { result } = renderHook(() => useEntityVersion('requirements'));
    const initial = result.current;
    act(() => { useStore.getState().bumpDataVersion(); });
    expect(result.current).toBe(initial + 1);
  });
});
