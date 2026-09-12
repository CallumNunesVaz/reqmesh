import { create } from 'zustand';
import type { Project, Requirement, Specification } from '../api/client';

/** List/table density. `comfortable` is the default and renders exactly as the
 *  app did before the setting existed (the `rt-row` marker is inert at
 *  comfortable); `compact` tightens vertical padding on list rows. */
export type Density = 'comfortable' | 'compact';

// Read once at module load so a saved `compact` is available before first paint
// (the same pre-paint read the theme does in its useState initializer). The
// DOM attribute itself is applied by DensityProvider on mount.
const initialDensity: Density = (() => {
  if (typeof window === 'undefined') return 'comfortable';
  try {
    return localStorage.getItem('rt-density') === 'compact' ? 'compact' : 'comfortable';
  } catch {
    return 'comfortable';
  }
})();

interface AppState {
  projects: Project[];
  currentProject: Project | null;
  requirements: Requirement[];
  specifications: Specification[];
  graphVersion: number;
  dataVersion: number;
  /** Per-collection invalidation counters, bumped when a remote mutation event
   *  names that collection. Pages subscribe via `useEntityVersion(...kinds)`
   *  so one user's edit refreshes only the views that display it. */
  entityVersions: Record<string, number>;
  refocusGraph: number;
  helpersEnabled: boolean;
  /** List/table density — `comfortable` (default) or `compact`. */
  density: Density;
  /** Baselines explicitly hidden in the graph filter — empty = nothing hidden. */
  hiddenBaselines: string[];
  /** Components explicitly hidden in the graph filter — empty = nothing hidden. */
  hiddenComponents: string[];
  /** A page with unsaved edits registers a guard here; navigators await it and
   *  abort when it resolves false (user chose to keep editing). Null = free. */
  navGuard: (() => boolean | Promise<boolean>) | null;
  /** Whether the context pane (right sidebar) is open. */
  contextOpen: boolean;

  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  setRequirements: (requirements: Requirement[]) => void;
  setSpecifications: (specifications: Specification[]) => void;
  bumpGraphVersion: () => void;
  bumpDataVersion: () => void;
  bumpEntityVersion: (kind: string) => void;
  toggleHelpers: () => void;
  setDensity: (density: Density) => void;
  setNavGuard: (fn: (() => boolean | Promise<boolean>) | null) => void;
  setHiddenBaselines: (filters: string[]) => void;
  toggleHiddenBaseline: (name: string) => void;
  setHiddenComponents: (filters: string[]) => void;
  toggleHiddenComponent: (id: string) => void;
  /** Drop all visibility state. Call when the open project changes.
   *
   *  Both hidden lists key on values that are only unique *within* a project:
   *  component ids are per-project sequences, so `COMP0001` exists in every
   *  project, and baselines are matched by name, so `PDR` collides across all
   *  of them. Without this, hiding a component in one project silently hid an
   *  unrelated one in the next, with the eye showing off in a project where
   *  nobody had touched it. Saved views are already scoped per project
   *  (`rt-graph-views-<id>`); this brings the live state in line. */
  resetVisibility: () => void;
  setContextOpen: (updater: boolean | ((prev: boolean) => boolean)) => void;
}

export const useStore = create<AppState>((set) => ({
  projects: [],
  currentProject: null,
  requirements: [],
  specifications: [],
  graphVersion: 0,
  dataVersion: 0,
  entityVersions: {},
  refocusGraph: 0,
  helpersEnabled: false,
  density: initialDensity,
  hiddenBaselines: [],
  hiddenComponents: [],
  navGuard: null,
  contextOpen: true,

  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
  setRequirements: (requirements) => set({ requirements }),
  setSpecifications: (specifications) => set({ specifications }),
  bumpGraphVersion: () => set((s) => ({ graphVersion: s.graphVersion + 1, refocusGraph: s.refocusGraph + 1 })),
  bumpDataVersion: () => set((s) => ({ dataVersion: s.dataVersion + 1 })),
  bumpEntityVersion: (kind) => set((s) => ({
    entityVersions: { ...s.entityVersions, [kind]: (s.entityVersions[kind] ?? 0) + 1 },
  })),
  toggleHelpers: () => set((s) => ({ helpersEnabled: !s.helpersEnabled })),
  setDensity: (density) => set({ density }),
  setNavGuard: (navGuard) => set({ navGuard }),
  setHiddenBaselines: (hiddenBaselines) => set({ hiddenBaselines }),
  toggleHiddenBaseline: (name) => set((s) => {
    const idx = s.hiddenBaselines.indexOf(name);
    if (idx >= 0) {
      const next = [...s.hiddenBaselines];
      next.splice(idx, 1);
      return { hiddenBaselines: next };
    }
    return { hiddenBaselines: [...s.hiddenBaselines, name] };
  }),
  setHiddenComponents: (hiddenComponents) => set({ hiddenComponents }),
  toggleHiddenComponent: (id) => set((s) => {
    const idx = s.hiddenComponents.indexOf(id);
    if (idx >= 0) {
      const next = [...s.hiddenComponents];
      next.splice(idx, 1);
      return { hiddenComponents: next };
    }
    return { hiddenComponents: [...s.hiddenComponents, id] };
  }),
  resetVisibility: () => set({ hiddenBaselines: [], hiddenComponents: [] }),
  setContextOpen: (updater) => set((s) => ({
    contextOpen: typeof updater === 'function' ? updater(s.contextOpen) : updater
  })),
}));

/**
 * Subscribe to a set of entity collections.
 *
 * Returns a number that changes when any named collection changes, or when the
 * global `dataVersion` changes (a local mutation, or a remote change the server
 * could not attribute to one collection). This is what lets one user's edit
 * refresh only the views that display the edited collection instead of every
 * mounted page re-fetching and re-solving the whole project.
 */
export function useEntityVersion(...kinds: string[]): number {
  return useStore((s) => {
    let v = s.dataVersion;
    for (const k of kinds) v += s.entityVersions[k] ?? 0;
    return v;
  });
}

/**
 * A single number that changes whenever *any* collection (or the global
 * `dataVersion`) changes. Used to key the imperative entity/parameter index
 * caches, which are broad and not tied to one collection.
 */
export function entityEpoch(): number {
  const s = useStore.getState();
  let v = s.dataVersion;
  for (const k in s.entityVersions) v += s.entityVersions[k];
  return v;
}

