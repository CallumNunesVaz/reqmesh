import { useEffect, useState, useId } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2, X, Play, CheckCircle2, XCircle, Clock, FlaskConical, ClipboardList, ListChecks, Link as LinkIcon, Loader, Plus } from 'lucide-react';
import { api, type VerificationCase, type Requirement, type Component } from '../api/client';
import type { VerificationCaseUpdate } from '../api/generated/writeModels';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useEntityKinds } from '../components/entityIndex';
import { AutoLinkText } from '../components/autoLink';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useToasts } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';
import AutocompleteInput from '../components/AutocompleteInput';
import MentionTextarea from '../components/MentionTextarea';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import LoadingSplash from '../components/LoadingSplash';
import Reveal from '../components/Reveal';

const METHOD_OPTIONS = ['test', 'analysis', 'demonstration', 'inspection'] as const;
const STATUS_OPTIONS = ['pending', 'in_progress', 'passed', 'failed'] as const;

const statusBadges: Record<string, string> = {
  pending: 'border-cs-amber/30 bg-cs-amber/10 text-cs-amber',
  in_progress: 'border-cs-blue/30 bg-cs-blue/10 text-cs-blue',
  passed: 'border-cs-green/30 bg-cs-green/10 text-cs-green',
  failed: 'border-cs-red/30 bg-cs-red/10 text-cs-red',
};

const statusIconColors: Record<string, string> = {
  pending: 'bg-cs-amber/10 text-cs-amber',
  in_progress: 'bg-cs-blue/10 text-cs-blue',
  passed: 'bg-cs-green/10 text-cs-green',
  failed: 'bg-cs-red/10 text-cs-red',
};

const statusIcons: Record<string, React.ComponentType<any>> = {
  pending: Clock,
  in_progress: XCircle,
  passed: CheckCircle2,
  failed: XCircle,
};

export default function VerificationDetailPage() {
  const { projectId, vcId } = useParams<{ projectId: string; vcId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canEdit());
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const entityKinds = useEntityKinds(projectId);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();

  const [vc, setVc] = useState<VerificationCase | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [linkInput, setLinkInput] = useState('');
  const [stepAction, setStepAction] = useState('');
  const [stepExpected, setStepExpected] = useState('');
  const [measurement, setMeasurement] = useState({ parameter: '', value: '', unit: '' });
  const [running, setRunning] = useState(false);
  const [runFeedback, setRunFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const descriptionId = useId();

  const load = () => {
    if (!projectId || !vcId) return;
    setLoading(true);
    setError('');
    Promise.all([
      api.getVerificationCase(projectId, vcId),
      api.listRequirements(projectId),
      api.listComponents(projectId),
    ]).then(([case_, reqs, comps]) => {
      setVc(case_);
      setRequirements(reqs);
      setComponents(comps);
      setLoading(false);
    }).catch((err: any) => {
      setVc(null);
      setError(err.message || 'Verification case not found');
      setLoading(false);
    });
  };

  useEffect(load, [projectId, vcId]);

  const save = async (patch: VerificationCaseUpdate) => {
    if (!projectId || !vcId) return;
    setError('');
    try {
      const updated = await api.updateVerificationCase(projectId, vcId, patch);
      setVc(updated);
      bumpDataVersion();
    } catch (err: any) {
      addToast('error', err.message || 'Save failed');
    }
  };

  const handleDelete = async () => {
    if (!projectId || !vcId) return;
    const ok = await showConfirm(`Delete verification case ${vcId}?`, 'Delete Verification Case', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      await api.deleteVerificationCase(projectId, vcId);
      addToast('success', `Verification case ${vcId} deleted`);
      navigate(`/project/${projectId}/verification`);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleLinkRequirement = async () => {
    const reqId = linkInput.trim();
    if (!projectId || !vcId || !vc || !reqId) return;
    if (vc.verified_requirements.includes(reqId)) {
      setLinkInput('');
      return;
    }
    const next = [...vc.verified_requirements, reqId];
    setVc({ ...vc, verified_requirements: next });
    setLinkInput('');
    await save({ verified_requirements: next });
    try {
      const req = await api.getRequirement(projectId, reqId);
      const vcs = [...(req.verification_cases || []), vcId];
      await api.updateRequirement(projectId, reqId, { verification_cases: vcs });
    } catch (err: any) {
      // requirement may not exist — VC link still saved above
      addToast('error', err.message || 'Failed to update requirement back-link');
    }
  };

  const handleUnlinkRequirement = async (reqId: string) => {
    if (!projectId || !vcId || !vc) return;
    const next = vc.verified_requirements.filter((r) => r !== reqId);
    setVc({ ...vc, verified_requirements: next });
    await save({ verified_requirements: next });
    try {
      const req = await api.getRequirement(projectId, reqId);
      const vcs = (req.verification_cases || []).filter((v: string) => v !== vcId);
      await api.updateRequirement(projectId, reqId, { verification_cases: vcs });
    } catch (err: any) {
      addToast('error', err.message || 'Failed to update requirement back-link');
    }
  };

  const handleAddStep = async () => {
    if (!projectId || !vcId || !vc || !stepAction.trim()) return;
    const next = [...(vc.steps || []), { action: stepAction.trim(), expected_result: stepExpected.trim(), actual_result: null }];
    setStepAction('');
    setStepExpected('');
    await save({ steps: next });
  };

  const handleUpdateStepResult = async (idx: number, actual: string) => {
    if (!vc) return;
    const steps = [...(vc.steps || [])];
    steps[idx] = { ...steps[idx], actual_result: actual };
    await save({ steps });
  };

  const handleAddMeasurement = async () => {
    if (!projectId || !vcId || !vc) return;
    const draft = measurement;
    if (!draft.parameter.trim() || draft.value.trim() === '') return;
    const next = [...(vc.measurements || []), {
      parameter: draft.parameter.trim(), value: Number(draft.value), unit: draft.unit.trim(),
    }];
    setMeasurement({ parameter: '', value: '', unit: '' });
    await save({ measurements: next });
  };

  const handleRemoveMeasurement = async (idx: number) => {
    if (!vc) return;
    const next = (vc.measurements || []).filter((_, i) => i !== idx);
    await save({ measurements: next });
  };

  const handleRunTest = async () => {
    if (!projectId || !vcId || !vc) return;
    setRunning(true);
    setRunFeedback(null);
    try {
      const stepResults: Record<string, string> = {};
      (vc.steps || []).forEach((_s, i) => {
        stepResults[String(i)] = '';
      });
      const updated = await api.runVerification(projectId, vcId, {
        status: vc.status === 'pending' ? 'in_progress' : vc.status,
        notes: '',
        step_results: stepResults,
      });
      setVc(updated);
      setRunFeedback({ type: 'success', message: 'Test completed' });
      bumpDataVersion();
    } catch (err) {
      setRunFeedback({ type: 'error', message: err instanceof Error ? err.message : 'Test failed' });
      addToast('error', err instanceof Error ? err.message : 'Test failed');
    } finally {
      setRunning(false);
      setTimeout(() => setRunFeedback(null), 4000);
    }
  };

  if (loading) {
    return <div className="relative h-[60vh]"><LoadingSplash label="Loading verification case…" /></div>;
  }

  if (!vc) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground">{error || 'Verification case not found.'}</p>
        <button onClick={() => navigate(`/project/${projectId}/verification`)} className="btn-secondary mt-4">
          <ArrowLeft size={14} /> Back to verification cases
        </button>
      </div>
    );
  }

  const StatusIcon = statusIcons[vc.status] || Clock;
  const linkedCount = vc.verified_requirements.length;
  const reqSuggestions = requirements
    .filter((r) => !vc.verified_requirements.includes(r.id))
    .map((r) => ({ id: r.id, label: r.name || r.id }));
  const measurementSuggestions = requirements
    .filter((r) => vc.verified_requirements.includes(r.id))
    .flatMap((r) => (r.parameters || []).map((p) => ({
      id: `${r.id}.${p.name}`, label: p.unit || '', unit: p.unit || '',
    })));
  const refReqs = requirements.filter(
    (r) => (r.verification_cases || []).includes(vc.id) && !vc.verified_requirements.includes(r.id),
  );
  const refComps = components.filter((c) => (c.verification_cases || []).includes(vc.id));

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/project/${projectId}/verification`)} className="btn-secondary p-2" aria-label="Back to verification cases">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StatusIcon size={16} className={statusIconColors[vc.status] || 'text-muted-foreground'} />
            <h1 className="text-xl font-bold tracking-tight font-mono text-foreground">{vc.id}</h1>
            <CopyLinkButton kind="verification" id={vc.id} />
          </div>
          <input
            className="input text-lg font-medium mt-1 w-full max-w-md"
            value={vc.name || ''}
            onChange={(e) => setVc({ ...vc, name: e.target.value })}
            onBlur={(e) => save({ name: e.target.value })}
            disabled={!editable}
            placeholder="Verification case name"
            aria-label="Name"
          />
        </div>
        <button onClick={handleDelete} className="btn-danger" disabled={!editable} title="Delete">
          <Trash2 size={14} />
        </button>
      </div>

      <div className="grid grid-cols-1 @4xl:grid-cols-3 gap-6">
        <div className="@4xl:col-span-2 space-y-6">
          <Reveal className="card p-5">
            <label className="label" htmlFor={descriptionId}>Description</label>
            {editable ? (
              <MentionTextarea
                id={descriptionId}
                className="input min-h-[64px]"
                value={vc.description || ''}
                onChange={(v) => setVc({ ...vc, description: v })}
                onBlur={() => save({ description: vc.description })}
                disabled={!editable}
                placeholder="What this case verifies…"
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[60px] opacity-90">
                {vc.description ? <AutoLinkText text={vc.description} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No description</span>}
              </div>
            )}
          </Reveal>

          <Reveal step={2} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-1.5">
              <LinkIcon size={14} /> Linked Requirements
            </h2>
            {editable && (
              <div className="flex gap-2 mb-3">
                <AutocompleteInput
                  className="input flex-1 text-xs font-mono"
                  placeholder="Add requirement ID..."
                  value={linkInput}
                  onChange={setLinkInput}
                  suggestions={reqSuggestions}
                />
                <button
                  onClick={handleLinkRequirement}
                  className="btn-secondary shrink-0"
                  disabled={!linkInput.trim()}
                >
                  <LinkIcon size={13} /> Link
                </button>
              </div>
            )}
            {linkedCount === 0 ? (
              <p className="text-xs text-muted-foreground py-1">No requirements linked.</p>
            ) : (
              <div className="space-y-1">
                {vc.verified_requirements.map((reqId) => (
                  <div key={reqId} className="flex items-center gap-2 text-xs py-1 px-2 rounded-md hover:bg-accent group/link">
                    <EntityLink
                      kind="requirement"
                      id={reqId}
                      name={requirements.find((r) => r.id === reqId)?.name}
                      className="flex-1 min-w-0 text-foreground hover:text-cs-blue"
                    />
                    {editable && (
                      <button onClick={() => handleUnlinkRequirement(reqId)} className="p-0.5 rounded-md text-muted-foreground hover:text-destructive opacity-0 group-hover/link:opacity-100 transition-[color,opacity]" title="Unlink requirement">
                        <X size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {(refReqs.length > 0 || refComps.length > 0) && (
              <div className="border-t mt-3 pt-3">
                <h4 className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Referenced By
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {refReqs.map((r) => (
                    <span key={r.id} className="inline-flex items-center px-2 py-1 rounded-md bg-muted text-xs">
                      <EntityLink kind="requirement" id={r.id} name={r.name} className="max-w-[220px] hover:text-primary" />
                    </span>
                  ))}
                  {refComps.map((c) => (
                    <span key={c.id} className="inline-flex items-center px-2 py-1 rounded-md bg-muted text-xs">
                      <EntityLink kind="component" id={c.id} name={c.name} subtype={c.type} className="max-w-[220px] hover:text-primary" />
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Reveal>

          <Reveal step={3} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-1.5">
              <ClipboardList size={14} /> Test Procedure
            </h2>
            {editable ? (
              <MentionTextarea
                className="input min-h-[60px] text-xs resize-y"
                placeholder="Describe the test procedure..."
                value={vc.test_procedure || ''}
                onChange={(v) => setVc({ ...vc, test_procedure: v })}
                onBlur={() => save({ test_procedure: vc.test_procedure })}
                disabled={!editable}
              />
            ) : (
              <p className="text-xs text-muted-foreground">{vc.test_procedure || 'No procedure defined.'}</p>
            )}
          </Reveal>

          <Reveal step={4} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-1.5">
              <ListChecks size={14} /> Test Steps
            </h2>
            {(vc.steps || []).length === 0 && !editable && (
              <p className="text-xs text-muted-foreground">No steps defined.</p>
            )}
            {(vc.steps || []).map((step, si) => (
              <div key={si} className="mb-2 pl-3 border-l-2 border-muted">
                <div className="flex items-start gap-2 text-xs">
                  <span className="font-mono text-3xs text-muted-foreground mt-0.5 shrink-0">#{si + 1}</span>
                  <div className="flex-1 min-w-0 space-y-1">
                    <div><span className="text-3xs text-muted-foreground">Action:</span> <span className="text-foreground">{step.action}</span></div>
                    <div><span className="text-3xs text-muted-foreground">Expected:</span> <span className="text-foreground">{step.expected_result}</span></div>
                    <div className="flex items-center gap-1">
                      <span className="text-3xs text-muted-foreground shrink-0">Actual:</span>
                      {editable ? (
                        <input
                          className="bg-transparent text-xs flex-1 border-b border-dashed border-muted-foreground/30 outline-none focus:border-primary/50 py-px"
                          placeholder="(enter actual result)"
                          value={step.actual_result || ''}
                          onChange={(e) => {
                            const steps = [...(vc.steps || [])];
                            steps[si] = { ...steps[si], actual_result: e.target.value };
                            setVc({ ...vc, steps });
                          }}
                          onBlur={(e) => handleUpdateStepResult(si, e.target.value)}
                        />
                      ) : (
                        <span className="text-foreground text-xs">{step.actual_result || '—'}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {editable && (
              <div className="flex gap-1.5 mt-2">
                <input
                  className="input flex-1 text-2xs"
                  placeholder="Step action..."
                  value={stepAction}
                  onChange={(e) => setStepAction(e.target.value)}
                />
                <input
                  className="input flex-1 text-2xs"
                  placeholder="Expected result..."
                  value={stepExpected}
                  onChange={(e) => setStepExpected(e.target.value)}
                />
                <button
                  onClick={handleAddStep}
                  className="btn-secondary shrink-0"
                  disabled={!stepAction.trim()}
                >
                  <Plus size={12} />
                </button>
              </div>
            )}
          </Reveal>

          <Reveal step={5} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-1.5">
              <FlaskConical size={14} /> Measurements
            </h2>
            {(vc.measurements || []).length === 0 && !editable && (
              <p className="text-xs text-muted-foreground">No measurements recorded.</p>
            )}
            {(vc.measurements || []).map((m, mi) => (
              <div key={mi} className="flex items-center gap-2 text-xs py-1 px-2 rounded-md hover:bg-accent group/meas">
                <EntityLink
                  kind="requirement"
                  id={m.parameter.split('.')[0]}
                  className="shrink-0 hover:text-primary"
                />
                <span className="font-mono text-muted-foreground flex-1 truncate">.{m.parameter.split('.').slice(1).join('.')}</span>
                <span className="font-mono text-foreground">{m.value}</span>
                <span className="text-muted-foreground w-10 truncate">{m.unit}</span>
                {editable && (
                  <button onClick={() => handleRemoveMeasurement(mi)} className="p-0.5 rounded-md text-muted-foreground hover:text-destructive opacity-0 group-hover/meas:opacity-100 transition-[color,opacity]">
                    <X size={11} />
                  </button>
                )}
              </div>
            ))}
            {editable && (
              <div className="flex gap-1.5 mt-1">
                <AutocompleteInput
                  className="input flex-1 text-2xs font-mono"
                  placeholder="REQID.parameter"
                  value={measurement.parameter}
                  onChange={(v) => {
                    const match = measurementSuggestions.find((s) => s.id === v);
                    setMeasurement({ ...measurement, parameter: v, unit: match?.unit || measurement.unit });
                  }}
                  suggestions={measurementSuggestions}
                />
                <input className="input w-24 text-2xs font-mono" placeholder="value"
                  value={measurement.value}
                  onChange={(e) => setMeasurement({ ...measurement, value: e.target.value })} />
                <input className="input w-16 text-2xs" placeholder="unit"
                  value={measurement.unit}
                  onChange={(e) => setMeasurement({ ...measurement, unit: e.target.value })} />
                <button
                  onClick={handleAddMeasurement}
                  className="btn-secondary shrink-0"
                  disabled={!measurement.parameter.trim() || measurement.value.trim() === ''}
                >
                  <Plus size={12} />
                </button>
              </div>
            )}
          </Reveal>

          <Reveal step={6} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Run Test</h2>
            {editable && (
              <button
                onClick={handleRunTest}
                disabled={running}
                className="btn-primary w-full justify-center text-xs disabled:opacity-60"
              >
                {running ? (
                  <Loader size={13} className="animate-spin" />
                ) : (
                  <Play size={13} />
                )} Run Test
              </button>
            )}
            {runFeedback && (
              <p className={`text-xs mt-1.5 ${runFeedback.type === 'success' ? 'text-cs-green' : 'text-cs-red'}`}>
                {runFeedback.type === 'success' ? (
                  <CheckCircle2 size={12} className="inline mr-1" />
                ) : (
                  <XCircle size={12} className="inline mr-1" />
                )}
                {runFeedback.message}
              </p>
            )}
          </Reveal>

          {(vc.execution_history || []).length > 0 && (
            <Reveal step={6} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">Execution History</h2>
              <div className="space-y-1.5">
                {(vc.execution_history || []).map((run, ri) => (
                  <div key={ri} className="flex items-center gap-2 text-3xs py-1 px-2 rounded-md bg-muted/30">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      run.status === 'passed' ? 'bg-cs-green' : run.status === 'failed' ? 'bg-cs-red' : 'bg-cs-amber'
                    }`} />
                    <span className="font-mono text-muted-foreground">{new Date(run.timestamp).toLocaleString()}</span>
                    <span className="text-foreground font-medium capitalize">{run.status}</span>
                    {run.executed_by && <span className="text-muted-foreground">by {run.executed_by}</span>}
                    {run.notes && <span className="text-muted-foreground">— {run.notes}</span>}
                  </div>
                ))}
              </div>
            </Reveal>
          )}

          <Reveal step={6} className="card p-5">
            <CommentThread entityKind="verification_cases" entityId={vc.id} />
          </Reveal>
          <Reveal step={6} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Change History</h2>
            <HistoryPanel itemId={vc.id} defaultOpen />
          </Reveal>
        </div>

        <div className="space-y-6">
          <Reveal step={1} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Properties</h2>
            <div className="space-y-3">
              <label className="label">Method
                <select className="select" value={vc.method || ''}
                  onChange={(e) => save({ method: e.target.value })} disabled={!editable}>
                  {METHOD_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <label className="label">Status
                <select className="select" value={vc.status || ''}
                  onChange={(e) => save({ status: e.target.value })} disabled={!editable}>
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <div className="flex items-center gap-2">
                <span className={`badge border ${statusBadges[vc.status] || ''}`}>{vc.status}</span>
              </div>
              {vc.result && (
                <p className="text-xs text-muted-foreground">{vc.result}</p>
              )}
            </div>
          </Reveal>

          <div className="text-xs text-muted-foreground space-y-1">
            <div>Created: {new Date(vc.created).toLocaleString()}</div>
            <div>Modified: {new Date(vc.modified).toLocaleString()}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
