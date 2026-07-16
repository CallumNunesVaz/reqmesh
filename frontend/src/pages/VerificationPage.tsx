import { useCallback, useEffect, useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, CheckCircle2, Trash2, XCircle, Clock, ChevronDown, X, Link as LinkIcon, Play, ListChecks, ClipboardList } from 'lucide-react';
import { api, type VerificationCase, type Requirement } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import AutocompleteInput from '../components/AutocompleteInput';
import { EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';

const statusBadges: Record<string, string> = {
  pending: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  in_progress: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  passed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  failed: 'border-red-500/30 bg-red-500/10 text-red-400',
};

const statusIconColors: Record<string, string> = {
  pending: 'bg-amber-500/10 text-amber-400',
  in_progress: 'bg-blue-500/10 text-blue-400',
  passed: 'bg-emerald-500/10 text-emerald-400',
  failed: 'bg-red-500/10 text-red-400',
};

const statusIcons: Record<string, React.ComponentType<any>> = {
  pending: Clock,
  in_progress: XCircle,
  passed: CheckCircle2,
  failed: XCircle,
};

export default function VerificationPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { verificationCases, setVerificationCases } = useStore();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [showCreate, setShowCreate] = useState(false);
  const [newVC, setNewVC] = useState({ id: '', name: '', description: '', method: 'test' });
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [linkReqInput, setLinkReqInput] = useState<Record<string, string>>({});
  const [newStepAction, setNewStepAction] = useState<Record<string, string>>({});
  const [newStepExpected, setNewStepExpected] = useState<Record<string, string>>({});

  const load = () => {
    if (!projectId) return;
    Promise.all([
      api.listVerificationCases(projectId),
      api.listRequirements(projectId),
    ]).then(([vcs, reqs]) => {
      setVerificationCases(vcs);
      setRequirements(reqs);
    }).catch(console.error);
  };

  useEffect(() => { load(); }, [projectId]);

  const reqSuggestions = useMemo(
    () => requirements.map((r) => ({ id: r.id, label: r.name || r.id })),
    [requirements],
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !newVC.id.trim() || !editable) return;
    try {
      await api.createVerificationCase(projectId, newVC);
      setShowCreate(false);
      setNewVC({ id: '', name: '', description: '', method: 'test' });
      load();
    } catch {
      // silently no-op
    }
  };

  const handleDelete = async (vcId: string) => {
    if (!projectId) return;
    if (!confirm(`Delete verification case ${vcId}?`)) return;
    await api.deleteVerificationCase(projectId, vcId);
    setVerificationCases(verificationCases.filter((v) => v.id !== vcId));
  };

  const handleStatusChange = async (vcId: string, status: string) => {
    if (!projectId) return;
    await api.updateVerificationCase(projectId, vcId, { status });
    load();
  };

  const toggleExpand = (vcId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(vcId)) next.delete(vcId);
      else next.add(vcId);
      return next;
    });
  };

  const getLinkInput = (vcId: string) => linkReqInput[vcId] || '';
  const setLinkInput = (vcId: string, val: string) => {
    setLinkReqInput((prev) => ({ ...prev, [vcId]: val }));
  };
  const getStepAction = (vcId: string) => newStepAction[vcId] || '';
  const setStepAction = (vcId: string, val: string) => setNewStepAction((p) => ({ ...p, [vcId]: val }));
  const getStepExpected = (vcId: string) => newStepExpected[vcId] || '';
  const setStepExpected = (vcId: string, val: string) => setNewStepExpected((p) => ({ ...p, [vcId]: val }));

  const handleLinkRequirement = async (vcId: string) => {
    const reqId = getLinkInput(vcId).trim();
    if (!projectId || !reqId) return;
    const vc = verificationCases.find((v) => v.id === vcId);
    if (!vc) return;
    if (vc.verified_requirements.includes(reqId)) {
      setLinkInput(vcId, '');
      return;
    }
    await api.updateVerificationCase(projectId, vcId, {
      verified_requirements: [...vc.verified_requirements, reqId],
    });
    try {
      const req = await api.getRequirement(projectId, reqId);
      const vcs = [...(req.verification_cases || []), vcId];
      await api.updateRequirement(projectId, reqId, { verification_cases: vcs });
    } catch {
      // requirement may not exist — VC link still saved above
    }
    setLinkInput(vcId, '');
    load();
  };

  const handleUnlinkRequirement = async (vcId: string, reqId: string) => {
    if (!projectId) return;
    const vc = verificationCases.find((v) => v.id === vcId);
    if (!vc) return;
    await api.updateVerificationCase(projectId, vcId, {
      verified_requirements: vc.verified_requirements.filter((r) => r !== reqId),
    });
    try {
      const req = await api.getRequirement(projectId, reqId);
      const vcs = (req.verification_cases || []).filter((v: string) => v !== vcId);
      await api.updateRequirement(projectId, reqId, { verification_cases: vcs });
    } catch {
      // requirement may not exist
    }
    load();
  };

  const handleAddStep = async (vcId: string, action: string, expected: string) => {
    if (!projectId || !action.trim()) return;
    const vc = verificationCases.find((v) => v.id === vcId);
    if (!vc) return;
    const steps = [...(vc.steps || []), { action: action.trim(), expected_result: expected.trim(), actual_result: null }];
    await api.updateVerificationCase(projectId, vcId, { steps } as any);
    load();
  };

  const handleUpdateStepResult = async (vcId: string, stepIdx: number, actual: string) => {
    if (!projectId) return;
    const vc = verificationCases.find((v) => v.id === vcId);
    if (!vc) return;
    const steps = [...(vc.steps || [])];
    if (stepIdx < steps.length) {
      steps[stepIdx] = { ...steps[stepIdx], actual_result: actual };
    }
    await api.updateVerificationCase(projectId, vcId, { steps } as any);
    load();
  };

  const handleUpdateProcedure = async (vcId: string, procedure: string) => {
    if (!projectId) return;
    await api.updateVerificationCase(projectId, vcId, { test_procedure: procedure } as any);
    load();
  };

  const handleRunTest = async (vcId: string) => {
    if (!projectId) return;
    const vc = verificationCases.find((v) => v.id === vcId);
    if (!vc) return;
    const stepResults: Record<string, string> = {};
    (vc.steps || []).forEach((_s, i) => {
      stepResults[String(i)] = '';
    });
    await api.runVerification(projectId, vcId, {
      status: vc.status === 'pending' ? 'in_progress' : vc.status,
      notes: '',
      step_results: stepResults,
    });
    load();
  };

  // Arriving from a link elsewhere (?focus=VC-001): open that case and scroll
  // to it, so the reference lands on the thing it pointed at.
  const focusId = useFocusedEntity(
    verificationCases.length > 0,
    useCallback((id: string) => setExpanded((prev) => new Set(prev).add(id)), []),
  );

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Verification Cases</h1>
          <p className="text-sm text-muted-foreground mt-1">{verificationCases.length} verification cases</p>
        </div>
        {editable && (
        <button onClick={() => setShowCreate(!showCreate)} className="btn-primary">
          <Plus size={16} /> New Verification Case
        </button>
        )}
      </div>

      <AnimatePresence>
        {showCreate && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate}
            className="card p-4 mb-4 overflow-hidden"
          >
            <div className="flex items-end gap-3">
              <div className="w-40">
                <label className="label">ID</label>
                <input className="input font-mono" placeholder="VC-001" value={newVC.id} onChange={(e) => setNewVC({ ...newVC, id: e.target.value })} autoFocus />
              </div>
              <div className="flex-1">
                <label className="label">Name</label>
                <input className="input" placeholder="Verification case name" value={newVC.name} onChange={(e) => setNewVC({ ...newVC, name: e.target.value })} />
              </div>
              <div>
                <label className="label">Method</label>
                <select className="select" value={newVC.method} onChange={(e) => setNewVC({ ...newVC, method: e.target.value })}>
                  <option value="test">Test</option>
                  <option value="analysis">Analysis</option>
                  <option value="demonstration">Demonstration</option>
                  <option value="inspection">Inspection</option>
                </select>
              </div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {verificationCases.length === 0 ? (
        <div className="card p-12 text-center">
          <CheckCircle2 size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No verification cases yet</p>
          <p className="text-sm text-muted-foreground mt-1">Create verification cases to track requirement testing.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {verificationCases.map((vc, i) => {
            const StatusIcon = statusIcons[vc.status] || Clock;
            const isExpanded = expanded.has(vc.id);
            const linkedCount = vc.verified_requirements.length;
            return (
              <motion.div
                key={vc.id}
                id={`entity-${vc.id}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`card hover:shadow-md transition-shadow group ${
                  focusId === vc.id ? 'ring-2 ring-primary/50' : ''
                }`}
              >
                <div
                  className="flex items-center gap-3 p-4 cursor-pointer"
                  onClick={() => toggleExpand(vc.id)}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${statusIconColors[vc.status] || 'bg-muted text-muted-foreground'}`}>
                    <StatusIcon size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{vc.id}</span>
                      <h3 className="font-medium text-card-foreground">{vc.name || 'Untitled'}</h3>
                      <span className={`badge border ${statusBadges[vc.status] || ''}`}>
                        {vc.status}
                      </span>
                    </div>
                    {vc.description && (
                      <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">{vc.description}</p>
                    )}
                    <div className="flex gap-3 mt-2 text-xs text-muted-foreground">
                      <span>Method: <strong className="text-foreground">{vc.method}</strong></span>
                      <span>{linkedCount} linked requirement{linkedCount !== 1 ? 's' : ''}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <select
                      className="select text-xs py-1 w-28"
                      value={vc.status}
                      onChange={(e) => handleStatusChange(vc.id, e.target.value)}
                      disabled={!editable}
                    >
                      <option value="pending">Pending</option>
                      <option value="in_progress">In Progress</option>
                      <option value="passed">Passed</option>
                      <option value="failed">Failed</option>
                    </select>
                    {editable && (
                    <button
                      onClick={() => handleDelete(vc.id)}
                      className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <Trash2 size={14} />
                    </button>
                    )}
                  </div>
                  <ChevronDown
                    size={15}
                    className={`text-muted-foreground transition-transform duration-200 shrink-0 ${isExpanded ? 'rotate-180' : ''}`}
                  />
                </div>

                <AnimatePresence initial={false}>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="overflow-hidden"
                    >
                      <div className="px-4 pb-4 border-t pt-3 space-y-3">
                        {/* Linked Requirements */}
                        {editable && (
                        <div className="flex gap-2">
                          <AutocompleteInput
                            className="input flex-1 text-xs font-mono"
                            placeholder="Add requirement ID..."
                            value={getLinkInput(vc.id)}
                            onChange={(v) => setLinkInput(vc.id, v)}
                            suggestions={reqSuggestions.filter(
                              (s) => !vc.verified_requirements.includes(s.id)
                            )}
                          />
                          <button
                            onClick={(e) => { e.stopPropagation(); handleLinkRequirement(vc.id); }}
                            className="btn-secondary shrink-0"
                            disabled={!getLinkInput(vc.id).trim()}
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
                              <div key={reqId} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent group/link">
                                <EntityLink
                                  kind="requirement"
                                  id={reqId}
                                  name={requirements.find((r) => r.id === reqId)?.name}
                                  className="flex-1 min-w-0 text-foreground hover:text-cs-blue"
                                />
                                {editable && (
                                <button onClick={(e) => { e.stopPropagation(); handleUnlinkRequirement(vc.id, reqId); }} className="p-0.5 rounded text-muted-foreground hover:text-destructive opacity-0 group-hover/link:opacity-100 transition-all" title="Unlink requirement">
                                  <X size={11} />
                                </button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Test Procedure */}
                        <div className="border-t pt-3">
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <ClipboardList size={12} /> Test Procedure
                          </h4>
                          {editable ? (
                            <textarea
                              className="input min-h-[60px] text-xs resize-y"
                              placeholder="Describe the test procedure..."
                              value={vc.test_procedure || ''}
                              onChange={(e) => { e.stopPropagation(); handleUpdateProcedure(vc.id, e.target.value); }}
                            />
                          ) : (
                            <p className="text-xs text-muted-foreground">{vc.test_procedure || 'No procedure defined.'}</p>
                          )}
                        </div>

                        {/* Test Steps */}
                        <div>
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <ListChecks size={12} /> Test Steps
                          </h4>
                          {(vc.steps || []).length === 0 && !editable && (
                            <p className="text-xs text-muted-foreground">No steps defined.</p>
                          )}
                          {(vc.steps || []).map((step, si) => (
                            <div key={si} className="mb-2 pl-3 border-l-2 border-muted">
                              <div className="flex items-start gap-2 text-xs">
                                <span className="font-mono text-[10px] text-muted-foreground mt-0.5 shrink-0">#{si + 1}</span>
                                <div className="flex-1 min-w-0 space-y-1">
                                  <div><span className="text-[10px] text-muted-foreground">Action:</span> <span className="text-foreground">{step.action}</span></div>
                                  <div><span className="text-[10px] text-muted-foreground">Expected:</span> <span className="text-foreground">{step.expected_result}</span></div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-muted-foreground shrink-0">Actual:</span>
                                    {editable ? (
                                      <input
                                        className="bg-transparent text-xs flex-1 border-b border-dashed border-muted-foreground/30 outline-none focus:border-primary/50 py-px"
                                        placeholder="(enter actual result)"
                                        value={step.actual_result || ''}
                                        onBlur={(e) => handleUpdateStepResult(vc.id, si, e.target.value)}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          const vcUpdated = { ...vc, steps: [...(vc.steps || [])] };
                                          vcUpdated.steps[si] = { ...vcUpdated.steps[si], actual_result: e.target.value };
                                        }}
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
                              className="input flex-1 text-[11px]"
                              placeholder="Step action..."
                              value={getStepAction(vc.id)}
                              onChange={(e) => setStepAction(vc.id, e.target.value)}
                            />
                            <input
                              className="input flex-1 text-[11px]"
                              placeholder="Expected result..."
                              value={getStepExpected(vc.id)}
                              onChange={(e) => setStepExpected(vc.id, e.target.value)}
                            />
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleAddStep(vc.id, getStepAction(vc.id), getStepExpected(vc.id));
                                setStepAction(vc.id, '');
                                setStepExpected(vc.id, '');
                              }}
                              className="btn-secondary shrink-0"
                              disabled={!getStepAction(vc.id).trim()}
                            >
                              <Plus size={12} />
                            </button>
                          </div>
                          )}
                        </div>

                        {/* Run Test */}
                        {editable && (
                        <div className="border-t pt-3">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRunTest(vc.id); }}
                            className="btn-primary w-full justify-center text-xs"
                          >
                            <Play size={13} /> Run Test
                          </button>
                        </div>
                        )}

                        {/* Execution History */}
                        {(vc.execution_history || []).length > 0 && (
                        <div className="border-t pt-3">
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                            Execution History
                          </h4>
                          <div className="space-y-1.5">
                            {(vc.execution_history || []).map((run, ri) => (
                              <div key={ri} className="flex items-center gap-2 text-[10px] py-1 px-2 rounded bg-muted/30">
                                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                  run.status === 'passed' ? 'bg-emerald-500' : run.status === 'failed' ? 'bg-red-500' : 'bg-amber-500'
                                }`} />
                                <span className="font-mono text-muted-foreground">{new Date(run.timestamp).toLocaleString()}</span>
                                <span className="text-foreground font-medium capitalize">{run.status}</span>
                                {run.executed_by && <span className="text-muted-foreground">by {run.executed_by}</span>}
                                {run.notes && <span className="text-muted-foreground">— {run.notes}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
