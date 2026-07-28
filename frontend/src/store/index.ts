import { create } from 'zustand';
import type { Project, Requirement, Specification, VerificationCase } from '../api/client';

interface AppState {
  projects: Project[];
  currentProject: Project | null;
  requirements: Requirement[];
  specifications: Specification[];
  verificationCases: VerificationCase[];
  loading: boolean;
  error: string | null;
  graphVersion: number;
  dataVersion: number;
  refocusGraph: number;
  helpersEnabled: boolean;
  /** Baselines currently selected in the graph filter — empty = show all. */
  baselineFilters: string[];
  /** Components currently selected in the graph filter — empty = show all. */
  componentFilters: string[];
  /** A page with unsaved edits registers a guard here; navigators await it and
   *  abort when it resolves false (user chose to keep editing). Null = free. */
  navGuard: (() => boolean | Promise<boolean>) | null;

  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  setRequirements: (requirements: Requirement[]) => void;
  setSpecifications: (specifications: Specification[]) => void;
  setVerificationCases: (cases: VerificationCase[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  bumpGraphVersion: () => void;
  bumpDataVersion: () => void;
  toggleHelpers: () => void;
  setNavGuard: (fn: (() => boolean | Promise<boolean>) | null) => void;
  setBaselineFilters: (filters: string[]) => void;
  toggleBaselineFilter: (name: string) => void;
  setComponentFilters: (filters: string[]) => void;
  toggleComponentFilter: (id: string) => void;
}

export const useStore = create<AppState>((set) => ({
  projects: [],
  currentProject: null,
  requirements: [],
  specifications: [],
  verificationCases: [],
  loading: false,
  error: null,
  graphVersion: 0,
  dataVersion: 0,
  refocusGraph: 0,
  helpersEnabled: false,
  baselineFilters: [],
  componentFilters: [],
  navGuard: null,

  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
  setRequirements: (requirements) => set({ requirements }),
  setSpecifications: (specifications) => set({ specifications }),
  setVerificationCases: (verificationCases) => set({ verificationCases }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  bumpGraphVersion: () => set((s) => ({ graphVersion: s.graphVersion + 1, refocusGraph: s.refocusGraph + 1 })),
  bumpDataVersion: () => set((s) => ({ dataVersion: s.dataVersion + 1 })),
  toggleHelpers: () => set((s) => ({ helpersEnabled: !s.helpersEnabled })),
  setNavGuard: (navGuard) => set({ navGuard }),
  setBaselineFilters: (filters) => set({ baselineFilters: filters }),
  toggleBaselineFilter: (name) => set((s) => {
    const idx = s.baselineFilters.indexOf(name);
    if (idx >= 0) {
      const next = [...s.baselineFilters];
      next.splice(idx, 1);
      return { baselineFilters: next };
    }
    return { baselineFilters: [...s.baselineFilters, name] };
  }),
  setComponentFilters: (filters) => set({ componentFilters: filters }),
  toggleComponentFilter: (id) => set((s) => {
    const idx = s.componentFilters.indexOf(id);
    if (idx >= 0) {
      const next = [...s.componentFilters];
      next.splice(idx, 1);
      return { componentFilters: next };
    }
    return { componentFilters: [...s.componentFilters, id] };
  }),
}));
