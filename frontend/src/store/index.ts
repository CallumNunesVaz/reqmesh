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
}));
