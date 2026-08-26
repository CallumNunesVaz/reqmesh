import { useEffect, useMemo, useState } from 'react';
import { usePersistedState } from '../hooks/usePersistedState';
import { useNavigate, useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, GitPullRequest, Square, CheckSquare, X, Search, Play, Edit3, Ban } from 'lucide-react';
import { api, type ChangeRequest, type Component, type CRRedline, type Project, type Requirement, CR_URGENCIES } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { useConfirm } from '../components/ConfirmDialog';
import { LinkEditor } from '../components/LinkEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useToasts } from '../components/Toast';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import { useSelectedReq, useContextPane } from '../components/Layout';
import LoadingSplash from '../components/LoadingSplash';
import EmptyState from '../components/EmptyState';

const statusBadges: Record<string, string> = {
  submitted: 'border-cs-blue/30 bg-cs-blue/10 text-cs-blue',
  in_review: 'border-cs-amber/30 bg-cs-amber/10 text-cs-amber',
  approved: 'border-cs-green/30 bg-cs-green/10 text-cs-green',
  rejected: 'border-cs-red/30 bg-cs-red/10 text-cs-red',
  implemented: 'border-cs-purple/30 bg-cs-purple/10 text-cs-purple',
  closed: 'border-cs-grey/30 bg-cs-grey/10 text-cs-grey',
};

const urgencyBadges: Record<string, string> = {
  low: 'border-cs-grey/30 bg-cs-grey/10 text-cs-grey',
  normal: 'border-cs-blue/30 bg-cs-blue/10 text-cs-blue',
  high: 'border-cs-amber/30 bg-cs-amber/10 text-cs-amber',
  emergency: 'border-cs-red/30 bg-cs-red/10 text-cs-red',
};

interface RequirementNamingRule {
  separator?: string;
  suffix_type?: string;
}

// The same grammar as `core.ids.safe_id`, so an id the authoring form refuses
// is one `safe_id` would refuse too.
const SAFE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._ -]*$/;

/** Reason a proposed new-requirement id cannot be created, or null when valid.
 *  Mirrors `safe_id` + `services.rename.matches_scheme` so a proposed id is
 *  refused here exactly the way execute and rename would refuse it later. */
function proposedIdError(id: string, naming: RequirementNamingRule | undefined, existing: Set<string>): string | null {
  const trimmed = id.trim();
  if (!trimmed) return "'id' is empty";
  if (trimmed.includes('..') || !SAFE_ID_RE.test(trimmed)) {
    return `'${trimmed}' is not a valid requirement id`;
  }
  if (existing.has(trimmed)) {
    return `'${trimmed}' already exists`;
  }
  const separator = naming?.separator ?? '';
  const suffixType = naming?.suffix_type ?? 'numeric';
  if (separator && !trimmed.includes(separator)) {
    return `'${trimmed}' is missing the '${separator}' between its prefix and number`;
  }
  const tail = separator ? trimmed.split(separator).pop() ?? trimmed : trimmed;
  if (suffixType === 'numeric' && !/\d$/.test(tail)) {
    return `'${trimmed}' must end in a number`;
  }
  return null;
}

/** Render a single diff field: before strikethrough, after marked. */
function DiffField({ field, before, after }: { field: string; before: unknown; after: unknown }) {
  const beforeStr = before === null || before === undefined ? '\u2014' : String(before);
  const afterStr = String(after ?? '');
  return (
    <div className="text-xs py-0.5">
      <span className="font-mono text-muted-foreground">{field}: </span>
      <span className="line-through text-cs-red">{beforeStr}</span>
      <span className="mx-1 text-muted-foreground">→</span>
      <span className="text-cs-green">{afterStr}</span>
    </div>
  );
}

export default function ChangeRequestsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [crs, setCrs] = useState<ChangeRequest[]>([]);
  const [redlines, setRedlines] = useState<Record<string, CRRedline>>({});
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ id: '', title: '', description: '', rationale: '', urgency: 'normal' });
  const [idExample, setIdExample] = useState('');
  const [editingCrId, setEditingCrId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: '', description: '', rationale: '', urgency: 'normal' });
  const [loading, setLoading] = useState(true);
  const editable = useAuthStore((s) => s.canPropose());
  // Bulk operations are maintainer-tier (backend require_maintain), unlike
  // individual create/edit/delete which are propose-tier.
  const canBulk = useAuthStore((s) => s.canEdit());
  // `canEdit` rather than a role check of its own: it is maintainer-or-admin
  // *and* edit mode, and edit mode is the guard against changing data you only
  // meant to read. A local role-only predicate put Execute and Reject on screen
  // while the header said VIEWING — the same defect the store's own comment
  // records fixing for canPropose.
  const canMaintain = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const [components, setComponents] = useState<Component[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  // Proposed new requirements on the in-progress CR, plus any authoring-time
  // id error, held separately so a bad id never reaches the API.
  const [proposals, setProposals] = useState<{ id: string; name: string; description: string }[]>([{ id: '', name: '', description: '' }]);
  const [proposalError, setProposalError] = useState('');
  const dataVersion = useStore((s) => s.dataVersion);
  const entityKinds = useEntityKinds(projectId);
  const showConfirm = useConfirm();
  const navigate = useNavigate();
  const { selectReq } = useSelectedReq();
  const { openContext } = useContextPane();
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  // Persisted per project — see RequirementsPage/ComponentsPage for why.
  const pk = (field: string) => (projectId ? `rt-crs-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterStatus, setFilterStatus] = usePersistedState(pk('filter-status'), '');

  const load = () => {
    if (!projectId) return;
    api.listChangeRequests(projectId).then(setCrs).catch(console.error)
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId, dataVersion]);
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    api.listComponents(projectId)
      .then((v) => { if (alive) setComponents(v); })
      .catch(() => { if (alive) setComponents([]); });
    return () => { alive = false; };
  }, [projectId, dataVersion]);

  // The naming scheme (for id validation) and the existing ids (to refuse a
  // collision) both come from the project; fetched together because the form
  // needs both before a proposal can be judged.
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    Promise.all([
      api.getProject(projectId),
      api.listRequirements(projectId),
    ])
      .then(([p, reqs]) => {
        if (!alive) return;
        setProject(p);
        setRequirements(reqs);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [projectId, dataVersion]);

  // Fetch redlines for each CR after the list loads.
  useEffect(() => {
    if (!projectId || crs.length === 0) return;
    const fetched: Record<string, CRRedline> = {};
    let alive = true;
    Promise.all(
      crs.map((cr) =>
        api.getCRRedline(projectId, cr.id)
          .then((rl) => { if (alive) fetched[cr.id] = rl; })
          .catch(() => {})
      )
    ).then(() => { if (alive) setRedlines(fetched); });
    return () => { alive = false; };
  }, [projectId, crs]);

  const filteredCRs = useMemo(() => {
    if (!search && !filterStatus) return crs;
    const q = search.toLowerCase();
    return crs.filter((cr) => {
      if (filterStatus && cr.status !== filterStatus) return false;
      if (q) {
        const hay = `${cr.id} ${cr.title || ''} ${cr.description || ''} ${cr.rationale || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [crs, search, filterStatus]);
  const filtering = !!(search || filterStatus);

  // Arriving from a link elsewhere (?focus=CR-001).
  const focusId = useFocusedEntity(crs.length > 0);

  const openCreate = () => {
    setShowCreate(true);
    if (!projectId) return;
    api.getNextId(projectId, 'change_requests')
      .then((r) => {
        setForm((f) => (f.id ? f : { ...f, id: r.next_id }));
        setIdExample(r.next_id);
      })
      .catch(() => {});
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !form.id.trim()) return;
    const naming = (project?.naming as Record<string, RequirementNamingRule> | undefined)?.requirements;
    const existing = new Set(requirements.map((r) => r.id));
    const filled = proposals.filter((p) => p.id.trim());
    for (const p of filled) {
      const reason = proposedIdError(p.id, naming, existing);
      if (reason) {
        setProposalError(`Proposed requirement ${reason}`);
        return;
      }
    }
    const changes: Record<string, Record<string, unknown>> = {};
    const creates: string[] = [];
    for (const p of filled) {
      changes[p.id.trim()] = { name: p.name, description: p.description };
      creates.push(p.id.trim());
    }
    try {
      await api.createChangeRequest(projectId, {
        id: form.id.trim(),
        title: form.title,
        description: form.description,
        rationale: form.rationale,
        urgency: form.urgency,
        affected_requirements: creates,
        changes,
        creates,
      });
      setShowCreate(false);
      setForm({ id: '', title: '', description: '', rationale: '', urgency: 'normal' });
      setProposals([{ id: '', name: '', description: '' }]);
      setProposalError('');
      load();
    } catch (err: any) { setError(err.message || 'Failed to create'); }
  };

  const addProposal = () => setProposals((prev) => [...prev, { id: '', name: '', description: '' }]);
  const removeProposal = (index: number) => setProposals((prev) => prev.filter((_, i) => i !== index));
  const updateProposal = (index: number, field: 'id' | 'name' | 'description', value: string) => {
    setProposals((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
    setProposalError('');
  };

  const handleDelete = async (crId: string) => {
    const ok = await showConfirm('Delete this change request?', 'Delete Change Request', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      await api.deleteChangeRequest(projectId!, crId);
      setCrs((prev) => prev.filter((c) => c.id !== crId));
    } catch (err: any) { setError(err.message || 'Failed to delete'); }
  };

  const handleExecute = async (crId: string, rl: CRRedline | undefined) => {
    const blocked = rl?.blocked;
    // Creating a requirement is not the same act as editing one, so the gate
    // says so: the reviewer is told exactly which ids this brings into
    // existence before it happens, not just that changes will be applied.
    const newIds = (rl?.targets ?? []).filter((t) => t.creates).map((t) => t.id);
    const newClause = newIds.length
      ? ` This creates ${newIds.length} new requirement${newIds.length === 1 ? '' : 's'}: ${newIds.join(', ')}.`
      : '';
    const msg = blocked
      ? `This change request is stale — ${rl?.targets.filter(t => t.stale).map(t => t.id).join(', ')} changed since it was raised. Execute anyway?`
      : `Apply all proposed changes?${newClause}`;
    const ok = await showConfirm(msg, newIds.length ? 'Create & apply' : 'Execute');
    if (!ok) return;
    try {
      const result = await api.executeChangeRequest(projectId!, crId);
      load();
      // A requirement that did not exist a moment ago is worth landing on, so
      // approving the CR hands you the same view as creating it by hand:
      // reload the graph so the new node exists, select it (the canvas expands
      // its ancestors and frames it), reveal the inspector in case it was
      // collapsed, and open the requirement itself.
      const created = result.created ?? [];
      const focusId = created[0];
      if (focusId) {
        bumpGraphVersion();
        selectReq(focusId);
        openContext();
        addToast('success', created.length === 1 ? `Created ${focusId}` : `Created ${created.join(', ')}`);
        navigate(`/project/${projectId}/requirements/${focusId}`);
      }
    } catch (err: any) { setError(err.message || 'Failed to execute'); }
  };

  const handleReject = async (crId: string) => {
    const ok = await showConfirm('Reject this change request?', 'Reject');
    if (!ok) return;
    try {
      await api.rejectChangeRequest(projectId!, crId);
      load();
    } catch (err: any) { setError(err.message || 'Failed to reject'); }
  };

  const startEditing = (cr: ChangeRequest) => {
    setEditingCrId(cr.id);
    setEditForm({
      title: cr.title || '',
      description: cr.description || '',
      rationale: cr.rationale || '',
      urgency: cr.urgency || 'normal',
    });
  };

  const cancelEditing = () => {
    setEditingCrId(null);
  };

  const setAffectedComponents = async (crId: string, linked: string[]) => {
    if (!projectId) return;
    setCrs((prev) => prev.map((c) => (c.id === crId ? { ...c, affected_components: linked } : c)));
    try {
      await api.updateChangeRequest(projectId, crId, { affected_components: linked });
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const handleModifySave = async (crId: string) => {
    if (!projectId) return;
    try {
      await api.updateChangeRequest(projectId, crId, {
        title: editForm.title,
        description: editForm.description,
        rationale: editForm.rationale,
        urgency: editForm.urgency,
      });
      setEditingCrId(null);
      load();
    } catch (err: any) { setError(err.message || 'Failed to modify'); }
  };

  // `filteredCRs` is the list as displayed, which is the only ordering a
  // Shift range may span.
  const { selectedIds, select: toggleCR, setSelectedIds } =
    useRangeSelection(useMemo(() => filteredCRs.map((c) => c.id), [filteredCRs]));
  const clearCRSelection = () => setSelectedIds(new Set());
  const selectAllCRs = () => setSelectedIds(new Set(filteredCRs.map(c => c.id)));

  const { runBulkDelete, runBulkUpdate } = useBulkActions({
    clearSelection: clearCRSelection,
    reload: load,
  });

  const handleBulkCRStatus = async (status: string) => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const before = Object.fromEntries(
      crs.filter((c) => selectedIds.has(c.id)).map((c) => [c.id, { status: c.status }]),
    );
    await runBulkUpdate({
      label: `${status} on ${ids.length} change requests`,
      noun: 'change request',
      ids,
      before,
      updates: { status },
      apply: (updateIds, updatePayload) => api.bulkUpdateChangeRequests(projectId, updateIds, updatePayload),
      applyOne: (id, updatePayload) => api.updateChangeRequest(projectId, id, updatePayload),
    });
  };

  const handleBulkCRDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const saved = crs.filter((c) => selectedIds.has(c.id)).map((c) => ({ ...c }));
    await runBulkDelete({
      noun: 'change request',
      ids,
      saved,
      idOf: (c) => c.id,
      remove: (idsToRemove) => api.bulkDeleteChangeRequests(projectId, idsToRemove),
      recreate: (item) => api.createChangeRequest(projectId, item),
    });
  };

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && crs.length === 0 && <LoadingSplash label="Loading change requests…" />}
      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Change Requests</h1>
          <p className="text-sm text-muted-foreground mt-1">{filtering ? `${filteredCRs.length} of ${crs.length} change requests` : `${crs.length} change requests`}</p>
        </div>
        {editable && (
        <button onClick={openCreate} className="btn-primary">
          <Plus size={16} /> New Change Request
        </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="input pl-9 pr-14 h-9"
              placeholder="Search change requests…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search ? (
              <button className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            ) : (
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded border bg-muted text-[10px] font-mono text-muted-foreground pointer-events-none">/</kbd>
            )}
          </div>
          <select className="select w-36 h-9 text-xs" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="submitted">Submitted</option>
            <option value="in_review">In Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="implemented">Implemented</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      <AnimatePresence>
        {showCreate && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate} className="card p-4 mb-4 overflow-hidden">
            <div className="flex items-end gap-3">
              <div className="w-32"><label className="label">ID <input className="input font-mono" placeholder="CR-001" value={form.id} onChange={e => setForm({...form, id: e.target.value})} /></label>{idExample && <span className="text-[10px] text-muted-foreground">e.g. {idExample}</span>}</div>
              <div className="flex-1"><label className="label">Title <input className="input" placeholder="Change request title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} /></label></div>
              <div className="w-28">
                <label className="label">Urgency <select className="select" value={form.urgency} onChange={e => setForm({...form, urgency: e.target.value})}>
                  {CR_URGENCIES.map((u) => <option key={u} value={u}>{u}</option>)}
                </select></label>
              </div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
            <div className="mt-2">
              <label className="label">Description <input className="input" placeholder="What the change is" value={form.description} onChange={e => setForm({...form, description: e.target.value})} /></label>
            </div>
            <div className="mt-2">
              <label className="label">Rationale <input className="input" placeholder="Why the change is needed" value={form.rationale} onChange={e => setForm({...form, rationale: e.target.value})} /></label>
            </div>
            <div className="mt-3 pt-3 border-t border-border">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Proposed new requirements</div>
                <button type="button" onClick={addProposal} className="btn-secondary text-xs py-1 px-2"><Plus size={13} /> Add</button>
              </div>
              {proposals.map((p, i) => (
                <div key={i} className="flex items-end gap-2 mb-2">
                  <div className="w-44"><label className="label">ID <input className="input font-mono" placeholder="REQ0001" value={p.id} onChange={e => updateProposal(i, 'id', e.target.value)} /></label></div>
                  <div className="flex-1"><label className="label">Name <input className="input" placeholder="Proposed requirement name" value={p.name} onChange={e => updateProposal(i, 'name', e.target.value)} /></label></div>
                  <div className="flex-1"><label className="label">Description <input className="input" placeholder="What the requirement says" value={p.description} onChange={e => updateProposal(i, 'description', e.target.value)} /></label></div>
                  {proposals.length > 1 && (
                    <button type="button" onClick={() => removeProposal(i)} className="btn-secondary shrink-0" title="Remove proposal"><X size={14} /></button>
                  )}
                </div>
              ))}
              {proposalError && (
                <div className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{proposalError}</div>
              )}
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {filteredCRs.length === 0 ? (
        <EmptyState
          icon={GitPullRequest}
          title={filtering ? 'No change requests match your filters.' : 'No change requests yet'}
          hint={filtering ? undefined : 'Propose and track changes to requirements.'}
          action={!filtering && editable ? { label: 'New Change Request', onClick: openCreate } : undefined}
        >
          {filtering && (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterStatus(''); }}>Clear filters</button>
          )}
        </EmptyState>
      ) : (
      <div className="space-y-3">
        {filteredCRs.map((cr, i) => {
          const rl = redlines[cr.id];
          return (
          <motion.div key={cr.id} id={`entity-${cr.id}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
            className={`card p-4 hover:shadow-md transition-shadow group ${focusId === cr.id ? 'ring-2 ring-primary/50' : ''}`}>
            <div className="flex items-center gap-3">
              {canBulk && (
                <span className="shrink-0">
                  {selectedIds.has(cr.id) ? (
                    <CheckSquare size={14} className="text-primary cursor-pointer" onClick={(e) => toggleCR(cr.id, e)} />
                  ) : (
                    <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={(e) => toggleCR(cr.id, e)} />
                  )}
                </span>
              )}
              <div className="w-9 h-9 bg-cs-purple/10 text-cs-purple rounded-lg flex items-center justify-center"><GitPullRequest size={18} /></div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{cr.id}</span>
                  <h3 className="font-medium text-card-foreground">{cr.title || 'Untitled'}</h3>
                  <span className={`badge border ${statusBadges[cr.status] || ''}`}>{cr.status}</span>
                  <span className={`badge border ${urgencyBadges[cr.urgency] || ''}`}>{cr.urgency}</span>
                  <CopyLinkButton kind="change" id={cr.id} className="opacity-0 group-hover:opacity-100" />
                </div>
                {cr.description && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1"><AutoLinkText text={cr.description} kinds={entityKinds} /></p>}
                <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                  {cr.submitted_by && <span>by <span className="font-medium text-foreground">{cr.submitted_by}</span></span>}
                  {cr.rationale && <span className="italic">— {cr.rationale}</span>}
                </div>
                {cr.affected_requirements.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Affects</span>
                    {cr.affected_requirements.map((rid) => (
                      <span key={rid} className="inline-flex items-center px-1.5 py-0.5 rounded bg-muted text-xs">
                        <EntityLink kind="requirement" id={rid} className="hover:text-primary" />
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-2">
                  <LinkEditor
                    label="Affects (components)" hint="" kind="component"
                    linked={(cr.affected_components || [])}
                    options={components}
                    editable={editable}
                    onAdd={(id) => setAffectedComponents(cr.id, [...(cr.affected_components || []), id])}
                    onRemove={(id) => setAffectedComponents(cr.id, (cr.affected_components || []).filter((x) => x !== id))}
                    nameOf={(id) => components.find((c) => c.id === id)?.name ?? ''}
                  />
                </div>
                {/* Redline: before/after per field */}
                {rl && rl.targets.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border text-xs">
                    {rl.targets.map((t) => {
                      const diffKeys = Object.keys(t.diffs);
                      if (t.stale && diffKeys.length === 0 && !t.creates && rl.targets.length === 1) {
                        return <span key={t.id} className="text-cs-amber">Target {t.id} no longer exists</span>;
                      }
                      return (
                        <div key={t.id} className="mb-1">
                          <span className="font-mono text-muted-foreground">
                            <EntityLink kind="requirement" id={t.id} name={t.name} className="hover:text-primary" />
                          </span>
                          {t.creates && <span className="ml-1 badge border border-cs-blue/30 bg-cs-blue/10 text-cs-blue">New requirement</span>}
                          {t.stale && <span className="ml-1 text-cs-amber italic">(stale)</span>}
                          {diffKeys.length > 0 && (
                            <div className="ml-2 mt-0.5 space-y-0">
                              {diffKeys.map((field) => (
                                <DiffField key={field} field={field} before={t.diffs[field].before} after={t.diffs[field].after} />
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-border">
                  <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Comments</h4>
                  <CommentThread entityKind="change_requests" entityId={cr.id} />
                </div>
                <div className="mt-3 pt-3 border-t border-border">
                  <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Change History</h4>
                  <HistoryPanel itemId={cr.id} />
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {editingCrId === cr.id ? (
                  <div className="flex flex-col gap-1 items-end">
                    <input className="input text-xs w-36" placeholder="Title" value={editForm.title} onChange={e => setEditForm({...editForm, title: e.target.value})} />
                    <select className="select text-xs w-36" value={editForm.urgency} onChange={e => setEditForm({...editForm, urgency: e.target.value})}>
                      {CR_URGENCIES.map((u) => <option key={u} value={u}>{u}</option>)}
                    </select>
                    <div className="flex gap-1">
                      <button onClick={() => handleModifySave(cr.id)} className="btn-primary text-xs py-0.5 px-2">Save</button>
                      <button onClick={cancelEditing} className="btn-secondary text-xs py-0.5 px-2">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <>
                    {canMaintain && (
                      <button
                        onClick={() => handleExecute(cr.id, rl)}
                        className="p-1.5 rounded-md hover:bg-cs-green/10 text-muted-foreground hover:text-cs-green opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                        title="Execute"
                      >
                        <Play size={14} />
                      </button>
                    )}
                    {editable && (
                      <button
                        onClick={() => startEditing(cr)}
                        className="p-1.5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                        title="Edit"
                      >
                        <Edit3 size={14} />
                      </button>
                    )}
                    {canMaintain && (
                      <button
                        onClick={() => handleReject(cr.id)}
                        className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                        title="Reject"
                      >
                        <Ban size={14} />
                      </button>
                    )}
                    {editable && (
                      <button onClick={() => handleDelete(cr.id)} className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]" title="Delete">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </motion.div>
        )})}
      </div>
      )}
      {selectedIds.size > 0 && canBulk && (
        <BulkActionBar
          count={selectedIds.size}
          onSelectAll={selectAllCRs}
          onClear={clearCRSelection}
        >
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkCRStatus(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set status...</option>
            <option value="open">Open</option>
            <option value="in_review">In Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <button onClick={handleBulkCRDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
  );
}
