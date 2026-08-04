import { useMemo, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Play, Pause, SkipBack, SkipForward, Check, RotateCcw, Loader2, X, Minimize2, FlaskConical, ChevronLeft, ChevronRight } from 'lucide-react';
import { useWhatIf } from './WhatIfContext';
import { VerdictBadge, MarginTag } from './parametrics';
import { requirementVerdict } from '../lib/whatIfVerdict';
import type { ImpactStepParam, ImpactStepConstraint, ConstraintStatus } from '../api/client';

function ParamStep({ step }: { step: ImpactStepParam }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-mono font-medium text-foreground">{step.name}</span>
      <span className="font-mono text-muted-foreground text-[10px]">
        {step.expr ? `= ${step.expr}` : ''}
      </span>
      <span className="text-muted-foreground text-[10px]">{step.unit}</span>
      <span className="flex items-baseline gap-1 font-mono text-[10px] ml-auto">
        <span className="text-muted-foreground">
          {step.before != null ? step.before : '?'}
        </span>
        <span className="text-muted-foreground">&rarr;</span>
        <span className="font-bold text-foreground">
          {step.after != null ? step.after : '?'}
        </span>
      </span>
    </div>
  );
}

function ConstraintStep({ step }: { step: ImpactStepConstraint }) {
  const beforeStatus = step.before.status as ConstraintStatus;
  const afterStatus = step.after.status as ConstraintStatus;
  const flipped = beforeStatus !== afterStatus;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-mono text-muted-foreground text-[10px] truncate flex-1">{step.expr}</span>
      <span className="flex items-center gap-1.5 shrink-0">
        {flipped ? (
          <>
            <VerdictBadge status={beforeStatus} />
            <span className="text-muted-foreground text-[10px]">&rarr;</span>
          </>
        ) : (
          <span className="text-muted-foreground font-mono text-[10px]">{step.before.margin?.value}</span>
        )}
        <VerdictBadge status={afterStatus} />
        {step.after.margin && !flipped && <MarginTag margin={step.after.margin} />}
        {step.after.margin && flipped && (
          <span className="text-[10px] font-mono text-red-400">
            {step.after.margin.value > 0 ? '+' : ''}{step.after.margin.value}
            {step.after.margin.pct !== undefined ? ` (${step.after.margin.pct > 0 ? '+' : ''}${step.after.margin.pct}%)` : ''}
          </span>
        )}
      </span>
    </div>
  );
}

export default function WhatIfPanel() {
  const { projectId } = useParams<{ projectId: string }>();
  const whatIf = useWhatIf();
  const { impact, overrides, base, pending, error,
    stepIndex, playing, setStepIndex, setPlaying, clear, confirm } = whatIf;
  const steps = impact?.steps ?? [];
  const affected = impact?.affected ?? [];
  const roots = impact?.roots ?? [];
  const overrideCount = Object.keys(overrides).length;
  // Minimized: the full overlay collapses to a floating bar so the parameter
  // rows underneath stay reachable — that's how a second override gets stacked.
  const [collapsed, setCollapsed] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const stepRef = useRef(stepIndex);
  stepRef.current = stepIndex;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!impact || impact.steps.length === 0) return;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setStepIndex(Math.max(0, stepIndex - 1));
      setPlaying(false);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setStepIndex(Math.min(impact.steps.length - 1, stepIndex + 1));
      setPlaying(false);
    }
  };

  useEffect(() => {
    if (playing && steps.length > 0) {
      timerRef.current = setInterval(() => {
        const next = stepRef.current + 1;
        if (next >= steps.length) {
          setPlaying(false);
        } else {
          setStepIndex(next);
        }
      }, 600);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, steps.length, setStepIndex, setPlaying]);

  // Count within the *affected* set (requirements whose verdict actually
  // changed), not the whole project — otherwise "M failing" reports every
  // failing requirement, unrelated to this override.
  const { failNow, passNow } = useMemo(() => {
    if (!impact) return { failNow: 0, passNow: 0 };
    const affectedSet = new Set(impact.affected);
    let f = 0, p = 0;
    for (const er of impact.evaluation.requirements) {
      if (!affectedSet.has(er.id)) continue;
      if (er.verdict === 'fail') f++;
      else if (er.verdict === 'pass') p++;
    }
    return { failNow: f, passNow: p };
  }, [impact]);

  const rootLines = useMemo(() => {
    return roots.map((r: string) => {
      const original = base[r];
      const next = overrides[r];
      return `${r}: ${original ?? '?'} → ${next}`;
    });
  }, [roots, base, overrides]);

  if (!impact && overrideCount === 0) return null;

  const rootOwners = new Set(roots.map((r: string) => r.split('.')[0]));

  const summary = (
    <>
      {overrideCount} value{overrideCount !== 1 ? 's' : ''}
      <span className="mx-1 text-muted-foreground/50">·</span>
      {affected.length} affected
      {failNow > 0 && <span className="text-red-400 ml-1">· {failNow} failing</span>}
      {passNow > 0 && <span className="text-emerald-400 ml-1">· {passNow} passing</span>}
    </>
  );

  // ── Minimized floating bar ────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="sticky bottom-3 z-30 mx-3 flex items-center gap-2 rounded-lg border bg-card/95 backdrop-blur px-3 py-2 shadow-lg">
        <FlaskConical size={13} className="text-blue-400 shrink-0" />
        <span className="text-[11px] text-muted-foreground truncate">
          {pending ? <span className="inline-flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Computing…</span> : summary}
        </span>
        <div className="flex-1" />
        <button
          onClick={() => setCollapsed(false)}
          className="text-[10px] px-2 py-1 rounded hover:bg-accent text-muted-foreground shrink-0"
          title="Expand what-if"
        >
          Expand
        </button>
        <button
          onClick={() => confirm(projectId!)}
          disabled={pending || overrideCount === 0}
          className="btn-primary flex items-center gap-1 text-[11px] px-2 py-1 disabled:opacity-40 shrink-0"
        >
          <Check size={11} /> Confirm
        </button>
        <button
          onClick={() => clear()}
          disabled={pending}
          className="btn-secondary flex items-center gap-1 text-[11px] px-2 py-1 shrink-0"
          title="Restore original values"
        >
          <RotateCcw size={11} />
        </button>
      </div>
    );
  }

  // ── Full overlay ──────────────────────────────────────────────────────────
  return (
    <div className="absolute inset-0 z-30 bg-background/95 backdrop-blur-sm overflow-auto" tabIndex={-1} onKeyDown={handleKeyDown}>
      <div className="flex flex-col h-full">
        <div className="flex items-start justify-between p-3 border-b shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-card-foreground">Live What-If Preview</h2>
            <p className="text-[10px] text-muted-foreground mt-0.5">{summary}</p>
            {rootLines.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {rootLines.map((line: string, i: number) => (
                  <span key={i} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    {line}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setCollapsed(true)}
              className="p-1 rounded hover:bg-accent text-muted-foreground"
              title="Minimize (keep previewing while you add more values)"
            >
              <Minimize2 size={14} />
            </button>
            <button onClick={() => clear()} className="p-1 rounded hover:bg-accent text-muted-foreground" title="Restore and close">
              <X size={14} />
            </button>
          </div>
        </div>

        {pending && (
          <div className="flex items-center gap-2 p-3 text-xs text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Computing impact...
          </div>
        )}

        {error && (
          <div className="p-3 text-xs text-red-400">Error: {error}</div>
        )}

        {impact && impact.steps.length === 0 && !pending && (
          <div className="p-3 text-xs text-muted-foreground">
            No downstream requirement changes — this value keeps every threshold satisfied.
          </div>
        )}

        {impact && impact.steps.length > 0 && (
          <>
            <div className="flex items-center gap-1 p-2 border-b shrink-0">
              <button
                onClick={() => setStepIndex(0)}
                disabled={stepIndex === 0}
                className="p-1 rounded hover:bg-accent text-muted-foreground disabled:opacity-30"
                title="First step"
              >
                <SkipBack size={12} />
              </button>
              <button
                onClick={() => { setStepIndex(Math.max(0, stepIndex - 1)); setPlaying(false); }}
                disabled={stepIndex === 0}
                className="p-1 rounded hover:bg-accent text-muted-foreground disabled:opacity-30"
                title="Step back"
              >
                <ChevronLeft size={12} />
              </button>
              <button
                onClick={() => setPlaying(!playing)}
                className="p-1 rounded hover:bg-accent text-muted-foreground"
                title={playing ? 'Pause' : 'Play'}
              >
                {playing ? <Pause size={12} /> : <Play size={12} />}
              </button>
              <button
                onClick={() => { setStepIndex(Math.min(impact.steps.length - 1, stepIndex + 1)); setPlaying(false); }}
                disabled={stepIndex >= impact.steps.length - 1}
                className="p-1 rounded hover:bg-accent text-muted-foreground disabled:opacity-30"
                title="Step forward"
              >
                <ChevronRight size={12} />
              </button>
              <button
                onClick={() => setStepIndex(impact.steps.length - 1)}
                disabled={stepIndex >= impact.steps.length - 1}
                className="p-1 rounded hover:bg-accent text-muted-foreground disabled:opacity-30"
                title="Last step"
              >
                <SkipForward size={12} />
              </button>
              <span className="text-[10px] text-muted-foreground ml-1">
                Step {stepIndex + 1} / {impact.steps.length}
              </span>
            </div>

            <div className="flex-1 overflow-auto p-3 space-y-1.5">
              {impact.steps.slice(0, stepIndex + 1).map((step, i) => {
                const v = impact.evaluation ? requirementVerdict(impact.evaluation, step.owner) : 'unknown';
                const verdictBorder = v === 'pass'
                  ? 'border-l-emerald-400/70'
                  : v === 'fail'
                    ? 'border-l-red-400/70'
                    : '';
                const verdictBg = v === 'pass'
                  ? 'bg-emerald-500/5'
                  : v === 'fail'
                    ? 'bg-red-500/5'
                    : '';
                return (
                <div
                  key={i}
                  className={`p-2 rounded border transition-colors cursor-pointer border-l-2 ${verdictBorder} ${verdictBg} ${
                    i === stepIndex
                      ? 'border-primary/60 bg-primary/5'
                      : 'border-transparent hover:bg-accent'
                  }`}
                  onClick={() => { setStepIndex(i); setPlaying(false); }}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    {/* The verdict in words as well as colour. A tint alone is
                        unreadable to anyone who cannot separate the hues, and
                        this is the answer the whole panel exists to give. */}
                    {v !== 'unknown' && (
                      <span className={`text-[9px] font-semibold uppercase tracking-wider ${
                        v === 'pass' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {v === 'pass' ? 'pass' : 'fail'}
                      </span>
                    )}
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">
                      {step.kind === 'param' ? 'Param' : 'Constraint'}
                    </span>
                    <span className={`text-[9px] font-mono ${rootOwners.has(step.owner) ? 'text-blue-400' : 'text-muted-foreground'}`}>
                      {step.owner}
                    </span>
                    {v !== 'unknown' && (
                      <span className={`text-[9px] font-semibold ml-auto ${v === 'pass' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {v === 'pass' ? 'pass' : 'fail'}
                      </span>
                    )}
                  </div>
                  {step.kind === 'param' ? (
                    <ParamStep step={step} />
                  ) : (
                    <ConstraintStep step={step} />
                  )}
                </div>
                );
              })}
            </div>
          </>
        )}

        <div className="flex items-center gap-2 p-3 border-t shrink-0 mt-auto">
          <button
            onClick={() => confirm(projectId!)}
            disabled={pending || overrideCount === 0}
            className="btn-primary flex items-center gap-1.5 text-xs px-3 py-1.5 disabled:opacity-40"
          >
            <Check size={12} /> Confirm
          </button>
          <button
            onClick={() => clear()}
            disabled={pending}
            className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-1.5"
          >
            <RotateCcw size={12} /> Restore
          </button>
          <span className="text-[10px] text-muted-foreground ml-auto">
            Minimize to add more values across requirements
          </span>
        </div>
      </div>
    </div>
  );
}
