import { useEffect, useState, useId } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Trash2, ArrowLeft, AlertTriangle, X } from 'lucide-react';
import { api, RISK_STATUSES, type Risk, type Requirement, type Component, type RiskMatrix } from '../api/client';
import type { RiskUpdate } from '../api/generated/writeModels';
import { CopyLinkButton } from '../components/entities';
import { useEntityKinds } from '../components/entityIndex';
import { AutoLinkHtml } from '../components/autoLink';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import LoadingSplash from '../components/LoadingSplash';
import Reveal from '../components/Reveal';
import { LinkEditor } from '../components/LinkEditor';
import RichTextEditor from '../components/RichTextEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useConfirm } from '../components/ConfirmDialog';
import { useToasts } from '../components/Toast';
import { deleteWithReferenceCheck } from '../lib/forceDelete';

const formatLevel = (s: string) => s.replace(/_/g, ' ');

export default function RiskDetailPage() {
  const { projectId, riskId } = useParams<{ projectId: string; riskId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canPropose());
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const entityKinds = useEntityKinds(projectId);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();

  const failureModeId = useId();
  const effectId = useId();
  const causeId = useId();

  const [risk, setRisk] = useState<Risk | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [matrix, setMatrix] = useState<RiskMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    if (!projectId || !riskId) return;
    setLoading(true);
    Promise.all([
      api.getRisk(projectId, riskId),
      api.listRequirements(projectId),
      api.listComponents(projectId),
      api.getRiskMatrix(projectId).catch(() => null),
    ]).then(([risk, reqs, comps, matrix]) => {
      if (!risk) { setError('Risk not found'); setLoading(false); return; }
      setRisk(risk);
      setRequirements(reqs);
      setComponents(comps);
      setMatrix(matrix);
      setLoading(false);
    }).catch((err) => { setError(err.message); setLoading(false); });
  };

  useEffect(load, [projectId, riskId]);

  const save = async (patch: RiskUpdate) => {
    if (!projectId || !riskId) return;
    setError('');
    try {
      const updated = await api.updateRisk(projectId, riskId, patch);
      setRisk(updated);
      addToast('success', `Risk ${riskId} updated`);
      bumpDataVersion();
    } catch (err: any) {
      addToast('error', err.message || 'Save failed');
    }
  };

  const handleDelete = async () => {
    if (!projectId || !riskId) return;
    const ok = await showConfirm(`Delete risk "${riskId}"?`, 'Delete Risk', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    setError('');
    try {
      const done = await deleteWithReferenceCheck(
        (force) => api.deleteRisk(projectId, riskId, force),
        (msg) => showConfirm(msg),
      );
      if (done) {
        addToast('success', `Risk ${riskId} deleted`);
        navigate(`/project/${projectId}/risks`);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to delete risk');
    }
  };

  useKeyboardShortcuts(projectId, {
    onDetailSave: () => { /* every field saves on blur; nothing to batch */ },
    onDetailDelete: handleDelete,
    onDetailEscape: () => { if (window.history.length > 1) navigate(-1); else navigate(`/project/${projectId}/risks`); },
  });

  const setList = (field: 'linked_requirements' | 'mitigating_requirements' | 'linked_components' | 'mitigating_components', next: string[]) => {
    if (!risk) return;
    setRisk({ ...risk, [field]: next });
    save({ [field]: next });
  };

  const nameOf = (id: string, list: { id: string; name: string }[]) =>
    list.find((x) => x.id === id)?.name ?? '';

  if (loading) {
    return <div className="relative h-[60vh]"><LoadingSplash label="Loading risk…" /></div>;
  }

  if (!risk) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground">{error || 'Risk not found.'}</p>
        <button onClick={() => navigate(`/project/${projectId}/risks`)} className="btn-secondary mt-4">
          <ArrowLeft size={14} /> Back to risks
        </button>
      </div>
    );
  }

  const rating = risk.rating;
  const bandLabel = rating?.label || (rating?.unrated_reason ? 'Unrated' : 'Unrated');

  return (
    <div className="max-w-4xl mx-auto p-8">
      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
          <AlertTriangle size={14} /> {error}
          <button onClick={() => setError('')} className="ml-auto text-destructive/50 hover:text-destructive"><X size={14} /></button>
        </div>
      )}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/project/${projectId}/risks`)} className="btn-secondary p-2">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-cs-red" />
            <h1 className="text-xl font-bold tracking-tight font-mono text-foreground">{risk.id}</h1>
            <CopyLinkButton kind="risk" id={risk.id} />
          </div>
          <input
            className="input text-lg font-medium mt-1 w-full max-w-md"
            value={risk.title}
            onChange={(e) => setRisk({ ...risk, title: e.target.value })}
            onBlur={(e) => save({ title: e.target.value })}
            disabled={!editable}
            placeholder="Risk title"
            aria-label="Title"
          />
        </div>
        <button onClick={handleDelete} className="btn-danger" disabled={!editable} title="Delete">
          <Trash2 size={14} />
        </button>
      </div>

      <div className="grid grid-cols-1 @4xl:grid-cols-3 gap-6">
        {/* Main content area */}
        <div className="@4xl:col-span-2 space-y-6">
          <Reveal className="card p-5">
            <label className="label" htmlFor={failureModeId}>Failure Mode</label>
            {editable ? (
              <RichTextEditor
                id={failureModeId}
                content={risk.failure_mode || ''}
                onChange={(html) => setRisk({ ...risk, failure_mode: html })}
                onBlur={(html) => save({ failure_mode: html })}
                placeholder="What goes wrong…"
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[60px] opacity-90">
                {risk.failure_mode ? <AutoLinkHtml html={risk.failure_mode} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No failure mode</span>}
              </div>
            )}
            <label className="label mt-4" htmlFor={effectId}>Effect</label>
            {editable ? (
              <RichTextEditor
                id={effectId}
                content={risk.effect || ''}
                onChange={(html) => setRisk({ ...risk, effect: html })}
                onBlur={(html) => save({ effect: html })}
                placeholder="What the failure does to the system…"
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[60px] opacity-90">
                {risk.effect ? <AutoLinkHtml html={risk.effect} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No effect</span>}
              </div>
            )}
            <label className="label mt-4" htmlFor={causeId}>Cause</label>
            {editable ? (
              <RichTextEditor
                id={causeId}
                content={risk.cause || ''}
                onChange={(html) => setRisk({ ...risk, cause: html })}
                onBlur={(html) => save({ cause: html })}
                placeholder="Why the failure happens…"
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[60px] opacity-90">
                {risk.cause ? <AutoLinkHtml html={risk.cause} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No cause</span>}
              </div>
            )}
          </Reveal>

          <Reveal step={2} className="card p-5">
            <label className="label">Mitigation
              <textarea
                className="input min-h-[64px]"
                value={risk.mitigation || ''}
                onChange={(e) => setRisk({ ...risk, mitigation: e.target.value })}
                onBlur={(e) => save({ mitigation: e.target.value })}
                disabled={!editable}
                placeholder="How the risk is controlled…"
              />
            </label>
            <label className="label mt-4">Impact
              <textarea
                className="input min-h-[64px]"
                value={risk.impact || ''}
                onChange={(e) => setRisk({ ...risk, impact: e.target.value })}
                onBlur={(e) => save({ impact: e.target.value })}
                disabled={!editable}
                placeholder="What the risk costs if it happens…"
              />
            </label>
          </Reveal>

          <Reveal step={3} className="card p-5">
            <LinkEditor label="Threatens" hint="Requirements this risk endangers" kind="requirement"
              linked={risk.linked_requirements || []} options={requirements} editable={editable}
              onAdd={(id) => setList('linked_requirements', [...(risk.linked_requirements || []), id])}
              onRemove={(id) => setList('linked_requirements', (risk.linked_requirements || []).filter((x) => x !== id))}
              nameOf={(id) => nameOf(id, requirements)} />
            <div className="mt-3 pt-3 border-t">
              <LinkEditor label="Mitigated By" hint="Requirements that control this risk" kind="requirement"
                linked={risk.mitigating_requirements || []} options={requirements} editable={editable}
                onAdd={(id) => setList('mitigating_requirements', [...(risk.mitigating_requirements || []), id])}
                onRemove={(id) => setList('mitigating_requirements', (risk.mitigating_requirements || []).filter((x) => x !== id))}
                nameOf={(id) => nameOf(id, requirements)} />
            </div>
            <div className="mt-3 pt-3 border-t">
              <LinkEditor label="Threatens (components)" hint="Components this risk endangers" kind="component"
                linked={risk.linked_components || []} options={components} editable={editable}
                onAdd={(id) => setList('linked_components', [...(risk.linked_components || []), id])}
                onRemove={(id) => setList('linked_components', (risk.linked_components || []).filter((x) => x !== id))}
                nameOf={(id) => nameOf(id, components)} />
            </div>
            <div className="mt-3 pt-3 border-t">
              <LinkEditor label="Mitigated By (components)" hint="Components that control this risk" kind="component"
                linked={risk.mitigating_components || []} options={components} editable={editable}
                onAdd={(id) => setList('mitigating_components', [...(risk.mitigating_components || []), id])}
                onRemove={(id) => setList('mitigating_components', (risk.mitigating_components || []).filter((x) => x !== id))}
                nameOf={(id) => nameOf(id, components)} />
            </div>
          </Reveal>

          <Reveal step={4} className="card p-5">
            <CommentThread entityKind="risks" entityId={riskId!} />
          </Reveal>
          <Reveal step={4} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Change History</h2>
            <HistoryPanel itemId={riskId!} defaultOpen />
          </Reveal>
        </div>

        {/* Properties sidebar */}
        <div className="space-y-6">
          <Reveal step={1} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Rating</h2>
            <div className="flex items-center gap-2 mb-4">
              <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: rating?.color || 'hsl(var(--muted-foreground))' }} />
              {/* The band as text, not only as colour — see the list row for why. */}
              <span className="text-sm font-semibold text-card-foreground">{bandLabel}</span>
            </div>
            {rating?.unrated_reason && (
              <p className="text-[11px] text-muted-foreground -mt-2 mb-4">{rating.unrated_reason}</p>
            )}
            <div className="space-y-3">
              <label className="label">Severity
                <select className="input" value={risk.severity || ''}
                  onChange={(e) => save({ severity: e.target.value })} disabled={!editable}>
                  {!((matrix?.severities ?? []).includes(risk.severity)) && risk.severity && (
                    <option value={risk.severity}>{risk.severity}</option>
                  )}
                  {(matrix?.severities ?? []).map((sv) => <option key={sv} value={sv}>{formatLevel(sv)}</option>)}
                </select>
              </label>
              <label className="label">Likelihood
                <select className="input" value={rating?.likelihood ?? risk.likelihood ?? ''}
                  onChange={(e) => save({ likelihood: e.target.value })} disabled={!editable}>
                  {!((matrix?.likelihoods ?? []).includes(rating?.likelihood ?? risk.likelihood ?? '')) && (rating?.likelihood ?? risk.likelihood) && (
                    <option value={rating?.likelihood ?? risk.likelihood}>{rating?.likelihood ?? risk.likelihood}</option>
                  )}
                  {(matrix?.likelihoods ?? []).map((l) => <option key={l} value={l}>{formatLevel(l)}</option>)}
                </select>
              </label>
              <label className="label">Detection
                <select className="input" value={risk.detection || ''}
                  onChange={(e) => save({ detection: e.target.value })} disabled={!editable}>
                  {!risk.detection && <option value="">not assessed</option>}
                  {risk.detection && !((matrix?.detections ?? []).includes(risk.detection)) && (
                    <option value={risk.detection}>{risk.detection}</option>
                  )}
                  {(matrix?.detections ?? []).map((d) => <option key={d} value={d}>{formatLevel(d)}</option>)}
                </select>
              </label>
              <label className="label">Status
                <select className="input" value={risk.status || ''}
                  onChange={(e) => save({ status: e.target.value })} disabled={!editable}>
                  {!RISK_STATUSES.includes(risk.status as any) && risk.status && (
                    <option value={risk.status}>{risk.status}</option>
                  )}
                  {RISK_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
            </div>
          </Reveal>

          <div className="text-xs text-muted-foreground space-y-1">
            <div>Created: {new Date(risk.created).toLocaleString()}</div>
            <div>Modified: {new Date(risk.modified).toLocaleString()}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
