import { Loader2, FlaskConical, Check, RotateCcw } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useWhatIf } from './WhatIfContext';
import { useAuthStore } from '../store/auth';

export default function WhatIfBar(): JSX.Element | null {
  const { projectId } = useParams<{ projectId: string }>();
  const whatIf = useWhatIf();
  const { impact, overrides, pending, clear, confirm } = whatIf;
  const overrideCount = Object.keys(overrides).length;
  const canEdit = useAuthStore((s) => s.canEdit());

  if (overrideCount === 0) return null;

  const affected = impact?.affected?.length ?? 0;

  const summary = (
    <>
      {overrideCount} value{overrideCount !== 1 ? 's' : ''}
      <span className="mx-1 text-muted-foreground/50">·</span>
      {affected} affected
    </>
  );

  return (
    <div className="sticky bottom-3 z-30 mx-3 flex items-center gap-2 rounded-lg border bg-card/95 backdrop-blur px-3 py-2 shadow-lg">
      <FlaskConical size={13} className="text-blue-400 shrink-0" />
      <span className="text-[11px] text-muted-foreground truncate">
        {pending ? <span className="inline-flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Computing…</span> : summary}
      </span>
      <div className="flex-1" />
      {canEdit && (
        <button
          onClick={() => confirm(projectId!)}
          disabled={pending || overrideCount === 0}
          className="btn-primary flex items-center gap-1 text-[11px] px-2 py-1 disabled:opacity-40 shrink-0"
        >
          <Check size={11} /> Confirm
        </button>
      )}
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
