import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { api, type ImpactResultData } from '../api/client';

interface WhatIfState {
  overrides: Record<string, number>;
  base: Record<string, number | null>;
  impact: ImpactResultData | null;
  pending: boolean;
  error: string | null;
  stepIndex: number;
  playing: boolean;
}

interface WhatIfActions {
  setOverride: (ref: string, value: number, original: number) => void;
  removeOverride: (ref: string) => void;
  evaluate: () => void;
  clear: () => void;
  confirm: (projectId: string) => Promise<void>;
  setStepIndex: (i: number) => void;
  setPlaying: (p: boolean) => void;
}

const WhatIfCtx = createContext<WhatIfState & WhatIfActions>({
  overrides: {},
  base: {},
  impact: null,
  pending: false,
  error: null,
  stepIndex: 0,
  playing: false,
  setOverride: () => {},
  removeOverride: () => {},
  evaluate: () => {},
  clear: () => {},
  confirm: async () => {},
  setStepIndex: () => {},
  setPlaying: () => {},
});

export function useWhatIf() {
  return useContext(WhatIfCtx);
}

export function WhatIfProvider({ projectId, children }: { projectId: string; children: React.ReactNode }) {
  const editMode = useAuthStore((s) => s.editMode);
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);

  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [base, setBase] = useState<Record<string, number | null>>({});
  const [impact, setImpact] = useState<ImpactResultData | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  const seqRef = useRef(0);

  const fetchImpact = useCallback((ov: Record<string, number>) => {
    if (Object.keys(ov).length === 0) {
      setImpact(null);
      setStepIndex(0);
      setPlaying(false);
      return;
    }
    const seq = ++seqRef.current;
    setPending(true);
    setError(null);
    api.getEvaluationImpact(projectId, ov)
      .then((result) => {
        if (seq !== seqRef.current) return;
        setImpact(result);
        setStepIndex(0);
        setPlaying(true);
        setPending(false);
      })
      .catch((err: Error) => {
        if (seq !== seqRef.current) return;
        setError(err.message);
        setPending(false);
      });
  }, [projectId]);

  useEffect(() => {
    if (!editMode) {
      setOverrides({});
      setBase({});
      setImpact(null);
      setStepIndex(0);
      setPlaying(false);
    }
  }, [editMode]);

  const setOverride = useCallback((ref: string, value: number, original: number) => {
    setOverrides((prev) => ({ ...prev, [ref]: value }));
    setBase((b) => ({ ...b, [ref]: original }));
  }, []);

  const removeOverride = useCallback((ref: string) => {
    setOverrides((prev) => {
      const next = { ...prev };
      delete next[ref];
      return next;
    });
    setBase((b) => {
      const nb = { ...b };
      delete nb[ref];
      return nb;
    });
  }, []);

  const evaluate = useCallback(() => {
    fetchImpact(overrides);
  }, [fetchImpact, overrides]);

  const clear = useCallback(() => {
    setOverrides({});
    setBase({});
    setImpact(null);
    setStepIndex(0);
    setPlaying(false);
    setError(null);
    bumpGraphVersion();
    bumpDataVersion();
  }, [bumpGraphVersion, bumpDataVersion]);

  const confirm = useCallback(async (pid: string) => {
    const entries = Object.entries(overrides);
    if (entries.length === 0) return;
    // Group the new values by requirement id. A ref is "REQ.param"; the id has
    // no dot, so split on the first one and keep the remainder as the name.
    const byReq: Record<string, Record<string, number>> = {};
    for (const [ref, value] of entries) {
      const dot = ref.indexOf('.');
      if (dot < 0) continue;
      const reqId = ref.slice(0, dot);
      const paramName = ref.slice(dot + 1);
      byReq[reqId] = byReq[reqId] || {};
      byReq[reqId][paramName] = value;
    }
    // Merge each override into the requirement's *full* parameter list — a bare
    // `{ parameters: [changed] }` update would replace the list and wipe every
    // other parameter (and this param's unit/kind).
    // Reported through this context's own `error`, which WhatIfPanel already
    // renders, rather than a toast — a provider that draws nothing should not
    // own a notification. Without it a refused write vanished as an unhandled
    // rejection partway through the loop, leaving some requirements committed
    // and others not, with the panel still showing the overrides as pending.
    try {
      for (const [reqId, changes] of Object.entries(byReq)) {
        const req = await api.getRequirement(pid, reqId);
        const params = (req.parameters ?? []).map((p) =>
          changes[p.name] !== undefined ? { ...p, value: changes[p.name] } : p
        );
        await api.updateRequirement(pid, reqId, { parameters: params });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not apply the overrides');
      bumpGraphVersion();
      bumpDataVersion();
      return;
    }
    bumpGraphVersion();
    bumpDataVersion();
    clear();
  }, [overrides, clear, bumpGraphVersion, bumpDataVersion]);

  const value: WhatIfState & WhatIfActions = {
    overrides,
    base,
    impact,
    pending,
    error,
    stepIndex,
    playing,
    setOverride,
    removeOverride,
    evaluate,
    clear,
    confirm,
    setStepIndex,
    setPlaying,
  };

  if (!editMode) return <>{children}</>;
  return <WhatIfCtx.Provider value={value}>{children}</WhatIfCtx.Provider>;
}
