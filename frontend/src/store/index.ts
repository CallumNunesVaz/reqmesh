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

  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  setRequirements: (requirements: Requirement[]) => void;
  setSpecifications: (specifications: Specification[]) => void;
  bumpGraphVersion: () => void;
  bumpDataVersion: () => void;
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
}

export const useStore = create<AppState>((set) => ({
  projects: [],
  currentProject: null,
  requirements: [],
  specifications: [],
  graphVersion: 0,
  dataVersion: 0,
  refocusGraph: 0,
  helpersEnabled: false,
  density: initialDensity,
  hiddenBaselines: [],
  hiddenComponents: [],
  navGuard: null,

  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
  setRequirements: (requirements) => set({ requirements }),
  setSpecifications: (specifications) => set({ specifications }),
  bumpGraphVersion: () => set((s) => ({ graphVersion: s.graphVersion + 1, refocusGraph: s.refocusGraph + 1 })),
  bumpDataVersion: () => set((s) => ({ dataVersion: s.dataVersion + 1 })),
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
}));
