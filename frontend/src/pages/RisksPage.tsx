import { useEffect, useMemo, useState, useId } from 'react';
import { usePersistedState } from '../hooks/usePersistedState';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Edit3, Square, CheckSquare, X, Search, AlertTriangle } from 'lucide-react';
import { api, RISK_STATUSES, type Risk, type Requirement, type Component, type RiskMatrix } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { CopyLinkButton } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkHtml } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { LinkEditor } from '../components/LinkEditor';
import { deleteWithReferenceCheck } from '../lib/forceDelete';
import RichTextEditor from '../components/RichTextEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useToasts } from '../components/Toast';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useConfirm } from '../components/ConfirmDialog';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';

const formatLevel = (s: string) => s.replace(/_/g, ' ');

export default function RisksPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ id: '', title: '', failure_mode: '', effect: '', cause: '', severity: '', likelihood: '' });
  const [idExample, setIdExample] = useState('');
  const failureModeId = useId();
  const effectId = useId();
  const causeId = useId();
  const editable = useAuthStore((s) => s.canPropose());
  // Bulk operations are maintainer-tier (backend require_maintain), unlike
  // individual create/edit/delete which are propose-tier.
  const canBulk = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const dataVersion = useStore((s) => s.dataVersion);
  const entityKinds = useEntityKinds(projectId);
  // Persisted per project — see RequirementsPage/ComponentsPage for why.
  const pk = (field: string) => (projectId ? `rt-risks-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterStatus, setFilterStatus] = usePersistedState(pk('filter-status'), '');
  const [filterSeverity, setFilterSeverity] = usePersistedState(pk('filter-severity'), '');
  const [filterLikelihood, setFilterLikelihood] = usePersistedState(pk('filter-likelihood'), '');

  // Requirements are loaded so the "Threatens" links can be edited here, not
  // just displayed — previously this list and the requirement's own "Risks"
  // card both showed the relationship read-only, so it could only be created
  // by hand-editing YAML.
  const [requirements, setRequirements] = useState<Requirement[]>([]);

  // Components are loaded so the "Threatens (components)" and "Mitigated By
  // (components)" links can be edited here, mirroring the requirement editors.
  const [components, setComponents] = useState<Component[]>([]);

  // The project's risk matrix: supplies the severity/likelihood vocabularies the
  // dropdowns offer, so a project that renamed its axes does not get a form
  // offering levels its own matrix cannot rate.
  const [matrix, setMatrix] = useState<RiskMatrix | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => { if (!projectId) return; api.listRisks(projectId).then(setRisks).catch(console.error).finally(() => setLoading(false)); };
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    api.getRiskMatrix(projectId).then((m) => {
      if (!alive) return;
      setMatrix(m);
      // Seed the create form from the middle of each axis rather than a
      // hardcoded 'medium', which a renamed axis would not contain.
      setForm((f) => ({
        ...f,
        severity: f.severity || m.severities[Math.floor(m.severities.length / 2)] || '',
        likelihood: f.likelihood || m.likelihoods[Math.floor(m.likelihoods.length / 2)] || '',
      }));
    }).catch(() => {});
    return () => { alive = false; };
  }, [projectId, dataVersion]);
  useEffect(load, [projectId, dataVersion]);
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    api.listRequirements(projectId)
      .then((v) => { if (alive) setRequirements(v); })
      .catch(() => { if (alive) setRequirements([]); });
    return () => { alive = false; };
  }, [projectId, dataVersion]);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    api.listComponents(projectId)
      .then((v) => { if (alive) setComponents(v); })
      .catch(() => { if (alive) setComponents([]); });
    return () => { alive = false; };
  }, [projectId, dataVersion]);

  // Severity/likelihood are the rating's inputs, so the row is re-read from
  // the response rather than patched locally — the new rating is computed
  // server-side and guessing it here would let the badge drift.
  const setRiskLevel = async (riskId: string, patch: { severity?: string; likelihood?: string }) => {
    if (!projectId) return;
    const before = risks;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, ...patch } : r)));
    try {
      const updated = await api.updateRisk(projectId, riskId, patch);
      setRisks((prev) => prev.map((r) => (r.id === riskId ? updated : r)));
    } catch (err: any) {
      setRisks(before);
      setError(err.message || 'Failed to update risk');
    }
  };

  const setRiskRequirements = async (riskId: string, linked: string[]) => {
    if (!projectId) return;
    // Optimistic: the card re-renders from `risks`, and a round-trip through
    // load() would make each add/remove feel like a page refresh.
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, linked_requirements: linked } : r)));
    try {
      await api.updateRisk(projectId, riskId, { linked_requirements: linked });
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const setRiskMitigations = async (riskId: string, linked: string[]) => {
    if (!projectId) return;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, mitigating_requirements: linked } : r)));
    try {
      await api.updateRisk(projectId, riskId, { mitigating_requirements: linked });
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const setRiskLinkedComponents = async (riskId: string, linked: string[]) => {
    if (!projectId) return;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, linked_components: linked } : r)));
    try {
      await api.updateRisk(projectId, riskId, { linked_components: linked });
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const setRiskMitigatingComponents = async (riskId: string, linked: string[]) => {
    if (!projectId) return;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, mitigating_components: linked } : r)));
    try {
      await api.updateRisk(projectId, riskId, { mitigating_components: linked });
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const setRiskStatus = async (riskId: string, status: string) => {
    if (!projectId) return;
    const before = risks;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, status } : r)));
    try {
      await api.updateRisk(projectId, riskId, { status });
    } catch (err: any) {
      setRisks(before);
      setError(err.message || 'Failed to update risk');
    }
  };

  const setRiskDetection = async (riskId: string, detection: string) => {
    if (!projectId) return;
    const before = risks;
    setRisks((prev) => prev.map((r) => (r.id === riskId ? { ...r, detection } : r)));
    try {
      await api.updateRisk(projectId, riskId, { detection });
    } catch (err: any) {
      setRisks(before);
      setError(err.message || 'Failed to update risk');
    }
  };

  const filteredRisks = useMemo(() => {
    if (!search && !filterStatus && !filterSeverity && !filterLikelihood) return risks;
    const q = search.toLowerCase();
    return risks.filter((r) => {
      if (filterStatus && r.status !== filterStatus) return false;
      if (filterSeverity && r.severity !== filterSeverity) return false;
      if (filterLikelihood && (r.rating?.likelihood ?? r.probability) !== filterLikelihood) return false;
      if (q) {
        const hay = `${r.id} ${r.title || ''} ${r.failure_mode || ''} ${r.effect || ''} ${r.cause || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [risks, search, filterStatus, filterSeverity, filterLikelihood]);
  const filtering = !!(search || filterStatus || filterSeverity || filterLikelihood);

  // Arriving from a link elsewhere (?focus=RSK-001).
  const focusId = useFocusedEntity(risks.length > 0);

  const openCreate = () => {
    setForm({ id: '', title: '', failure_mode: '', effect: '', cause: '', severity: '', likelihood: '' });
    setEditingId(null);
    setShowCreate(true);
    if (!projectId) return;
    api.getNextId(projectId, 'risks')
      .then((r) => {
        setForm((f) => (f.id ? f : { ...f, id: r.next_id }));
        setIdExample(r.next_id);
      })
      .catch(() => {});
  };

  const openEdit = (r: Risk) => {
    setForm({
      id: r.id,
      title: r.title || '',
      failure_mode: r.failure_mode || '',
      effect: r.effect || '',
      cause: r.cause || '',
      severity: r.severity || '',
      likelihood: r.rating?.likelihood ?? r.likelihood ?? '',
    });
    setEditingId(r.id);
    setShowCreate(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !form.id.trim()) return;
    try {
      if (editingId) {
        await api.updateRisk(projectId, editingId, {
          title: form.title, failure_mode: form.failure_mode, effect: form.effect, cause: form.cause,
          severity: form.severity, likelihood: form.likelihood,
        });
        addToast('success', `Risk ${editingId} updated`);
      } else {
        await api.createRisk(projectId, form);
        addToast('success', `Risk ${form.id.trim()} created`);
      }
      setShowCreate(false); setForm({ id: '', title: '', failure_mode: '', effect: '', cause: '', severity: '', likelihood: '' });
      setEditingId(null);
      load();
    } catch (err: any) { setError(err.message || 'Failed to create'); }
  };

  const handleDelete = async (id: string) => {
    if (!projectId) return;
    const ok = await showConfirm('Delete this risk?', 'Delete Risk', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      const done = await deleteWithReferenceCheck(
        (force) => api.deleteRisk(projectId, id, force),
        (msg) => showConfirm(msg),
      );
      if (done) {
        setRisks(risks.filter(r => r.id !== id));
        addToast('success', `Risk ${id} deleted`);
      }
    } catch (err: any) { setError(err.message || 'Failed to delete'); }
  };

  // `filteredRisks` is the list as displayed, which is the only ordering a
  // Shift range may span.
  const { selectedIds, select: toggleRisk, setSelectedIds } =
    useRangeSelection(useMemo(() => filteredRisks.map((r) => r.id), [filteredRisks]));
  const clearRiskSelection = () => setSelectedIds(new Set());
  const selectAllRisks = () => setSelectedIds(new Set(filteredRisks.map(r => r.id)));

  const showConfirm = useConfirm();

  const { runBulkDelete, runBulkUpdate } = useBulkActions({
    clearSelection: clearRiskSelection,
    reload: load,
  });

  const handleBulkRiskStatus = async (status: string) => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const before = Object.fromEntries(
      risks.filter((r) => selectedIds.has(r.id)).map((r) => [r.id, { status: r.status }]),
    );
    await runBulkUpdate({
      label: `${status} on ${ids.length} risks`,
      noun: 'risk',
      ids,
      before,
      updates: { status },
      apply: (updateIds, updatePayload) => api.bulkUpdateRisks(projectId, updateIds, updatePayload),
      applyOne: (id, updatePayload) => api.updateRisk(projectId, id, updatePayload),
    });
  };

  const handleBulkRiskDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const saved = risks.filter((r) => selectedIds.has(r.id)).map((r) => ({ ...r }));
    await runBulkDelete({
      noun: 'risk',
      ids,
      saved,
      idOf: (r) => r.id,
      remove: (idsToRemove) => api.bulkDeleteRisks(projectId, idsToRemove),
      recreate: (item) => api.createRisk(projectId, item),
    });
  };

  return (
    <div className="relative max-w-6xl mx-auto p-8">
      {loading && risks.length === 0 && <LoadingSplash label="Loading risks…" />}
      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}
      <div className="flex items-center justify-between mb-6">
        <div><h1 className="text-2xl font-bold tracking-tight text-foreground">Risks</h1><p className="text-sm text-muted-foreground mt-1">{filtering ? `${filteredRisks.length} of ${risks.length} risks` : `${risks.length} risks`}</p></div>
        {editable && (
        <button onClick={openCreate} className="btn-primary"><Plus size={16} /> New Risk</button>
        )}
      </div>
      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="input pl-9 pr-14 h-9"
              placeholder="Search risks…"
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
          <select className="select w-32 h-9 text-xs" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="mitigated">Mitigated</option>
          </select>
          <select className="select w-32 h-9 text-xs" value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
            <option value="">All severities</option>
            {(matrix?.severities ?? []).map((sv) => <option key={sv} value={sv}>{formatLevel(sv)}</option>)}
          </select>
          <select className="select w-36 h-9 text-xs" value={filterLikelihood} onChange={(e) => setFilterLikelihood(e.target.value)}>
            <option value="">All likelihoods</option>
            {(matrix?.likelihoods ?? []).map((l) => <option key={l} value={l}>{formatLevel(l)}</option>)}
          </select>
        </div>
      </div>
      <AnimatePresence>
        {showCreate && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate} className="card p-4 mb-4 overflow-hidden">
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-32"><label className="label">ID <input className="input font-mono" placeholder="RSK-001" value={form.id} onChange={e => setForm({...form, id: e.target.value})} disabled={!!editingId} /></label>{!editingId && idExample && <span className="text-[10px] text-muted-foreground">e.g. {idExample}</span>}</div>
              <div className="flex-1 min-w-[12rem]"><label className="label">Title <input className="input" placeholder="Risk title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} /></label></div>
              <div className="w-36"><label className="label">Severity <select className="select" value={form.severity} onChange={e => setForm({...form, severity: e.target.value})}>
                {(matrix?.severities ?? []).map((sv) => <option key={sv} value={sv}>{formatLevel(sv)}</option>)}
              </select></label></div>
              <div className="w-40"><label className="label">Likelihood <select className="select" value={form.likelihood} onChange={e => setForm({...form, likelihood: e.target.value})}>
                {(matrix?.likelihoods ?? []).map((l) => <option key={l} value={l}>{formatLevel(l)}</option>)}
              </select></label></div>
              <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create'}</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
            <div className="mt-3 space-y-3">
              <div>
                <label className="label" htmlFor={failureModeId}>Failure Mode</label>
                <RichTextEditor
                  id={failureModeId}
                  content={form.failure_mode}
                  onChange={(html) => setForm({ ...form, failure_mode: html })}
                  onBlur={() => {}}
                  placeholder="What goes wrong…"
                />
              </div>
              <div>
                <label className="label" htmlFor={effectId}>Effect</label>
                <RichTextEditor
                  id={effectId}
                  content={form.effect}
                  onChange={(html) => setForm({ ...form, effect: html })}
                  onBlur={() => {}}
                  placeholder="What the failure does to the system…"
                />
              </div>
              <div>
                <label className="label" htmlFor={causeId}>Cause</label>
                <RichTextEditor
                  id={causeId}
                  content={form.cause}
                  onChange={(html) => setForm({ ...form, cause: html })}
                  onBlur={() => {}}
                  placeholder="Why the failure happens…"
                />
              </div>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
      {filteredRisks.length === 0 ? (
        <div className="card p-12 text-center">
          <AlertTriangle size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">
            {filtering ? 'No risks match your filters.' : 'No risks yet'}
          </p>
          {filtering ? (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterStatus(''); setFilterSeverity(''); setFilterLikelihood(''); }}>Clear filters</button>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">Identify and track project risks with severity and likelihood.</p>
          )}
        </div>
      ) : (
      <div className="space-y-3">
        {filteredRisks.map((r, i) => (
          <motion.div key={r.id} id={`entity-${r.id}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
            className={`card p-4 hover:shadow-md transition-shadow group ${focusId === r.id ? 'ring-2 ring-primary/50' : ''}`}>
            <div className="flex items-start gap-3">
              {canBulk && (
                <span className="shrink-0 mt-0.5">
                  {selectedIds.has(r.id) ? (
                    <CheckSquare size={14} className="text-primary cursor-pointer" onClick={(e) => toggleRisk(r.id, e)} />
                  ) : (
                    <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={(e) => toggleRisk(r.id, e)} />
                  )}
                </span>
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className="inline-flex items-center gap-1.5 shrink-0 text-[11px] font-medium"
                    style={{ color: r.rating?.color || 'hsl(var(--muted-foreground))' }}
                    title={r.rating?.band ? `severity ${formatLevel(r.rating.severity || '')} x likelihood ${formatLevel(r.rating.likelihood || '')}` : (r.rating?.unrated_reason || 'Not rated')}
                  >
                    <span className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: r.rating?.color || 'hsl(var(--muted-foreground))' }} />
                    {/* The band as text, not only as colour: it is the matrix's
                        output, and a reader who cannot distinguish the dot's
                        hue would otherwise have no way to read it. */}
                    {r.rating?.label || 'Unrated'}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{r.id}</span>
                  <h3 className="font-medium text-card-foreground">{r.title}</h3>
                  <CopyLinkButton kind="risk" id={r.id} className="opacity-0 group-hover:opacity-100" />
                </div>
                {/* The four risk controls: severity & likelihood are the rating
                    inputs; status & detection are stored metadata. The severity
                    select is tinted by the rating band so the band is visible
                    without a second badge. */}
                <div className="flex flex-wrap gap-2 mt-1.5">
                  <label className="flex flex-col gap-0.5 flex-1 min-w-[7rem]">
                    <span className="text-[9px] uppercase tracking-wide text-muted-foreground/70">severity</span>
                    {editable ? (
                    <select
                    className="select h-8 py-0 text-[11px] w-full"
                    style={r.rating?.color ? { borderColor: r.rating.color, backgroundColor: r.rating.color + '12' } : undefined}
                    value={r.severity || ''}
                    onChange={(e) => setRiskLevel(r.id, { severity: e.target.value })}
                    aria-label="Severity"
                    title="Severity"
                    >
                    {!(matrix?.severities ?? []).includes(r.severity) && (
                    <option value={r.severity}>{r.severity || '—'}</option>
                    )}
                    {(matrix?.severities ?? []).map((sv) => <option key={sv} value={sv}>{formatLevel(sv)}</option>)}
                    </select>
                    ) : (
                    <span className="badge bg-muted text-muted-foreground text-[11px] h-8 flex items-center px-2">{r.severity ? formatLevel(r.severity) : '—'}</span>
                    )}
                  </label>
                  <label className="flex flex-col gap-0.5 flex-1 min-w-[7rem]">
                    <span className="text-[9px] uppercase tracking-wide text-muted-foreground/70">likelihood</span>
                    {editable ? (
                    <select
                    className="select h-8 py-0 text-[11px] w-full"
                    value={r.rating?.likelihood ?? r.likelihood ?? ''}
                    onChange={(e) => setRiskLevel(r.id, { likelihood: e.target.value })}
                    aria-label="Likelihood"
                    title="Likelihood"
                    >
                    {!(matrix?.likelihoods ?? []).includes(r.rating?.likelihood ?? r.likelihood ?? '') && (
                    <option value={r.rating?.likelihood ?? r.likelihood ?? ''}>{r.rating?.likelihood ?? r.likelihood ?? '—'}</option>
                    )}
                    {(matrix?.likelihoods ?? []).map((l) => <option key={l} value={l}>{formatLevel(l)}</option>)}
                    </select>
                    ) : (
                    <span className="badge bg-muted text-muted-foreground text-[11px] h-8 flex items-center px-2">{r.rating?.likelihood ?? r.likelihood ? formatLevel(r.rating?.likelihood ?? r.likelihood ?? '') : '—'}</span>
                    )}
                  </label>
                  <label className="flex flex-col gap-0.5 flex-1 min-w-[7rem]">
                    <span className="text-[9px] uppercase tracking-wide text-muted-foreground/70">status</span>
                    {editable ? (
                    <select
                    className="select h-8 py-0 text-[11px] min-w-[5.5rem] flex-1"
                    value={r.status || ''}
                    onChange={(e) => setRiskStatus(r.id, e.target.value)}
                    aria-label="Status"
                    title="Status"
                    >
                    {!RISK_STATUSES.includes(r.status as any) && r.status && (
                    <option value={r.status}>{r.status}</option>
                    )}
                    {RISK_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    ) : (
                    <span className="badge bg-muted text-muted-foreground text-[11px] h-8 flex items-center px-2">{r.status || '—'}</span>
                    )}
                  </label>
                  <label className="flex flex-col gap-0.5 flex-1 min-w-[7rem]">
                    <span className="text-[9px] uppercase tracking-wide text-muted-foreground/70">detection</span>
                    {editable ? (
                    <select
                    className="select h-8 py-0 text-[11px] min-w-[5.5rem] flex-1"
                    value={r.detection || ''}
                    onChange={(e) => setRiskDetection(r.id, e.target.value)}
                    aria-label="Detection"
                    title="Detection"
                    >
                    {!r.detection && <option value="">not assessed</option>}
                    {r.detection && !(matrix?.detections ?? []).includes(r.detection) && (
                    <option value={r.detection}>{r.detection}</option>
                    )}
                    {(matrix?.detections ?? []).map((d) => <option key={d} value={d}>{formatLevel(d)}</option>)}
                    </select>
                    ) : (
                    <span className="badge bg-muted text-muted-foreground text-[11px] h-8 flex items-center px-2">{r.detection ? formatLevel(r.detection) : '—'}</span>
                    )}
                  </label>
                </div>
                {r.failure_mode && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    <AutoLinkHtml html={r.failure_mode} kinds={entityKinds} />
                  </div>
                )}
                {r.effect && (
                  <div className="text-xs text-muted-foreground mt-1">
                    <span className="font-semibold text-card-foreground">Effect:</span>{' '}
                    <AutoLinkHtml html={r.effect} kinds={entityKinds} />
                  </div>
                )}
                {r.cause && (
                  <div className="text-xs text-muted-foreground mt-1">
                    <span className="font-semibold text-card-foreground">Cause:</span>{' '}
                    <AutoLinkHtml html={r.cause} kinds={entityKinds} />
                  </div>
                )}
                {(r.linked_requirements.length > 0 || (r.mitigating_requirements || []).length > 0
                 || (r.linked_components || []).length > 0 || (r.mitigating_components || []).length > 0
                 || editable) && (
                  <div className="mt-2">
                    <LinkEditor
                      label="Threatens" hint="" kind="requirement"
                      linked={r.linked_requirements}
                      options={requirements}
                      editable={editable}
                      onAdd={(id) => setRiskRequirements(r.id, [...r.linked_requirements, id])}
                      onRemove={(id) => setRiskRequirements(r.id, r.linked_requirements.filter((x) => x !== id))}
                      nameOf={(id) => requirements.find((q) => q.id === id)?.name ?? ''}
                    />
                    <div className="mt-2">
                      <LinkEditor
                        label="Mitigated By" hint="" kind="requirement"
                        linked={(r.mitigating_requirements || [])}
                        options={requirements}
                        editable={editable}
                        onAdd={(id) => setRiskMitigations(r.id, [...(r.mitigating_requirements || []), id])}
                        onRemove={(id) => setRiskMitigations(r.id, (r.mitigating_requirements || []).filter((x) => x !== id))}
                        nameOf={(id) => requirements.find((q) => q.id === id)?.name ?? ''}
                      />
                    </div>
                    <div className="mt-2">
                      <LinkEditor
                        label="Threatens (components)" hint="" kind="component"
                        linked={(r.linked_components || [])}
                        options={components}
                        editable={editable}
                        onAdd={(id) => setRiskLinkedComponents(r.id, [...(r.linked_components || []), id])}
                        onRemove={(id) => setRiskLinkedComponents(r.id, (r.linked_components || []).filter((x) => x !== id))}
                        nameOf={(id) => components.find((q) => q.id === id)?.name ?? ''}
                      />
                    </div>
                    <div className="mt-2">
                      <LinkEditor
                        label="Mitigated By (components)" hint="" kind="component"
                        linked={(r.mitigating_components || [])}
                        options={components}
                        editable={editable}
                        onAdd={(id) => setRiskMitigatingComponents(r.id, [...(r.mitigating_components || []), id])}
                        onRemove={(id) => setRiskMitigatingComponents(r.id, (r.mitigating_components || []).filter((x) => x !== id))}
                        nameOf={(id) => components.find((q) => q.id === id)?.name ?? ''}
                      />
                    </div>
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-border">
                  <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Comments</h4>
                  <CommentThread entityKind="risks" entityId={r.id} />
                </div>
                <div className="mt-3 pt-3 border-t border-border">
                  <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Change History</h4>
                  <HistoryPanel itemId={r.id} />
                </div>
              </div>
              {editable && (
              <div className="flex items-center gap-0.5 shrink-0">
              <button onClick={() => openEdit(r)} className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all" title="Edit risk"><Edit3 size={14} /></button>
              <button onClick={() => handleDelete(r.id)} className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all" title="Delete"><Trash2 size={14} /></button>
              </div>
              )}
            </div>
          </motion.div>
        ))}
      </div>
      )}
      {selectedIds.size > 0 && canBulk && (
        <BulkActionBar
          count={selectedIds.size}
          onSelectAll={selectAllRisks}
          onClear={clearRiskSelection}
        >
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkRiskStatus(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set status...</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="mitigated">Mitigated</option>
          </select>
          <button onClick={handleBulkRiskDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
  );
}
