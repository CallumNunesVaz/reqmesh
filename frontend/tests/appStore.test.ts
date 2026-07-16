import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from '../src/store';
import type { Requirement } from '../src/api/client';

const initial = useStore.getState();

beforeEach(() => {
  useStore.setState(initial, true);
});

describe('version counters', () => {
  // The SSE listener bumps these on every change frame; the graph and data
  // views re-fetch when their counter moves.
  it('bumping the graph version leaves the data version alone', () => {
    useStore.getState().bumpGraphVersion();
    expect(useStore.getState().graphVersion).toBe(1);
    expect(useStore.getState().dataVersion).toBe(0);
  });

  it('bumping the data version leaves the graph version alone', () => {
    useStore.getState().bumpDataVersion();
    expect(useStore.getState().dataVersion).toBe(1);
    expect(useStore.getState().graphVersion).toBe(0);
  });

  it('increments monotonically so repeated changes always re-trigger', () => {
    const { bumpGraphVersion } = useStore.getState();
    bumpGraphVersion();
    bumpGraphVersion();
    bumpGraphVersion();
    expect(useStore.getState().graphVersion).toBe(3);
  });
});

describe('setters', () => {
  it('replaces the requirement list', () => {
    const reqs = [{ id: 'REQ-001', name: 'Auth' }] as Requirement[];
    useStore.getState().setRequirements(reqs);
    expect(useStore.getState().requirements).toEqual(reqs);
  });

  it('clears the current project when set to null', () => {
    useStore.getState().setCurrentProject({ id: 'demo', name: 'Demo', path: '/tmp/demo' });
    expect(useStore.getState().currentProject?.id).toBe('demo');
    useStore.getState().setCurrentProject(null);
    expect(useStore.getState().currentProject).toBeNull();
  });

  it('tracks loading and error independently', () => {
    useStore.getState().setLoading(true);
    useStore.getState().setError('boom');
    expect(useStore.getState().loading).toBe(true);
    expect(useStore.getState().error).toBe('boom');
    useStore.getState().setError(null);
    expect(useStore.getState().error).toBeNull();
    expect(useStore.getState().loading).toBe(true);
  });
});
