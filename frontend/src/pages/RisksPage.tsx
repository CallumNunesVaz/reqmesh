import { useEffect, useMemo, useState, useId, useRef } from 'react';
import { usePersistedState } from '../hooks/usePersistedState';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { expandHeight } from '../lib/animations';
import { Plus, Trash2, Square, CheckSquare, X, Search, AlertTriangle, Link2, ChevronDown } from 'lucide-react';
import { api, RISK_STATUSES, type Risk, type RiskMatrix, type RequirementTreeNode, type ComponentTreeNode } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { CopyLinkButton } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import RichTextEditor from '../components/RichTextEditor';
import { useToasts } from '../components/Toast';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';
import EmptyState from '../components/EmptyState';
import { subtreeIds, riskInGroup, flattenTree, type TreeOption } from '../lib/riskGroups';
import { compareRisks, type RiskSortKey, type SortDir } from '../lib/riskSort';

const formatLevel = (s: string) => s.replace(/_/g, ' ');

const likelihoodOf = (r: Risk) => r.rating?.likelihood ?? r.likelihood ?? r.probability ?? '';

const riskLinkCount = (r: Risk) =>
  (r.linked_requirements ?? []).length
  + (r.mitigating_requirements ?? []).length
  + (r.linked_components ?? []).length
  + (r.mitigating_components ?? []).length;

/** A searchable picker over a flattened tree, one selection or none. */
function GroupPicker({ label, value, onChange, options, placeholder }: {
  label: string; value: string; onChange: (id: string) => void;
  options: TreeOption[]; placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? options.filter((o) => o.id.toLowerCase().includes(q) || o.name.toLowerCase().includes(q))
    : options;
  const selected = options.find((o) => o.id === value);

  return (
    <div ref={containerRef} className="relative" data-group-picker={label}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="input h-9 text-xs flex items-center gap-1.5 justify-between min-w-[10rem] max-w-[14rem] cursor-pointer"
        aria-label={label} title={selected ? `${label}: ${selected.name}` : label}>
        <span className="truncate">{selected ? `${label}: ${selected.name}` : label}</span>
        <ChevronDown size={13} className="shrink-0 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute z-50 left-0 mt-1 w-72 rounded-lg border bg-popover shadow-lg">
          <div className="p-2 border-b">
            <input
              className="input h-8 text-xs"
              placeholder={`Search ${placeholder}…`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            <button
              type="button"
              onClick={() => { onChange(''); setOpen(false); setQuery(''); }}
              className="w-full text-left px-2 py-1.5 text-xs rounded-md hover:bg-accent text-muted-foreground"
            >
              All {placeholder}
            </button>
            {filtered.map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => { onChange(o.id); setOpen(false); setQuery(''); }}
                className={`w-full text-left px-2 py-1.5 text-xs rounded-md hover:bg-accent flex items-center gap-2 ${o.id === value ? 'bg-primary/10 text-primary' : ''}`}
              >
                <span className="font-mono text-3xs text-muted-foreground shrink-0" style={{ paddingLeft: o.depth * 14 }}>{o.id}</span>
                <span className="truncate">{o.name}</span>
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="px-2 py-1.5 text-xs text-muted-foreground">No matches</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function RisksPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
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

  const [reqTree, setReqTree] = useState<RequirementTreeNode[]>([]);
  const [compTree, setCompTree] = useState<ComponentTreeNode[]>([]);
  const [matrix, setMatrix] = useState<RiskMatrix | null>(null);
  const [loading, setLoading] = useState(true);

  // Persisted per project — see RequirementsPage/ComponentsPage for why.
  const pk = (field: string) => (projectId ? `rt-risks-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterStatus, setFilterStatus] = usePersistedState(pk('filter-status'), '');
  const [filterSeverity, setFilterSeverity] = usePersistedState(pk('filter-severity'), '');
  const [filterLikelihood, setFilterLikelihood] = usePersistedState(pk('filter-likelihood'), '');
  const [filterComponentGroup, setFilterComponentGroup] = usePersistedState(pk('filter-component-group'), '');
  const [filterRequirementGroup, setFilterRequirementGroup] = usePersistedState(pk('filter-requirement-group'), '');
  const [sortKey, setSortKey] = usePersistedState<RiskSortKey>(pk('sort-key'), 'id');
  const [sortDir, setSortDir] = usePersistedState<SortDir>(pk('sort-dir'), 'asc');

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
    api.getRequirementTree(projectId).then((t) => { if (alive) setReqTree(t); }).catch(() => {});
    api.getComponentTree(projectId).then((t) => { if (alive) setCompTree(t); }).catch(() => {});
    return () => { alive = false; };
  }, [projectId, dataVersion]);

  // The subtrees the two group filters match against, computed once per
  // selection rather than per risk.
  const compSubtree = useMemo(
    () => (filterComponentGroup ? subtreeIds(compTree, filterComponentGroup) : null),
    [compTree, filterComponentGroup],
  );
  const reqSubtree = useMemo(
    () => (filterRequirementGroup ? subtreeIds(reqTree, filterRequirementGroup) : null),
    [reqTree, filterRequirementGroup],
  );

  const reqOptions = useMemo(() => flattenTree(reqTree), [reqTree]);
  const compOptions = useMemo(() => flattenTree(compTree), [compTree]);

  const filteredRisks = useMemo(() => {
    const q = search.toLowerCase();
    const bands = matrix?.bands ?? [];
    const out = risks.filter((r) => {
      if (filterStatus && r.status !== filterStatus) return false;
      if (filterSeverity && r.severity !== filterSeverity) return false;
      if (filterLikelihood && likelihoodOf(r) !== filterLikelihood) return false;
      if (compSubtree && !riskInGroup(r, compSubtree)) return false;
      if (reqSubtree && !riskInGroup(r, reqSubtree)) return false;
      if (q) {
        const hay = `${r.id} ${r.title || ''} ${r.failure_mode || ''} ${r.effect || ''} ${r.cause || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    if (sortKey === 'id' && sortDir === 'asc') return out;
    return [...out].sort((a, b) => compareRisks(a, b, sortKey, sortDir, bands));
  }, [risks, search, filterStatus, filterSeverity, filterLikelihood, compSubtree, reqSubtree, matrix, sortKey, sortDir]);

  const filtering = !!(search || filterStatus || filterSeverity || filterLikelihood || filterComponentGroup || filterRequirementGroup);

  // Arriving from an older link (?focus=RSK-001): ring and scroll to the row.
  const focusId = useFocusedEntity(risks.length > 0);

  const toggleSort = (col: RiskSortKey) => {
    if (sortKey === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(col); setSortDir('asc'); }
  };

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

  // `filteredRisks` is the list as displayed, which is the only ordering a
  // Shift range may span.
  const { selectedIds, select: toggleRisk, setSelectedIds } =
    useRangeSelection(useMemo(() => filteredRisks.map((r) => r.id), [filteredRisks]));
  const clearRiskSelection = () => setSelectedIds(new Set());
  const selectAllRisks = () => setSelectedIds(new Set(filteredRisks.map(r => r.id)));

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

  const SortHead = ({ col, label }: { col: RiskSortKey; label: string }) => (
    <button onClick={() => toggleSort(col)} className={`text-3xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground flex items-center gap-0.5 ${sortKey === col ? 'text-foreground' : ''}`}>
      {label}{sortKey === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
    </button>
  );

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
        <div className="flex gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[12rem]">
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
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded-md border bg-muted text-3xs font-mono text-muted-foreground pointer-events-none">/</kbd>
            )}
          </div>
          <select className="select w-32 h-9 text-xs" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All statuses</option>
            {RISK_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="select w-32 h-9 text-xs" value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
            <option value="">All severities</option>
            {(matrix?.severities ?? []).map((sv) => <option key={sv} value={sv}>{formatLevel(sv)}</option>)}
          </select>
          <select className="select w-36 h-9 text-xs" value={filterLikelihood} onChange={(e) => setFilterLikelihood(e.target.value)}>
            <option value="">All likelihoods</option>
            {(matrix?.likelihoods ?? []).map((l) => <option key={l} value={l}>{formatLevel(l)}</option>)}
          </select>
          <GroupPicker label="Component group" value={filterComponentGroup} onChange={setFilterComponentGroup} options={compOptions} placeholder="components" />
          <GroupPicker label="Requirement group" value={filterRequirementGroup} onChange={setFilterRequirementGroup} options={reqOptions} placeholder="requirements" />
        </div>
      </div>
      <AnimatePresence>
        {showCreate && (
          <motion.form variants={expandHeight} initial="initial" animate="animate" exit="exit"
            onSubmit={handleCreate} className="card p-4 mb-4 overflow-hidden">
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-32"><label className="label">ID <input className="input font-mono" placeholder="RSK-001" value={form.id} onChange={e => setForm({...form, id: e.target.value})} disabled={!!editingId} /></label>{!editingId && idExample && <span className="text-3xs text-muted-foreground">e.g. {idExample}</span>}</div>
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
        <EmptyState
          icon={AlertTriangle}
          title={filtering ? 'No risks match your filters.' : 'No risks yet'}
          hint={filtering ? undefined : 'Identify and track project risks with severity and likelihood.'}
          action={!filtering && editable ? { label: 'Create the first risk', onClick: openCreate } : undefined}
        >
          {filtering && (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterStatus(''); setFilterSeverity(''); setFilterLikelihood(''); setFilterComponentGroup(''); setFilterRequirementGroup(''); }}>Clear filters</button>
          )}
        </EmptyState>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-muted/30">
                {canBulk && <th className="px-3 py-2.5 w-0" aria-label="Select" />}
                <th className="px-4 py-2.5 w-28"><SortHead col="id" label="ID" /></th>
                <th className="px-4 py-2.5 min-w-[14rem]"><SortHead col="title" label="Title" /></th>
                <th className="px-4 py-2.5 w-28"><SortHead col="severity" label="Severity" /></th>
                <th className="px-4 py-2.5 w-32"><SortHead col="likelihood" label="Likelihood" /></th>
                <th className="px-4 py-2.5 w-28"><SortHead col="band" label="Band" /></th>
                <th className="px-4 py-2.5 w-28"><SortHead col="status" label="Status" /></th>
                <th className="px-4 py-2.5 w-24"><SortHead col="links" label="Links" /></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredRisks.map((r) => {
                const total = riskLinkCount(r);
                return (
                  <tr key={r.id} id={`entity-${r.id}`}
                    onClick={() => navigate(`/project/${projectId}/risks/${encodeURIComponent(r.id)}`)}
                    className={`group rt-row hover:bg-accent/30 transition-colors cursor-pointer ${focusId === r.id ? 'ring-2 ring-primary/50' : ''}`}>
                    {canBulk && (
                      <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                        {selectedIds.has(r.id) ? (
                          <CheckSquare size={14} className="text-primary cursor-pointer" onClick={(e) => toggleRisk(r.id, e)} />
                        ) : (
                          <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={(e) => toggleRisk(r.id, e)} />
                        )}
                      </td>
                    )}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs text-card-foreground">{r.id}</span>
                        <CopyLinkButton kind="risk" id={r.id} className="opacity-0 group-hover:opacity-100" />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">
                      <span className="line-clamp-1" title={r.title || undefined}>{r.title || <span className="text-muted-foreground/40 italic">—</span>}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">{r.severity ? formatLevel(r.severity) : '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">{likelihoodOf(r) ? formatLevel(likelihoodOf(r)) : '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5 text-2xs font-medium"
                        style={{ color: r.rating?.color || 'hsl(var(--muted-foreground))' }}
                        title={r.rating?.band ? `severity ${formatLevel(r.rating.severity || '')} x likelihood ${formatLevel(r.rating.likelihood || '')}` : (r.rating?.unrated_reason || 'Not rated')}>
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: r.rating?.color || 'hsl(var(--muted-foreground))' }} />
                        {/* The band as text, not only as colour: it is the matrix's
                            output, and a reader who cannot distinguish the dot's
                            hue would otherwise have no way to read it. */}
                        {r.rating?.label || 'Unrated'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">{r.status || '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1 text-2xs tabular-nums text-muted-foreground" title={`${(r.linked_requirements ?? []).length + (r.mitigating_requirements ?? []).length} requirement link(s), ${(r.linked_components ?? []).length + (r.mitigating_components ?? []).length} component link(s)`}>
                        <Link2 size={12} /> {total > 0 ? total : '—'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
            {RISK_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={handleBulkRiskDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
  );
}
