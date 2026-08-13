import { useMemo, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Play, Pause, SkipBack, SkipForward, Check, RotateCcw, Loader2, X, FlaskConical, ChevronLeft, ChevronRight } from 'lucide-react';
import { useWhatIf } from './WhatIfContext';
import { VerdictBadge, MarginTag } from './parametrics';
import { requirementVerdict } from '../lib/whatIfVerdict';
import { useAuthStore } from '../store/auth';
import { useToasts } from './Toast';
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

export default function WhatIfPanel(): JSX.Element | null {
  const { projectId } = useParams<{ projectId: string }>();
  const whatIf = useWhatIf();
  const { impact, overrides, base, pending, error,
    stepIndex, playing, setStepIndex, setPlaying, clear, apply } = whatIf;
  const steps = impact?.steps ?? [];
  const affected = impact?.affected ?? [];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const roots = impact?.roots ?? [];
  const overrideCount = Object.keys(overrides).length;
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const stepRef = useRef(stepIndex);
  stepRef.current = stepIndex;
  const canEdit = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const cardRef = useRef<HTMLDivElement>(null);

  // Bring a new result into view. Inline means the card sits below Parameters &
  // Constraints, which on a tall requirement is off the bottom of the pane — so
  // pressing Evaluate looked like it did nothing at all.
  //
  // Keyed on `impact` identity, not `stepIndex`: the context replaces impact
  // wholesale per evaluation, so this fires once per result. Scrolling on every
  // step would fight the reader working through the list, which is the same
  // reason the canvas only re-frames per evaluation.
  useEffect(() => {
    if (!impact) return;
    cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [impact]);

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

  return (
    <div ref={cardRef} className="card p-5">
      <div className="flex items-start justify-between mb-3">
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
        <button onClick={() => clear()} className="p-1 rounded hover:bg-accent text-muted-foreground" title="Restore original values">
          <X size={14} />
        </button>
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
          <div className="flex items-center gap-1 p-2 border-b">
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

          <div className="p-3 space-y-1.5">
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
              <button
                type="button"
                key={i}
                className={`p-2 w-full text-left rounded border transition-colors cursor-pointer border-l-2 ${verdictBorder} ${verdictBg} ${
                  i === stepIndex
                    ? 'border-primary/60 bg-primary/5'
                    : 'border-transparent hover:bg-accent'
                }`}
                onClick={() => { setStepIndex(i); setPlaying(false); }}
                onKeyDown={handleKeyDown}
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
              </button>
              );
            })}
          </div>
        </>
      )}

      <div className="flex items-center gap-2 mt-3 pt-3 border-t">
        {canEdit && (
          <button
            onClick={async () => {
              try { await apply(projectId!); }
              catch (err) { addToast('error', err instanceof Error ? err.message : 'Save failed'); }
            }}
            disabled={pending || overrideCount === 0}
            className="btn-primary flex items-center gap-1.5 text-xs px-3 py-1.5 disabled:opacity-40"
          >
            <Check size={12} /> Confirm
          </button>
        )}
        <button
          onClick={() => clear()}
          disabled={pending}
          className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-1.5"
        >
          <RotateCcw size={12} /> Restore
        </button>
      </div>
    </div>
  );
}
