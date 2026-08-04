import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GuardedLink as Link } from '../components/navGuard';
import { motion } from 'framer-motion';
import { Trash2, ArrowLeft, Plus, X, ArrowRight, ArrowLeftRight, Sparkles, ShieldCheck, ExternalLink, ChevronRight, Waypoints, AlertTriangle, CheckCircle2, GitFork, Loader, Save, Undo2 } from 'lucide-react';
import { api, baselineNames, type StakeholderDef, type RequirementValue, type Requirement, type VerificationCase, type QualityItem, type Component, type Specification, type ChangeRequest, type Risk, type EvaluatedRequirement, type Definition, type Comment, type DecisionRecord, type Backlinks } from '../api/client';
import { ParametricsCard } from '../components/parametrics';
import RichTextEditor from '../components/RichTextEditor';
import AutocompleteInput from '../components/AutocompleteInput';
import { CopyLinkButton, EntityLink, type EntityKind } from '../components/entities';
import { AutoLinkHtml } from '../components/autoLink';
import { ModalText } from '../components/ModalText';
import { useEntityKinds } from '../components/entityIndex';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useUndoStore } from '../store/undo';
import { useGraphPane, useSelectedReq } from '../components/Layout';
import { HelpTip } from '../components/HelpTip';
import { useConfirm } from '../components/ConfirmDialog';
import { deleteWithReferenceCheck } from '../lib/forceDelete';
import DescriptionHelper from '../components/DescriptionHelper';
import ParametricsGuide from '../components/ParametricsGuide';
import { LinkEditor } from '../components/LinkEditor';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import LoadingSplash from '../components/LoadingSplash';
import { statusColors } from '../components/RequirementNode';
import { REQUIREMENT_TYPE_META, formatReqType, reqTypeColor, typeOptionsFor } from '../lib/requirementTypes';
const priorityOptions = ['low', 'medium', 'high', 'critical'];
const priorityColorMap: Record<string, string> = {
  low: 'hsl(195,6%,62%)',
  medium: 'hsl(207,90%,64%)',
  high: 'hsl(28,100%,53%)',
  critical: 'hsl(0,84%,68%)',
};
const verifStatusColorMap: Record<string, string> = {
  pending: 'hsl(195,6%,62%)',
  in_progress: 'hsl(207,90%,64%)',
  passed: 'hsl(145,55%,42%)',
  failed: 'hsl(0,84%,68%)',
};
/** Registry collection -> the entity kinds EntityLink knows how to render.
 *  Collections without a detail page of their own (decisions, analysis cases)
 *  fall back to a plain chip rather than linking somewhere that 404s. */
const BACKLINK_KINDS: Record<string, EntityKind> = {
  requirements: 'requirement',
  components: 'component',
  verification_cases: 'verification',
  specifications: 'specification',
  change_requests: 'change',
  risks: 'risk',
};
// Modal keywords are highlighted by decorating the *text nodes* of the shared
// renderer, rather than by re-implementing it. AutoLinkHtml takes renderPlain
// for exactly this: entity ids still link, and only the prose between them is
// styled.
const withModals = (text: string) => <ModalText>{text}</ModalText>;
export default function RequirementDetailPage() {
  const { projectId, reqId } = useParams<{ projectId: string; reqId: string }>();
  const navigate = useNavigate();
  const [req, setReq] = useState<Requirement | null>(null);
  const [loading, setLoading] = useState(true);
  const [allReqs, setAllReqs] = useState<Requirement[]>([]);
  const [allVcs, setAllVcs] = useState<VerificationCase[]>([]);
  const [satisfiedBy, setSatisfiedBy] = useState<Component[]>([]);
  const [allComponents, setAllComponents] = useState<Component[]>([]);
  const [coverageNeedOptions, setCoverageNeedOptions] = useState<{ value: string; label: string }[]>([]);
  const [projectStakeholders, setProjectStakeholders] = useState<StakeholderDef[]>([]);
  const [reqValue, setReqValue] = useState<RequirementValue | null>(null);
  const [inSpecs, setInSpecs] = useState<Specification[]>([]);
  const [evaluated, setEvaluated] = useState<EvaluatedRequirement | undefined>();
  const [definitions, setDefinitions] = useState<Definition[]>([]);
  const [affectingCrs, setAffectingCrs] = useState<ChangeRequest[]>([]);
  const [linkedRisks, setLinkedRisks] = useState<Risk[]>([]);
  const [mitigatingRisks, setMitigatingRisks] = useState<Risk[]>([]);
  const [allRisksRaw, setAllRisksRaw] = useState<Risk[]>([]);
  const [backlinks, setBacklinks] = useState<Backlinks | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const entityKinds = useEntityKinds(projectId);
  const { graphOpen, toggleGraph } = useGraphPane();
  const { selectReq, showDerivation } = useSelectedReq();
  const [newAttrKey, setNewAttrKey] = useState('');
  const [newAttrVal, setNewAttrVal] = useState('');
  const [newRelType, setNewRelType] = useState('refines');
  const [newRelTarget, setNewRelTarget] = useState('');
  const [reverseAdd, setReverseAdd] = useState(false);
  const [newVC, setNewVC] = useState('');
  const { user } = useAuthStore();
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const setNavGuard = useStore((s) => s.setNavGuard);
  // Requirement fields are edit-tier (maintainer + edit mode); comments are
  // propose-tier (contributor+, no edit-mode gate).
  const editable = useAuthStore((s) => s.canEdit());
  const canPropose = useAuthStore((s) => s.canPropose());
  const showConfirm = useConfirm();
  const [workflow, setWorkflow] = useState<{ states: string[]; transitions: Record<string, string[]> } | null>(null);
  const [qualityResult, setQualityResult] = useState<QualityItem | null>(null);
  const [unreviewedIds, setUnreviewedIds] = useState<Set<string>>(new Set());
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const savedRef = useRef<Requirement | null>(null);
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
  const traceDerivation = () => {
    if (!req) return;
    if (!graphOpen) toggleGraph();
    showDerivation(req.id);
  };
  // Allocation goes through the same endpoint the Allocation Matrix page uses
  // (component.satisfies is the real relationship; req.allocated_to is a
  // display string the backend derives from it), rather than through the
  // normal dirty/save flow — the backend has already committed the change by
  // the time this returns, so req/savedRef are updated directly to keep the
  // dirty-diff and discard-changes logic from treating allocated_to as a
  // pending edit.
  // LinkEditor's option shape is {id, name}; a Risk calls its label `title`.
  const allRisks = useMemo(
    () => allRisksRaw.map((r) => ({ id: r.id, name: r.title })),
    [allRisksRaw],
  );
  /** Add or remove this requirement from a risk's linked_requirements. The
   *  link is owned by the risk, so this writes the risk — the same record the
   *  Risks page edits — rather than anything on the requirement. */
  const setRiskLink = async (riskId: string, linked: boolean) => {
    if (!projectId || !reqId) return;
    const risk = allRisksRaw.find((r) => r.id === riskId);
    if (!risk) return;
    const next = linked
      ? [...risk.linked_requirements, reqId]
      : risk.linked_requirements.filter((x) => x !== reqId);
    const updated = { ...risk, linked_requirements: next };
    setAllRisksRaw((prev) => prev.map((r) => (r.id === riskId ? updated : r)));
    setLinkedRisks((prev) => (linked ? [...prev, updated] : prev.filter((r) => r.id !== riskId)));
    try {
      await api.updateRisk(projectId, riskId, { linked_requirements: next });
    } catch (err) {
      console.error(err);
      api.listRisks(projectId).then((risks) => {
        setAllRisksRaw(risks);
        setLinkedRisks(risks.filter((r) => r.linked_requirements.includes(reqId)));
      }).catch(() => {});
    }
  };
  /** Add or remove this requirement from a risk's mitigating_requirements.
   *  Mirrors setRiskLink; the risk owns both lists. */
  const setMitigatingRiskLink = async (riskId: string, linked: boolean) => {
    if (!projectId || !reqId) return;
    const risk = allRisksRaw.find((r) => r.id === riskId);
    if (!risk) return;
    const next = linked
      ? [...(risk.mitigating_requirements || []), reqId]
      : (risk.mitigating_requirements || []).filter((x) => x !== reqId);
    const updated = { ...risk, mitigating_requirements: next };
    setAllRisksRaw((prev) => prev.map((r) => (r.id === riskId ? updated : r)));
    setMitigatingRisks((prev) => (linked ? [...prev, updated] : prev.filter((r) => r.id !== riskId)));
    try {
      await api.updateRisk(projectId, riskId, { mitigating_requirements: next });
    } catch (err) {
      console.error(err);
      api.listRisks(projectId).then((risks) => {
        setAllRisksRaw(risks);
        setMitigatingRisks(risks.filter((r) => (r.mitigating_requirements || []).includes(reqId)));
      }).catch(() => {});
    }
  };
  const allocateComponent = async (componentId: string, allocated: boolean) => {
    if (!projectId || !reqId) return;
    try {
      const result = await api.setAllocation(projectId, reqId, componentId, allocated);
      setSatisfiedBy((prev) => allocated
        ? (prev.some((c) => c.id === componentId)
            ? prev
            : [...prev, ...allComponents.filter((c) => c.id === componentId)])
        : prev.filter((c) => c.id !== componentId));
      setReq((r) => (r ? { ...r, allocated_to: result.allocated_to } : r));
      if (savedRef.current) savedRef.current = { ...savedRef.current, allocated_to: result.allocated_to };
    } catch (err) {
      console.error(err);
    }
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
    // Every fetch below is guarded: this page is NOT remounted per requirement
    // (no route key), so clicking REQ-A then REQ-B quickly could let A's slower
    // response land last and set `req`/`savedRef` while the URL says B. Delete
    // then removed B while the undo entry snapshotted A, making B unrecoverable.
    let alive = true;
    Promise.all([
      api.getRequirement(projectId, reqId),
      api.listRequirements(projectId),
      api.listVerificationCases(projectId),
    ]).then(([data, all, vcs]) => {
      if (!alive) return;
      setReq(data);
      // Re-anchor the saved baseline (and clear dirty) to the freshly loaded
      // requirement. This effect only re-runs on navigation, and the page is
      // not remounted per-requirement (no route key), so without this the
      // previous requirement's baseline would leak across and corrupt the
      // dirty/discard/undo diffing.
      savedRef.current = data;
      setDirty(false);
      setAllReqs(all.filter((r) => r.id !== reqId));
      setAllVcs(vcs);
    }).catch((err) => { if (alive) console.error(err); }).finally(() => { if (alive) setLoading(false); });
    api.getComponentsForRequirement(projectId, reqId).then((v) => { if (alive) setSatisfiedBy(v); }).catch(() => { if (alive) setSatisfiedBy([]); });
    api.listComponents(projectId).then((v) => { if (alive) setAllComponents(v); }).catch(() => { if (alive) setAllComponents([]); });
    api.getCoverageNeeds().then((v) => { if (alive) setCoverageNeedOptions(v.items); }).catch(() => { if (alive) setCoverageNeedOptions([]); });
    // Backlinks: everything else in the project that names this requirement.
    api.listSpecifications(projectId)
      .then((specs) => { if (alive) setInSpecs(specs.filter((s) => s.requirements.includes(reqId))); })
      .catch(() => { if (alive) setInSpecs([]); });
    api.listChangeRequests(projectId)
      .then((crs) => { if (alive) setAffectingCrs(crs.filter((c) => c.affected_requirements.includes(reqId))); })
      .catch(() => { if (alive) setAffectingCrs([]); });
    api.listRisks(projectId)
      .then((risks) => {
        if (!alive) return;
        setAllRisksRaw(risks);
        setLinkedRisks(risks.filter((r) => r.linked_requirements.includes(reqId)));
        setMitigatingRisks(risks.filter((r) => (r.mitigating_requirements || []).includes(reqId)));
      })
      .catch(() => { if (alive) { setAllRisksRaw([]); setLinkedRisks([]); setMitigatingRisks([]); } });
    api.getBacklinks(projectId, reqId)
      .then((b) => { if (alive) setBacklinks(b); })
      .catch(() => { if (alive) setBacklinks(null); });
    api.getEvaluation(projectId)
      .then((ev) => { if (alive) setEvaluated(ev.requirements.find((r) => r.id === reqId)); })
      .catch(() => { if (alive) setEvaluated(undefined); });
    api.listDefinitions(projectId).then((v) => { if (alive) setDefinitions(v); }).catch(() => { if (alive) setDefinitions([]); });
    api.getWorkflow(projectId).then((wf) => { if (alive) setWorkflow(wf); }).catch(() => {});
    api.getQuality(projectId).then((q) => {
      const match = q.per_requirement.find((r) => r.id === reqId);
      if (alive && match) setQualityResult(match);
    }).catch(() => {});
    api.getUnreviewed(projectId).then((u) => {
      if (alive) setUnreviewedIds(new Set(u.items.map((r) => r.id)));
    }).catch(() => {});
    api.getProject(projectId).then((p) => {
      if (!alive) return;
      setProjectBaselines(baselineNames(p.baselines));
      setProjectStakeholders(p.stakeholders || []);
    }).catch(() => {});
    api.getRequirementValue(projectId, reqId).then((v) => { if (alive) setReqValue(v); }).catch(() => { if (alive) setReqValue(null); });
    api.listComments(projectId, reqId).then((v) => { if (alive) setComments(v); }).catch(() => { if (alive) setComments([]); });
    api.listDecisions(projectId).then((decs) => { if (alive) setDecisions(decs.filter((d) => d.linked_requirements?.includes(reqId))); }).catch(() => { if (alive) setDecisions([]); });
    return () => { alive = false; };
  }, [projectId, reqId]);
  const save = (updates: Partial<Requirement>) => {
    if (!req || !editable || !savedRef.current) return;
    const next = { ...req, ...updates } as Requirement;
    setReq(next);
    for (const key of Object.keys(updates)) {
      const cur = JSON.stringify((next as any)[key]);
      const was = JSON.stringify((savedRef.current as any)[key]);
      if (cur !== was) { setDirty(true); return; }
    }
  };
  const discardChanges = () => {
    if (!savedRef.current) return;
    setReq(savedRef.current);
    setDirty(false);
    setSaveError('');
    setSaveSuccess(false);
  };
  const commitSave = useCallback(async () => {
    if (!projectId || !reqId || !req || !editable) return;
    const saved = savedRef.current;
    if (!saved) return;
    const diff: Record<string, any> = {};
    for (const key of Object.keys(req)) {
      if (key === 'modified' || key === 'created') continue;
      if (key === 'verification_method' || key === 'verification_status' || key === 'verification_methods') continue;
      if (JSON.stringify((req as any)[key]) !== JSON.stringify((saved as any)[key])) {
        diff[key] = (req as any)[key];
      }
    }
    if (Object.keys(diff).length === 0) { setDirty(false); return; }
    const beforeFields: Record<string, any> = {};
    for (const k of Object.keys(diff)) {
      beforeFields[k] = (saved as any)[k];
    }
    setSaving(true);
    try {
      const updated = await api.updateRequirement(projectId, reqId, diff);
      useUndoStore.getState().push({
        description: `Update ${reqId}`,
        undo: async () => { await api.updateRequirement(projectId, reqId, beforeFields); },
        redo: async () => { await api.updateRequirement(projectId, reqId, diff); },
      });
      setReq(updated);
      savedRef.current = updated;
      setSaveError('');
      setSaveSuccess(true);
      setDirty(false);
      setTimeout(() => setSaveSuccess(false), 2000);
      bumpGraphVersion();
      if (diff.parameters || diff.constraints) {
        api.getEvaluation(projectId)
          .then((ev) => setEvaluated(ev.requirements.find((r) => r.id === reqId)))
          .catch(() => {});
      }
      api.getUnreviewed(projectId).then((u) => {
        setUnreviewedIds(new Set(u.items.map((r) => r.id)));
      }).catch(() => {});
      // The value and rank depend on this requirement's scores *and* on every
      // other requirement's, so they are recomputed server-side after a save
      // rather than derived locally.
      if (diff.priorities) {
        api.getRequirementValue(projectId, reqId).then(setReqValue).catch(() => {});
      }
    } catch (err: any) {
      setSaveError(err?.message || 'Save failed');
      setTimeout(() => setSaveError(''), 5000);
    } finally {
      setSaving(false);
    }
  }, [projectId, reqId, req, editable, dirty, bumpGraphVersion]);
  // Unsaved-changes guard. `dirty` is read through a ref so the registered
  // guard and the beforeunload handler stay stable while always seeing the
  // current value. Returns true when it's safe to leave.
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const confirmLeave = useCallback(async () => {
    if (!dirtyRef.current) return true;
    return showConfirm('You have unsaved changes. Discard them and leave?', 'Discard changes');
  }, [showConfirm]);
  // Register the in-app guard so the requirement nav tree (and any other
  // navigator) prompts before discarding edits; clear it on unmount.
  useEffect(() => {
    setNavGuard(confirmLeave);
    return () => setNavGuard(null);
  }, [confirmLeave, setNavGuard]);
  // Browser-level guard for reload / tab close / external navigation.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);
  const handleDelete = async () => {
    if (!projectId || !reqId || !req) return;
    const ok = await showConfirm('Delete this requirement?', 'Delete Requirement');
    if (!ok) return;
    const snap = { ...req };
    try {
      const done = await deleteWithReferenceCheck(
        (force) => api.deleteRequirement(projectId, reqId, force),
        (msg) => showConfirm(msg, 'Referenced by other records'),
      );
      if (!done) return;
    } catch (e: any) {
      setSaveError(e?.message || 'Delete failed');
      return;
    }
    useUndoStore.getState().push({
      description: `Delete ${reqId}`,
      undo: async () => { await api.createRequirement(projectId, snap); },
      redo: async () => { await api.deleteRequirement(projectId, reqId, true); },
    });
    bumpGraphVersion();
    bumpDataVersion();
    navigate(`/project/${projectId}/requirements`);
  };
  useKeyboardShortcuts(projectId, {
    onDetailSave: () => req && commitSave(),
    onDetailDelete: handleDelete,
    onDetailEscape: async () => {
      if (!(await confirmLeave())) return;
      if (window.history.length > 1) navigate(-1); else navigate(`/project/${projectId}/requirements`);
    },
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
        } catch (e: any) {
          console.warn('Reverse relation add on target %s failed: %s', newRelTarget.trim(), e?.message || e);
        }
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
    const updated = { ...req, relations: updatedRelations };
    setReq(updated);
    savedRef.current = updated;
    try {
      const targetReq = await api.getRequirement(projectId, targetId);
      const targetRelations = [...(targetReq.relations || []), { type: relType, target: reqId }];
      await api.updateRequirement(projectId, targetId, { relations: targetRelations });
      setAllReqs((prev) => {
        const exists = prev.find((r) => r.id === targetId);
        if (exists) return prev.map((r) => r.id === targetId ? { ...r, relations: targetRelations } : r);
        return prev;
      });
    } catch (e: any) {
      console.warn('Relation flip on target %s failed: %s', targetId, e?.message || e);
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
    <div className="max-w-6xl mx-auto p-8">
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
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button onClick={async () => { if (await confirmLeave()) navigate(`/project/${projectId}/requirements`); }} className="btn-secondary p-2">
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
        <button
          onClick={traceDerivation}
          className="btn-secondary text-xs"
          title="Highlight everything that derives from this requirement — all incoming links, and their incoming links, expanding any collapsed groups on the way"
        >
          <GitFork size={14} /> Show derivation
        </button>
        {editable && unreviewedIds.has(req.id) && (
          <button
            onClick={async () => {
              const ok = await showConfirm(
                'Record this requirement as reviewed? Its current content will be snapshotted — if any tracked fields change later, a "Needs re-review" warning will appear.',
                'Mark Reviewed',
              );
              if (!ok) return;
              setReviewing(true);
              setSaveError('');
              setSaveSuccess(false);
              try {
                await api.reviewRequirement(projectId!, reqId!);
                const updated = await api.getRequirement(projectId!, reqId!);
                setReq(updated);
                savedRef.current = updated;
                setUnreviewedIds((prev) => { const next = new Set(prev); next.delete(reqId!); return next; });
                setSaveSuccess(true);
                setTimeout(() => setSaveSuccess(false), 2000);
              } catch (err: any) {
                setSaveError(err.message || 'Review failed');
              } finally {
                setReviewing(false);
              }
            }}
            className="btn-secondary text-xs mr-2"
            disabled={reviewing}
          >
            {reviewing ? (
              <><Loader size={14} className="animate-spin" /> Reviewing…</>
            ) : (
              <><ShieldCheck size={14} /> Mark Reviewed</>
            )}
          </button>
        )}
        {dirty && (
          <>
            <button
              onClick={commitSave}
              className="btn-primary text-xs p-2"
              disabled={saving}
              title="Save changes"
            >
              {saving ? <Loader size={14} className="animate-spin" /> : <Save size={14} />}
            </button>
            <button
              onClick={discardChanges}
              className="btn-secondary text-xs p-2"
              title="Discard changes"
            >
              <Undo2 size={14} />
            </button>
          </>
        )}
        {editable && (
        <button onClick={handleDelete} className="btn-danger" title="Delete">
          <Trash2 size={14} />
        </button>
        )}
      </div>
      <div className="grid grid-cols-1 @4xl:grid-cols-3 gap-6">
        <div className="@4xl:col-span-2 space-y-6">
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
              // Read mode: render the rich text with entity ids linked and
              // modal keywords highlighted.
              <AutoLinkHtml
                renderPlain={withModals}
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
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
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
                    className="bg-transparent flex-1 text-[11px] font-mono outline-none min-w-[110px] placeholder:text-muted-foreground/50"
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
          {/* The design side of the house: which components satisfy this
              requirement — allocation, in ISO 29148 terms. Used to be
              read-only here with a comment pointing at the Components page,
              plus a *second*, disconnected free-text "Allocated To" field
              above that wrote to req.allocated_to directly. Both are now one
              editable control, backed by the same /allocation endpoint the
              Allocation Matrix page uses, so this can no longer disagree with
              the matrix or go stale. */}
          {(satisfiedBy.length > 0 || editable) && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-1">Allocated To</h2>
              <LinkEditor
                hint="Components that satisfy this requirement" kind="component"
                linked={satisfiedBy.map((c) => c.id)}
                options={allComponents}
                editable={editable}
                onAdd={(id) => allocateComponent(id, true)}
                onRemove={(id) => allocateComponent(id, false)}
                nameOf={(id) => satisfiedBy.find((c) => c.id === id)?.name
                  ?? allComponents.find((c) => c.id === id)?.name ?? ''}
              />
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
          {/* Everything that points at this requirement, computed server-side
              from the link registry rather than assembled from a handful of
              per-entity fetches. Read-only: each link is owned by the record
              holding it, so editing lives on that record's page. */}
          {backlinks && backlinks.total > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.225 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-1">Referenced By</h2>
              <p className="text-[11px] text-muted-foreground mb-3">
                {backlinks.total} record{backlinks.total === 1 ? '' : 's'} depend on this requirement.
                Deleting it will ask before breaking them.
              </p>
              <div className="space-y-2.5">
                {backlinks.groups.map((g) => (
                  <div key={g.collection}>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                      {g.label}{g.items.length === 1 ? '' : 's'}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {g.items.map((it) => (
                        <span key={`${g.collection}-${it.id}`}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted text-xs"
                          title={it.label}>
                          {BACKLINK_KINDS[g.collection] ? (
                            <EntityLink kind={BACKLINK_KINDS[g.collection]} id={it.id}
                              name={it.name || undefined} className="hover:text-primary max-w-[180px]" />
                          ) : (
                            <span className="text-foreground truncate max-w-[180px]">
                              <span className="font-mono">{it.id}</span>{it.name ? ` — ${it.name}` : ''}
                            </span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
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
          {(affectingCrs.length > 0 || linkedRisks.length > 0 || mitigatingRisks.length > 0 || editable) && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3">Change Requests &amp; Risks</h2>
              <div className="space-y-1.5">
                {affectingCrs.map((c) => (
                  <div key={c.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                    <EntityLink kind="change" id={c.id} name={c.title} className="flex-1 min-w-0 text-foreground hover:text-primary" />
                    <span className="badge bg-muted text-muted-foreground shrink-0">{c.status}</span>
                  </div>
                ))}
              </div>
              {/* Risks are editable from here as well as from the Risks page.
                  The link lives on the risk (risk.linked_requirements), so both
                  views used to render it read-only and it could only be created
                  by hand-editing YAML. Writing from this side updates the risk,
                  which is the same record the Risks page edits. */}
              <div className={affectingCrs.length > 0 ? 'mt-3 pt-3 border-t' : ''}>
                <LinkEditor
                  label="Threatened by" hint="Risks that threaten this requirement" kind="risk"
                  linked={linkedRisks.map((r) => r.id)}
                  options={allRisks}
                  editable={editable}
                  onAdd={(id) => setRiskLink(id, true)}
                  onRemove={(id) => setRiskLink(id, false)}
                  nameOf={(id) => allRisks.find((r) => r.id === id)?.name ?? ''}
                />
                <div className={linkedRisks.length > 0 ? 'mt-3 pt-3 border-t' : ''}>
                  <LinkEditor
                    label="Mitigates" hint="Risks this requirement reduces" kind="risk"
                    linked={mitigatingRisks.map((r) => r.id)}
                    options={allRisks}
                    editable={editable}
                    onAdd={(id) => setMitigatingRiskLink(id, true)}
                    onRemove={(id) => setMitigatingRiskLink(id, false)}
                    nameOf={(id) => allRisks.find((r) => r.id === id)?.name ?? ''}
                  />
                </div>
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
          {(comments.length > 0 || canPropose) && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center justify-between">
                <span>Comments ({comments.length})</span>
                <AddCommentForm projectId={projectId!} reqId={reqId!} onAdded={() => api.listComments(projectId!, reqId).then(setComments).catch(() => {})} disabled={!canPropose} />
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
                <select className="select" value={req.type} onChange={(e) => save({ type: e.target.value })} disabled={!editable} style={{ color: reqTypeColor(req.type) }}>
                  {typeOptionsFor(req.type).map((t) => (
                    <option key={t} value={t} style={{ color: reqTypeColor(t) }}>
                      {REQUIREMENT_TYPE_META[t]
                        ? REQUIREMENT_TYPE_META[t].label
                        : `${formatReqType(t)} (unrecognised)`}
                    </option>
                  ))}
                </select>
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
        <select className="select" value={req.status} onChange={(e) => save({ status: e.target.value })} disabled={!editable} style={{ color: statusColors[req.status]?.text }}>
          {statusOptions.map((s) => (<option key={s} value={s} style={{ color: statusColors[s]?.text }}>{s}</option>))}
        </select>
      </div>
              <div>
                <label className="label">Priority</label>
                <select className="select" value={req.priority} onChange={(e) => save({ priority: e.target.value })} disabled={!editable} style={{ color: priorityColorMap[req.priority] }}>
                  {priorityOptions.map((p) => (<option key={p} value={p} style={{ color: priorityColorMap[p] }}>{p}</option>))}
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
                {/* Checkboxes over the vocabulary the backend actually
                    satisfies, fetched from /coverage-needs. Free text let a
                    project declare obligations nothing could ever discharge —
                    the demo shipped `design` and `verification_case`, which the
                    old model compared against a child requirement's *type*, and
                    neither is a valid RequirementType. Any value already stored
                    that is not in the vocabulary is still listed, so an
                    existing project can see and clear it rather than having it
                    silently vanish on the next save. */}
                <div className="space-y-1 mt-1">
                  {[...coverageNeedOptions.map((o) => o.value),
                    ...(req.needs || []).filter((n) => !coverageNeedOptions.some((o) => o.value === n)),
                  ].map((value) => {
                    const known = coverageNeedOptions.find((o) => o.value === value);
                    const checked = (req.needs || []).includes(value);
                    return (
                      <label key={value} className="flex items-start gap-2 text-xs cursor-pointer group">
                        <input
                          type="checkbox"
                          className="w-3.5 h-3.5 mt-0.5 rounded border-muted-foreground/30 shrink-0"
                          checked={checked}
                          disabled={!editable}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...(req.needs || []), value]
                              : (req.needs || []).filter((n) => n !== value);
                            save({ needs: next });
                          }}
                        />
                        <span className="min-w-0">
                          <span className="font-mono text-[11px] text-foreground">{value}</span>
                          {known
                            ? <span className="text-[10px] text-muted-foreground block">{known.label}</span>
                            : <span className="text-[10px] text-amber-400 block">Not a recognised obligation — nothing can satisfy it</span>}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">Artifacts that must exist to cover this requirement</div>
              </div>
              <div>
                <label className="label flex items-center justify-between">
                  <span>Stakeholder Priorities</span>
                  {reqValue?.value != null && (
                    <span className="text-[10px] font-normal text-muted-foreground">
                      value <span className="font-mono text-foreground">{reqValue.value}</span>
                      {reqValue.rank != null && <> · #{reqValue.rank} of {reqValue.ranked_total}</>}
                    </span>
                  )}
                </label>
                {/* Was a textarea parsed as `name: score` lines. It reparsed on
                    every keystroke and rebuilt its own value from the result, so
                    a half-typed line ("safety" before the colon) failed to parse
                    and vanished under the cursor — the field genuinely could not
                    be typed into. One numeric input per project stakeholder
                    instead, which also makes the scores comparable across
                    requirements: they are keyed to a defined list rather than to
                    whatever each author happened to type. */}
                {projectStakeholders.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground">
                    No stakeholders defined.{' '}
                    <Link to={`/project/${projectId}/settings`} className="text-primary hover:underline">
                      Add them in project settings
                    </Link>{' '}
                    to score this requirement.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {projectStakeholders.map((s) => {
                      const score = req.priorities?.[s.name];
                      return (
                        <div key={s.name} className="flex items-center gap-2">
                          <span className="text-xs text-foreground flex-1 min-w-0 truncate" title={s.name}>{s.name}</span>
                          <span className="text-[10px] text-muted-foreground shrink-0 w-10 text-right">×{s.weight}</span>
                          <input
                            type="range" min={0} max={5} step={1}
                            className="w-16 h-7 shrink-0 cursor-pointer"
                            value={score != null && score > 5 ? 5 : (score ?? 0)}
                            onChange={(e) => {
                              const next = { ...(req.priorities || {}) };
                              const v = Number(e.target.value);
                              if (v === 0) delete next[s.name];
                              else next[s.name] = v;
                              save({ priorities: next });
                            }}
                            disabled={!editable}
                          />
                          <span className="text-[10px] text-muted-foreground w-5 text-right tabular-nums shrink-0">
                            {score != null && score > 5 ? 5 : (score ?? '–')}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {/* Scores left over from a stakeholder that has since been
                    renamed or removed. Shown so they can be cleared, rather
                    than sitting in the data invisibly and unused. */}
                {(reqValue?.unknown_stakeholders?.length ?? 0) > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {reqValue!.unknown_stakeholders.map((name) => (
                      <div key={name} className="flex items-center gap-2 text-[10px] text-amber-400">
                        <span className="flex-1 min-w-0 truncate">{name}: {req.priorities?.[name]} — not a project stakeholder</span>
                        {editable && (
                          <button
                            className="hover:text-destructive shrink-0"
                            title="Remove this score"
                            onClick={() => {
                              const next = { ...(req.priorities || {}) };
                              delete next[name];
                              save({ priorities: next });
                            }}
                          ><X size={11} /></button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <div className="text-[10px] text-muted-foreground mt-1">
                  0–5 per stakeholder. Value is the weighted mean of those scored
                  {reqValue && reqValue.stakeholder_count > 0 &&
                    <> ({reqValue.scored_count} of {reqValue.stakeholder_count} scored)</>}.
                </div>
              </div>
              <div>
                <label className="label">Verification</label>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-foreground">
                    {req.verification_methods.length > 1
                      ? req.verification_methods.join(', ')
                      : req.verification_methods.length === 1
                        ? req.verification_method
                        : <span title="No verification case covers this requirement">—</span>
                    }
                  </span>
                  <span
                    className="badge text-xs"
                    style={{ color: verifStatusColorMap[req.verification_status || 'pending'] }}
                  >
                    {(req.verification_status || 'pending').replace(/_/g, ' ')}
                  </span>
                </div>
                {req.verification_cases.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {req.verification_cases.map((vc) => (
                      <span key={vc} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted text-xs text-foreground">
                        <EntityLink
                          kind="verification"
                          id={vc}
                          name={allVcs.find((v) => v.id === vc)?.name}
                          className="hover:text-primary"
                        />
                      </span>
                    ))}
                  </div>
                )}
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
                {/* A single-line <input> for the "why" behind a requirement was
                    too small to write in and lost every bit of structure. Same
                    editor as Description, so [[SYST0001]] entity links and
                    formatting work here too — and rationale already round-trips
                    to SysML v2 as doc text, so structure is worth keeping. */}
                {editable ? (
                  <RichTextEditor
                    content={req.rationale || ''}
                    onChange={(html) => { setReq({ ...req, rationale: html }); }}
                    onBlur={(html) => save({ rationale: html })}
                    disabled={false}
                  />
                ) : (
                  <AutoLinkHtml
                    html={req.rationale || ''}
                    kinds={entityKinds}
                    className="prose prose-sm dark:prose-invert max-w-none border rounded-lg p-3 min-h-[80px] opacity-90"
                  />
                )}
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
              {/* "Allocated To" used to be a free-text input here, writing straight
                  to req.allocated_to — a field the allocation matrix already
                  derives and overwrites from component.satisfies
                  (extra_routes.py: set_allocation), so anything typed here
                  disagreed with the matrix the moment anyone touched it there,
                  and never reached the SysML export at all. The "Satisfied By"
                  card below is the same relationship, backed by the same
                  endpoint the matrix uses — editable there now instead of a
                  second, disconnected copy of the same idea. */}
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
    } catch (e: any) {
      console.warn('Comment submit failed: %s', e?.message || e);
    }
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
