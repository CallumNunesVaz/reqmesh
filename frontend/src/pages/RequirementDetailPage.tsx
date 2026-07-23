import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Trash2, ArrowLeft, Plus, X, ArrowRight, ArrowLeftRight, Sparkles, ShieldCheck, ExternalLink, ChevronRight, Waypoints, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { api, type Requirement, type VerificationCase, type QualityItem, type Component, type Specification, type ChangeRequest, type Risk, type EvaluatedRequirement, type Definition, type Comment, type DecisionRecord } from '../api/client';
import { ParametricsCard } from '../components/parametrics';
import RichTextEditor from '../components/RichTextEditor';
import AutocompleteInput from '../components/AutocompleteInput';
import { CopyLinkButton, EntityLink, type EntityKind } from '../components/entities';
import { AutoLinkHtml } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useUndoStore } from '../store/undo';
import { useGraphPane, useSelectedReq } from '../components/Layout';
import { HelpTip } from '../components/HelpTip';
import { useConfirm } from '../components/ConfirmDialog';
import DescriptionHelper from '../components/DescriptionHelper';
import ParametricsGuide from '../components/ParametricsGuide';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import LoadingSplash from '../components/LoadingSplash';

const typeOptions = ['functional', 'non_functional_performance', 'non_functional_security', 'non_functional_usability', 'non_functional_maintainability', 'non_functional_reliability', 'non_functional_scalability', 'non_functional_portability', 'interface', 'user', 'system', 'business', 'regulatory_compliance', 'safety', 'environmental', 'verification'];
const priorityOptions = ['low', 'medium', 'high', 'critical'];
const methodOptions = ['test', 'analysis', 'demonstration', 'inspection'];

export default function RequirementDetailPage() {
  const { projectId, reqId } = useParams<{ projectId: string; reqId: string }>();
  const navigate = useNavigate();
  const [req, setReq] = useState<Requirement | null>(null);
  const [loading, setLoading] = useState(true);
  const [allReqs, setAllReqs] = useState<Requirement[]>([]);
  const [allVcs, setAllVcs] = useState<VerificationCase[]>([]);
  const [satisfiedBy, setSatisfiedBy] = useState<Component[]>([]);
  const [inSpecs, setInSpecs] = useState<Specification[]>([]);
  const [evaluated, setEvaluated] = useState<EvaluatedRequirement | undefined>();
  const [definitions, setDefinitions] = useState<Definition[]>([]);
  const [affectingCrs, setAffectingCrs] = useState<ChangeRequest[]>([]);
  const [linkedRisks, setLinkedRisks] = useState<Risk[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const entityKinds = useEntityKinds(projectId);
  const { graphOpen, toggleGraph } = useGraphPane();
  const { selectReq } = useSelectedReq();
  const [newAttrKey, setNewAttrKey] = useState('');
  const [newAttrVal, setNewAttrVal] = useState('');
  const [newRelType, setNewRelType] = useState('refines');
  const [newRelTarget, setNewRelTarget] = useState('');
  const [reverseAdd, setReverseAdd] = useState(false);
  const [newVC, setNewVC] = useState('');
  const { user, editMode } = useAuthStore();
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const editable = user !== null && user.role !== 'viewer' && editMode;
  const showConfirm = useConfirm();
  const [workflow, setWorkflow] = useState<{ states: string[]; transitions: Record<string, string[]> } | null>(null);
  const [qualityResult, setQualityResult] = useState<QualityItem | null>(null);
  const [unreviewedIds, setUnreviewedIds] = useState<Set<string>>(new Set());
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [projectBaselines, setProjectBaselines] = useState<string[]>([]);
  const statusOptions = workflow?.states || ['proposed', 'approved', 'implemented', 'verified', 'rejected', 'deprecated'];

  const refSuggestions = useMemo(() => {
    const reqItems = [...allReqs, req].filter(Boolean).map((r) => ({ id: r!.id, label: r!.name || r!.id }));
    const vcItems = allVcs.map((v) => ({ id: v.id, label: v.name || v.id }));
    return [...reqItems, ...vcItems];
  }, [allReqs, req, allVcs]);

  const vcSuggestions = useMemo(
    () => allVcs.map((v) => ({ id: v.id, label: v.name || v.id })),
    [allVcs],
  );

  // Relations can point at either a requirement or a verification case, so the
  // link target depends on which one actually owns the id.
  const vcIds = useMemo(() => new Set(allVcs.map((v) => v.id)), [allVcs]);
  const kindOf = (id: string): EntityKind => (vcIds.has(id) ? 'verification' : 'requirement');

  // Ancestor chain from the root down to (excluding) this requirement, for
  // the breadcrumb. Guards against parent cycles in hand-edited YAML.
  const ancestors = useMemo(() => {
    if (!req?.parent) return [];
    const byId = new Map(allReqs.map((r) => [r.id, r]));
    const chain: { id: string; name: string }[] = [];
    const seen = new Set<string>([req.id]);
    let cursor: string | null = req.parent;
    while (cursor && !seen.has(cursor)) {
      seen.add(cursor);
      const parent = byId.get(cursor);
      chain.unshift({ id: cursor, name: parent?.name || '' });
      cursor = parent?.parent ?? null;
    }
    return chain;
  }, [req, allReqs]);

  const showInGraph = () => {
    if (!req) return;
    if (!graphOpen) toggleGraph();
    selectReq(req.id);
  };

  const incomingRelations = useMemo(() => {
    if (!req) return [];
    const results: { source: string; type: string; sourceName: string }[] = [];
    for (const r of allReqs) {
      for (const rel of r.relations || []) {
        if (rel.target === req.id) {
          results.push({ source: r.id, type: rel.type, sourceName: r.name || r.id });
        }
      }
    }
    return results;
  }, [allReqs, req]);

  useEffect(() => {
    if (!projectId || !reqId) return;
    Promise.all([
      api.getRequirement(projectId, reqId),
      api.listRequirements(projectId),
      api.listVerificationCases(projectId),
    ]).then(([data, all, vcs]) => {
      setReq(data);
      setAllReqs(all.filter((r) => r.id !== reqId));
      setAllVcs(vcs);
      setLoading(false);
    }).catch(console.error);
    api.getComponentsForRequirement(projectId, reqId).then(setSatisfiedBy).catch(() => setSatisfiedBy([]));
    // Backlinks: everything else in the project that names this requirement.
    api.listSpecifications(projectId)
      .then((specs) => setInSpecs(specs.filter((s) => s.requirements.includes(reqId))))
      .catch(() => setInSpecs([]));
    api.listChangeRequests(projectId)
      .then((crs) => setAffectingCrs(crs.filter((c) => c.affected_requirements.includes(reqId))))
      .catch(() => setAffectingCrs([]));
    api.listRisks(projectId)
      .then((risks) => setLinkedRisks(risks.filter((r) => r.linked_requirements.includes(reqId))))
      .catch(() => setLinkedRisks([]));
    api.getEvaluation(projectId)
      .then((ev) => setEvaluated(ev.requirements.find((r) => r.id === reqId)))
      .catch(() => setEvaluated(undefined));
    api.listDefinitions(projectId).then(setDefinitions).catch(() => setDefinitions([]));
    api.getWorkflow(projectId).then((wf) => setWorkflow(wf)).catch(() => {});
    api.getQuality(projectId).then((q) => {
      const match = q.per_requirement.find((r) => r.id === reqId);
      if (match) setQualityResult(match);
    }).catch(() => {});
    api.getUnreviewed(projectId).then((u) => {
      setUnreviewedIds(new Set(u.items.map((r) => r.id)));
    }).catch(() => {});
    api.getProject(projectId).then((p: any) => setProjectBaselines(p.baselines || [])).catch(() => {});
    api.listComments(projectId, reqId).then(setComments).catch(() => setComments([]));
    api.listDecisions(projectId).then((decs) => setDecisions(decs.filter((d) => d.linked_requirements?.includes(reqId)))).catch(() => setDecisions([]));
  }, [projectId, reqId]);

  const save = async (updates: Partial<Requirement>) => {
    if (!projectId || !reqId || !req || !editable) return;
    const beforeFields: Record<string, any> = {};
    for (const k of Object.keys(updates)) {
      beforeFields[k] = (req as any)[k];
    }
    try {
      const updated = await api.updateRequirement(projectId, reqId, updates);
      useUndoStore.getState().push({
        description: `Update ${reqId}`,
        undo: async () => { await api.updateRequirementSkipWorkflow(projectId, reqId, beforeFields); },
        redo: async () => { await api.updateRequirement(projectId, reqId, updates); },
      });
      setReq(updated);
      setSaveError('');
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      bumpGraphVersion();
      if (updates.parameters || updates.constraints) {
        api.getEvaluation(projectId)
          .then((ev) => setEvaluated(ev.requirements.find((r) => r.id === reqId)))
          .catch(() => {});
      }
    } catch (err: any) {
      setSaveError(err?.message || 'Save failed');
      setTimeout(() => setSaveError(''), 5000);
    }
  };

  const handleDelete = async () => {
    if (!projectId || !reqId || !req) return;
    const ok = await showConfirm('Delete this requirement?', 'Delete Requirement');
    if (!ok) return;
    const snap = { ...req };
    await api.deleteRequirement(projectId, reqId);
    useUndoStore.getState().push({
      description: `Delete ${reqId}`,
      undo: async () => { await api.createRequirement(projectId, snap); },
      redo: async () => { await api.deleteRequirement(projectId, reqId); },
    });
    bumpGraphVersion();
    bumpDataVersion();
    navigate(`/project/${projectId}/requirements`);
  };

  useKeyboardShortcuts(projectId, {
    onDetailSave: () => req && save({}),
    onDetailDelete: handleDelete,
    onDetailEscape: () => { if (window.history.length > 1) navigate(-1); else navigate(`/project/${projectId}/requirements`); },
  });

  if (loading) {
    return <div className="relative h-[60vh]"><LoadingSplash label="Loading requirement…" /></div>;
  }

  if (!req) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground">Requirement not found.</p>
        <button onClick={() => navigate(`/project/${projectId}/requirements`)} className="btn-secondary mt-4">
          <ArrowLeft size={14} /> Back to list
        </button>
      </div>
    );
  }

  const addAttribute = () => {
    if (!newAttrKey.trim() || !newAttrVal.trim()) return;
    save({ attributes: [...req.attributes, { key: newAttrKey.trim(), value: newAttrVal.trim() }] });
    setNewAttrKey('');
    setNewAttrVal('');
  };

  const removeAttribute = (index: number) => {
    save({ attributes: req.attributes.filter((_, i) => i !== index) });
  };

  const addRelation = async () => {
    if (!newRelTarget.trim() || !projectId || !reqId) return;
    if (reverseAdd) {
      const target = allReqs.find((r) => r.id === newRelTarget.trim());
      if (!target) {
        try {
          await api.updateRequirement(projectId, newRelTarget.trim(), {
            relations: [...((await api.getRequirement(projectId, newRelTarget.trim())).relations || []), { type: newRelType, target: reqId }],
          });
        } catch { /* target might not exist yet */ }
      } else {
        await api.updateRequirement(projectId, target.id, {
          relations: [...target.relations, { type: newRelType, target: reqId }],
        });
      }
    } else {
      save({ relations: [...req.relations, { type: newRelType, target: newRelTarget.trim() }] });
    }
    setNewRelTarget('');
    setReverseAdd(false);
    bumpGraphVersion();
  };

  const removeRelation = (index: number) => {
    save({ relations: req.relations.filter((_, i) => i !== index) });
  };

  const flipRelation = async (index: number, targetId: string, relType: string) => {
    if (!projectId || !reqId || !req) return;
    const updatedRelations = req.relations.filter((_, i) => i !== index);
    await api.updateRequirement(projectId, reqId, { relations: updatedRelations });
    setReq({ ...req, relations: updatedRelations });

    try {
      const targetReq = await api.getRequirement(projectId, targetId);
      const targetRelations = [...(targetReq.relations || []), { type: relType, target: reqId }];
      await api.updateRequirement(projectId, targetId, { relations: targetRelations });
      setAllReqs((prev) => {
        const exists = prev.find((r) => r.id === targetId);
        if (exists) return prev.map((r) => r.id === targetId ? { ...r, relations: targetRelations } : r);
        return prev;
      });
    } catch {
      // Target may be a VC or doesn't exist — still removed from source above.
    }
    bumpGraphVersion();
  };

  const addVerificationCase = () => {
    if (!newVC.trim()) return;
    save({ verification_cases: [...req.verification_cases, newVC.trim()] });
    setNewVC('');
  };

  const removeVerificationCase = (index: number) => {
    save({ verification_cases: req.verification_cases.filter((_, i) => i !== index) });
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      {saveError && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2">
          <AlertTriangle size={14} /> {saveError}
          <button onClick={() => setSaveError('')} className="ml-auto text-red-400/50 hover:text-red-400">
            <X size={14} />
          </button>
        </div>
      )}
      {saveSuccess && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm flex items-center gap-2">
          <CheckCircle2 size={14} /> Saved
        </div>
      )}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/project/${projectId}/requirements`)} className="btn-secondary p-2">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          {ancestors.length > 0 && (
            <nav className="flex items-center gap-1 text-[11px] text-muted-foreground mb-0.5 flex-wrap">
              {ancestors.map((a) => (
                <span key={a.id} className="inline-flex items-center gap-1">
                  <EntityLink kind="requirement" id={a.id} showIcon={false} className="hover:text-primary" />
                  <ChevronRight size={10} className="shrink-0" />
                </span>
              ))}
              <span className="font-mono text-foreground/70">{req.id}</span>
            </nav>
          )}
          <div className="flex items-center gap-1.5">
            <h1 className="text-xl font-bold tracking-tight font-mono text-foreground">{req.id}</h1>
            <CopyLinkButton kind="requirement" id={req.id} />
          </div>
          {unreviewedIds.has(req.id) && (
            <span className="badge bg-amber-500/10 text-amber-400 text-[10px] px-2 py-0.5">Needs re-review</span>
          )}
        </div>
        <button onClick={showInGraph} className="btn-secondary text-xs" title="Select this requirement in the graph pane">
          <Waypoints size={14} /> Show in graph
        </button>
        {editable && (
          <button
            onClick={async () => {
              await api.reviewRequirement(projectId!, reqId!);
              const updated = await api.getRequirement(projectId!, reqId!);
              setReq(updated);
              setUnreviewedIds((prev) => { const next = new Set(prev); next.delete(reqId!); return next; });
            }}
            className="btn-secondary text-xs mr-2"
          >
            <ShieldCheck size={14} /> Review
          </button>
        )}
        <button onClick={handleDelete} className="btn-danger" disabled={!editable}>
          <Trash2 size={14} /> Delete
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
            <label className="label">Name</label>
            <input
              className="input text-lg font-medium"
              value={req.name}
              onChange={(e) => setReq({ ...req, name: e.target.value })}
              onBlur={(e) => save({ name: e.target.value })}
              disabled={!editable}
            />
            <label className="label mt-4 flex items-center gap-2">
              Description
              <DescriptionHelper description={req.description} verificationMethod={req.verification_method} />
            </label>
            {editable ? (
              <RichTextEditor
                content={req.description}
                onChange={(html) => { setReq({ ...req, description: html }); }}
                onBlur={(html) => save({ description: html })}
                disabled={false}
              />
            ) : (
              // Read mode: render the rich text with entity ids linked, which
              // the editor (even disabled) can't do.
              <AutoLinkHtml
                html={req.description}
                kinds={entityKinds}
                className="prose prose-sm dark:prose-invert max-w-none border rounded-lg p-3 min-h-[80px] opacity-90"
              />
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-1">Relations</h2>
            <HelpTip>Link this requirement to others using relationship types like refines, satisfies, derives, or conflicts. Relations form the traceability graph — they show which requirements depend on or are detailed by others.</HelpTip>

            {/* Add outgoing relation */}
            {editable && (
            <div className="flex items-end gap-1.5 mb-4">
              <div className="flex-1 bg-muted/40 rounded-lg p-2.5 border">
                <div className="flex items-center gap-1.5 text-[11px]">
                  <span className="font-mono font-semibold text-foreground">{req.id}</span>
                  <ArrowRight size={12} className="text-muted-foreground shrink-0" />
                  <select className="bg-transparent text-[11px] font-medium text-primary border-b border-dashed border-primary/30 px-0.5 py-px outline-none cursor-pointer" value={newRelType} onChange={(e) => setNewRelType(e.target.value)}>
                    <option value="refines">refines</option>
                    <option value="satisfies">satisfies</option>
                    <option value="verified_by">verified by</option>
                    <option value="derives">derives</option>
                    <option value="conflicts">conflicts</option>
                    <option value="duplicates">duplicates</option>
                  </select>
                  <ArrowRight size={12} className="text-muted-foreground shrink-0" />
                  <AutocompleteInput
                    className="bg-transparent flex-1 text-[11px] font-mono outline-none min-w-0 placeholder:text-muted-foreground/50"
                    placeholder="target ID..."
                    value={newRelTarget}
                    onChange={setNewRelTarget}
                    suggestions={refSuggestions}
                  />
                </div>
              </div>
              <button
                onClick={() => setReverseAdd(!reverseAdd)}
                className={`p-2 rounded-lg border transition-all shrink-0 ${reverseAdd ? 'bg-primary/10 border-primary/30 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-accent'}`}
                title={reverseAdd ? 'Direction: target → this (click to swap)' : 'Direction: this → target (click to swap)'}
              >
                <ArrowLeftRight size={14} />
              </button>
              <button onClick={addRelation} className="btn-secondary shrink-0" disabled={!newRelTarget.trim()}>
                <Plus size={14} />
              </button>
            </div>
            )}

            {/* Outgoing: THIS → ... */}
            <div className="mb-3">
              <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Outgoing
                <span className="ml-1 font-normal normal-case text-[10px] text-muted-foreground/60">
                  ({req.id} → target)
                </span>
              </h3>
              {req.relations.length === 0 ? (
                <p className="text-xs text-muted-foreground pl-1">None</p>
              ) : (
                <div className="space-y-1">
                  {req.relations.map((rel, i) => {
                    const targetName = allReqs.find((r) => r.id === rel.target)?.name
                      || allVcs.find((v) => v.id === rel.target)?.name;
                    return (
                      <div key={`out-${i}`} className="flex items-center gap-2 text-xs group py-1.5 px-2 rounded hover:bg-accent">
                        <span className="font-mono text-[11px] font-semibold text-foreground shrink-0">{req.id}</span>
                        <ArrowRight size={11} className="text-muted-foreground shrink-0" />
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary shrink-0">{rel.type.replace(/_/g, ' ')}</span>
                        <ArrowRight size={11} className="text-muted-foreground shrink-0" />
                        <EntityLink
                          kind={kindOf(rel.target)}
                          id={rel.target}
                          name={targetName}
                          className="text-[11px] text-foreground hover:text-primary flex-1 min-w-0"
                        />
                        {editable && (
                        <div className="flex items-center gap-0.5">
                          <button
                            onClick={() => flipRelation(i, rel.target, rel.type)}
                            className="p-1 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 transition-all"
                            title={`Flip: make ${rel.target} → ${rel.type} → ${req.id}`}
                          >
                            <ArrowLeftRight size={11} />
                          </button>
                          <button onClick={() => removeRelation(i)} className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                            <X size={12} />
                          </button>
                        </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Incoming: ... → THIS */}
            <div>
              <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Incoming
                <span className="ml-1 font-normal normal-case text-[10px] text-muted-foreground/60">
                  (source → {req.id})
                </span>
              </h3>
              {incomingRelations.length === 0 ? (
                <p className="text-xs text-muted-foreground pl-1">None</p>
              ) : (
                <div className="space-y-1">
                  {incomingRelations.map((inc, i) => (
                    <div key={`in-${i}`} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent/50">
                      <EntityLink
                        kind={kindOf(inc.source)}
                        id={inc.source}
                        name={inc.sourceName !== inc.source ? inc.sourceName : undefined}
                        className="text-[11px] text-foreground hover:text-primary flex-1 min-w-0"
                      />
                      <ArrowRight size={11} className="text-muted-foreground shrink-0" />
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 shrink-0">{inc.type.replace(/_/g, ' ')}</span>
                      <ArrowRight size={11} className="text-muted-foreground shrink-0" />
                      <span className="font-mono text-[11px] font-semibold text-foreground shrink-0">{req.id}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>

          <ParametricsGuide />

          <ParametricsCard
            reqId={req.id}
            parameters={req.parameters || []}
            constraints={req.constraints || []}
            evaluated={evaluated}
            editable={editable}
            onSave={save}
            definitions={definitions}
          />

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-1">Verification Cases</h2>
            <HelpTip>Verification cases prove that this requirement is met. They can be tests, analyses, demonstrations, or inspections. Link existing VCs or create new ones from the Verification page.</HelpTip>
            <div className="flex gap-2 mt-2 mb-3">
              <AutocompleteInput
                className="input flex-1 font-mono text-sm"
                placeholder="VC ID (e.g. VC-001)"
                value={newVC}
                onChange={setNewVC}
                suggestions={vcSuggestions}
                disabled={!editable}
              />
              <button onClick={addVerificationCase} className="btn-secondary shrink-0" disabled={!editable}><Plus size={14} /></button>
            </div>
            {req.verification_cases.length === 0 ? (
              <p className="text-xs text-muted-foreground">No verification cases linked.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {req.verification_cases.map((vc, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-xs text-foreground group">
                    <EntityLink
                      kind="verification"
                      id={vc}
                      name={allVcs.find((v) => v.id === vc)?.name}
                      className="hover:text-primary"
                    />
                    {editable && (
                    <button onClick={() => removeVerificationCase(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                      <X size={10} />
                    </button>
                    )}
                  </span>
                ))}
              </div>
            )}
          </motion.div>

          {/* The design side of the house: which components claim to realise
              this requirement. Read-only here — the mapping is owned by the
              component, so editing it lives on the Components page. */}
          {satisfiedBy.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">Satisfied By</h2>
              <div className="flex flex-wrap gap-2">
                {satisfiedBy.map((c) => (
                  <span key={c.id} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-xs text-foreground">
                    <EntityLink kind="component" id={c.id} name={c.name} className="hover:text-primary" />
                  </span>
                ))}
              </div>
            </motion.div>
          )}

          {qualityResult && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><Sparkles size={14} className="text-violet-400" /> Quality</h2>
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold ${qualityResult.score >= 80 ? 'bg-emerald-500/10 text-emerald-400' : qualityResult.score >= 50 ? 'bg-amber-500/10 text-amber-400' : 'bg-red-500/10 text-red-400'}`}>
                  {qualityResult.score}
                </div>
                <div className="flex-1">
                  <div className="w-full bg-muted rounded-full h-2">
                    <div className={`h-full rounded-full transition-all duration-500 ${qualityResult.score >= 80 ? 'bg-emerald-500' : qualityResult.score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${qualityResult.score}%` }} />
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-1">/100</div>
                </div>
              </div>
              {qualityResult.findings.length > 0 && (
                <div className="space-y-1">
                  {qualityResult.findings.slice(0, 5).map((f, i) => (
                    <div key={i} className={`text-xs px-2 py-1 rounded ${f.severity === 'error' ? 'bg-red-500/5 text-red-400' : f.severity === 'warning' ? 'bg-amber-500/5 text-amber-400' : 'bg-muted text-muted-foreground'}`}>
                      {f.message}
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Attributes</h2>
            <div className="flex gap-1 mb-3">
              <input className="input flex-1 text-xs" placeholder="Key" value={newAttrKey} onChange={(e) => setNewAttrKey(e.target.value)} disabled={!editable} />
              <input className="input flex-1 text-xs" placeholder="Value" value={newAttrVal} onChange={(e) => setNewAttrVal(e.target.value)} disabled={!editable} />
              <button onClick={addAttribute} className="btn-secondary shrink-0 p-2" disabled={!editable}><Plus size={12} /></button>
            </div>
            {req.attributes.length === 0 ? (
              <p className="text-xs text-muted-foreground">No custom attributes.</p>
            ) : (
              <div className="space-y-1.5">
                {req.attributes.map((attr, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs group py-1 px-2 rounded hover:bg-accent">
                    <span className="font-medium text-muted-foreground w-24 shrink-0 truncate">{attr.key}</span>
                    <span className="text-foreground flex-1 truncate">{attr.value}</span>
                    {editable && (
                    <button onClick={() => removeAttribute(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                      <X size={12} />
                    </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </motion.div>

          {/* Backlinks: things that name this requirement from their own
              side. Read-only here — each mapping is owned by the other
              entity, so editing lives on its page. */}
          {inSpecs.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.23 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">In Specifications</h2>
              <div className="flex flex-wrap gap-2">
                {inSpecs.map((s) => (
                  <span key={s.id} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-xs text-foreground">
                    <EntityLink kind="specification" id={s.id} name={s.name} className="hover:text-primary" />
                  </span>
                ))}
              </div>
            </motion.div>
          )}

          {(affectingCrs.length > 0 || linkedRisks.length > 0) && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">Change Requests &amp; Risks</h2>
              <div className="space-y-1.5">
                {affectingCrs.map((c) => (
                  <div key={c.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                    <EntityLink kind="change" id={c.id} name={c.title} className="flex-1 min-w-0 text-foreground hover:text-primary" />
                    <span className="badge bg-muted text-muted-foreground shrink-0">{c.status}</span>
                  </div>
                ))}
                {linkedRisks.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                    <EntityLink kind="risk" id={r.id} name={r.title} className="flex-1 min-w-0 text-foreground hover:text-primary" />
                    <span className="badge bg-muted text-muted-foreground shrink-0">{r.severity}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {req.references && req.references.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">References</h2>
              <div className="space-y-1.5">
                {req.references.map((ref, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group">
                    <span className={`badge text-[9px] shrink-0 ${ref.kind === 'impl' ? 'bg-blue-500/10 text-blue-400' : ref.kind === 'test' ? 'bg-purple-500/10 text-purple-400' : ref.kind === 'doc' ? 'bg-teal-500/10 text-teal-400' : 'bg-muted text-muted-foreground'}`}>{ref.kind}</span>
                    <span className="font-mono text-[11px] text-foreground flex-1 truncate">{ref.path}</span>
                    {ref.lines && <span className="text-[10px] text-muted-foreground shrink-0">{ref.lines}</span>}
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {comments.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center justify-between">
                <span>Comments ({comments.length})</span>
                <AddCommentForm projectId={projectId!} reqId={reqId!} onAdded={() => api.listComments(projectId!, reqId).then(setComments).catch(() => {})} disabled={!editable} />
              </h2>
              <div className="space-y-3">
                {comments.map((c) => (
                  <div key={c.id} className={`flex items-start gap-3 p-2.5 rounded-lg text-xs ${c.resolved ? 'bg-muted/30 opacity-60' : 'bg-accent/30'}`}>
                    <span className="w-1 self-stretch rounded-full shrink-0" style={{ background: 'hsl(var(--primary) / 0.4)' }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-medium text-foreground">{c.author}</span>
                        <span className="text-muted-foreground">{new Date(c.created).toLocaleDateString()}</span>
                        {c.resolved && <span className="badge bg-emerald-500/10 text-emerald-400 text-[9px]">Resolved</span>}
                      </div>
                      <p className="text-muted-foreground leading-relaxed">{c.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {decisions.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.27 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">Related Decisions ({decisions.length})</h2>
              <div className="space-y-2">
                {decisions.map((d) => (
                  <div key={d.id} className="p-2.5 rounded-lg bg-accent/20 text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono font-medium text-foreground">{d.id}</span>
                      <span className="font-medium">{d.title}</span>
                      <span className="badge bg-muted text-muted-foreground ml-auto">{d.status}</span>
                    </div>
                    <p className="text-muted-foreground leading-relaxed line-clamp-2">{d.decision}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </div>

        <div className="space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-1">Properties</h2>
            <HelpTip>Classification metadata for this requirement. Type describes what kind of requirement it is. Status tracks its lifecycle. Priority reflects stakeholder importance. Verification method selects the approach used to prove it.</HelpTip>
            <div className="space-y-3 mt-2">
              <div>
                <label className="label">Type</label>
                <select className="select" value={req.type} onChange={(e) => save({ type: e.target.value })} disabled={!editable}>
                  {typeOptions.map((t) => {
                    let label = t.replace(/_/g, ' ');
                    if (t.startsWith('non_functional_')) {
                      label = 'Non-Functional \u2013 ' + t.slice('non_functional_'.length).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    } else {
                      label = label.replace(/\b\w/g, c => c.toUpperCase());
                    }
                    return (<option key={t} value={t}>{label}</option>);
                  })}
                </select>
              </div>
              <div>
                <label className="label">Kind</label>
                <select className="select" value={req.requirement_kind || 'system_requirement'} onChange={(e) => save({ requirement_kind: e.target.value as any })} disabled={!editable}>
                  <option value="system_requirement">System Requirement</option>
                  <option value="stakeholder_need">Stakeholder Need</option>
                </select>
                <div className="text-[10px] text-muted-foreground mt-0.5">OOSEM: system requirement vs stakeholder need</div>
              </div>
              <div>
                <label className="label">System States</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="takeoff, cruise, landing"
                  value={(req.system_states || []).join(', ')}
                  onBlur={(e) => save({ system_states: e.target.value ? e.target.value.split(',').map(s => s.trim()).filter(Boolean) : [] })}
                  disabled={!editable}
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">OOSEM: modes this requirement applies to</div>
              </div>
              <div>
                <label className="label">Status</label>
                <select className="select" value={req.status} onChange={(e) => save({ status: e.target.value })} disabled={!editable}>
                  {statusOptions.map((s) => (<option key={s} value={s}>{s}</option>))}
                </select>
                {workflow && editable && (
                  <div className="text-[10px] text-muted-foreground mt-1 flex flex-wrap gap-1">
                    <span>Next:</span>
                    {(workflow.transitions[req.status] || []).map((t) => (
                      <button
                        key={t}
                        onClick={() => save({ status: t })}
                        className="px-1.5 py-px rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                      >
                        {t}
                      </button>
                    ))}
                    {(workflow.transitions[req.status] || []).length === 0 && (
                      <span className="text-muted-foreground/60">terminal</span>
                    )}
                  </div>
                )}
              </div>
              <div>
                <label className="label">Priority</label>
                <select className="select" value={req.priority} onChange={(e) => save({ priority: e.target.value })} disabled={!editable}>
                  {priorityOptions.map((p) => (<option key={p} value={p}>{p}</option>))}
                </select>
              </div>
              <div>
                <label className="label flex items-center justify-between">
                  <span>Derived</span>
                  <input type="checkbox" checked={req.derived || false} onChange={(e) => save({ derived: e.target.checked })} disabled={!editable} className="w-4 h-4 rounded border-muted-foreground/30" />
                </label>
                <div className="text-[10px] text-muted-foreground mt-0.5">No parent link required</div>
              </div>
              <div>
                <label className="label flex items-center justify-between">
                  <span>Normative</span>
                  <input type="checkbox" checked={req.normative !== false} onChange={(e) => save({ normative: e.target.checked })} disabled={!editable} className="w-4 h-4 rounded border-muted-foreground/30" />
                </label>
                <div className="text-[10px] text-muted-foreground mt-0.5">Included in coverage analysis</div>
              </div>
              <div>
                <label className="label">Coverage Needs</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="e.g. design, verification_case"
                  value={(req.needs || []).join(', ')}
                  onChange={(e) => {
                    const needs = e.target.value ? e.target.value.split(',').map(s => s.trim()).filter(Boolean) : [];
                    setReq({ ...req, needs });
                  }}
                  onBlur={(e) => {
                    const needs = e.target.value ? e.target.value.split(',').map(s => s.trim()).filter(Boolean) : [];
                    save({ needs });
                  }}
                  disabled={!editable}
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">Artifact types that must cover this requirement</div>
              </div>
              <div>
                <label className="label">Subject</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="e.g. WING (the part this requirement constrains)"
                  value={req.subject || ''}
                  onChange={(e) => setReq({ ...req, subject: e.target.value })}
                  onBlur={(e) => save({ subject: e.target.value || null } as Partial<Requirement>)}
                  disabled={!editable}
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">SysML v2 subject — the component this requirement is about</div>
              </div>
              <div>
                <label className="label">Stakeholder Priorities</label>
                <textarea
                  className="input font-mono text-xs h-16 resize-none"
                  placeholder="development: 5&#10;customers: 8&#10;safety: 10"
                  value={Object.entries(req.priorities || {}).map(([k, v]) => `${k}: ${v}`).join('\n')}
                  onChange={(e) => {
                    const prio: Record<string, number> = {};
                    for (const line of e.target.value.split('\n')) {
                      const [k, v] = line.split(':').map(s => s.trim());
                      if (k && v && !isNaN(Number(v))) prio[k] = Number(v);
                    }
                    setReq({ ...req, priorities: prio });
                  }}
                  onBlur={(e) => {
                    const prio: Record<string, number> = {};
                    for (const line of e.target.value.split('\n')) {
                      const [k, v] = line.split(':').map(s => s.trim());
                      if (k && v && !isNaN(Number(v))) prio[k] = Number(v);
                    }
                    save({ priorities: prio });
                  }}
                  disabled={!editable}
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">Per-stakeholder priority scores (e.g. development: 5)</div>
              </div>
              <div>
                <label className="label">Effort (story points)</label>
                <input
                  className="input"
                  type="number"
                  min="0"
                  value={req.effort ?? ''}
                  onBlur={(e) => {
                    const v = parseInt(e.target.value);
                    save({ effort: !isNaN(v) && v >= 0 ? v : null });
                  }}
                  disabled={!editable}
                />
              </div>
              <div>
                <label className="label">Verification Method</label>
                <select className="select" value={req.verification_method} onChange={(e) => save({ verification_method: e.target.value })} disabled={!editable}>
                  {methodOptions.map((m) => (<option key={m} value={m}>{m}</option>))}
                </select>
              </div>
              <div>
                <label className="label">Verification Status</label>
                <select className="select" value={req.verification_status || 'pending'} onChange={(e) => save({ verification_status: e.target.value })} disabled={!editable}>
                  <option value="pending">Pending</option>
                  <option value="in_progress">In Progress</option>
                  <option value="passed">Passed</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
              <div>
                <label className="label">Parent</label>
                {/* The select owns the value; an <option> can't be a link, so
                    navigation to the parent gets its own button beside it. */}
                <div className="flex items-center gap-1.5">
                  <select
                    className="select flex-1 min-w-0"
                    value={req.parent || ''}
                    onChange={(e) => save({ parent: e.target.value || null })}
                    disabled={!editable}
                  >
                    <option value="">None (top-level)</option>
                    {allReqs.map((r) => (
                      <option key={r.id} value={r.id}>{r.id} - {r.name}</option>
                    ))}
                  </select>
                  {req.parent && (
                    <Link
                      to={`/project/${projectId}/requirements/${encodeURIComponent(req.parent)}`}
                      title={`Go to parent ${req.parent}`}
                      className="p-2 rounded-md text-muted-foreground hover:text-primary hover:bg-accent transition-colors shrink-0"
                    >
                      <ExternalLink size={14} />
                    </Link>
                  )}
                </div>
              </div>
              <div>
                <label className="label">Rationale</label>
                <input
                  className="input"
                  placeholder="Why this requirement exists..."
                  value={req.rationale || ''}
                  onChange={(e) => setReq({ ...req, rationale: e.target.value })}
                  onBlur={(e) => save({ rationale: e.target.value })}
                  disabled={!editable}
                />
              </div>
              <div>
                <label className="label">Source</label>
                <input
                  className="input"
                  placeholder="Stakeholder/document reference..."
                  value={req.source || ''}
                  onChange={(e) => setReq({ ...req, source: e.target.value })}
                  onBlur={(e) => save({ source: e.target.value })}
                  disabled={!editable}
                />
              </div>
              <div>
                <label className="label">Allocated To</label>
                <input
                  className="input"
                  placeholder="System element..."
                  value={req.allocated_to || ''}
                  onChange={(e) => setReq({ ...req, allocated_to: e.target.value })}
                  onBlur={(e) => save({ allocated_to: e.target.value })}
                  disabled={!editable}
                />
              </div>
              <div>
                <label className="label">Baselines</label>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {projectBaselines.map((b) => {
                    const active = (req.baselines || []).includes(b);
                    return (
                      <button
                        key={b}
                        type="button"
                        onClick={() => {
                          const current = req.baselines || [];
                          const next = active ? current.filter(x => x !== b) : [...current, b];
                          save({ baselines: next });
                        }}
                        disabled={!editable}
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                          active
                            ? 'bg-primary/15 text-primary border-primary/30'
                            : 'bg-muted text-muted-foreground border-transparent hover:border-primary/20'
                        }`}
                      >
                        {b}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </motion.div>

          <div className="text-xs text-muted-foreground space-y-1">
            <div>Created: {new Date(req.created).toLocaleString()}</div>
            <div>Modified: {new Date(req.modified).toLocaleString()}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AddCommentForm({ projectId, reqId, onAdded, disabled }: { projectId: string; reqId: string; onAdded: () => void; disabled: boolean }) {
  const [show, setShow] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const user = useAuthStore((s) => s.user);

  if (!show) {
    return disabled ? null : (
      <button onClick={() => setShow(true)} className="text-xs text-muted-foreground hover:text-foreground">+ Add comment</button>
    );
  }

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.createComment(projectId, { requirement_id: reqId, author: user?.username || 'unknown', text: text.trim() });
      setText('');
      setShow(false);
      onAdded();
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  return (
    <div className="flex gap-1.5 mt-1">
      <input className="input text-xs flex-1" placeholder="Write a comment..." value={text}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setShow(false); }} autoFocus />
      <button onClick={submit} disabled={busy || !text.trim()} className="btn-primary text-xs">{busy ? '...' : 'Send'}</button>
    </div>
  );
}
