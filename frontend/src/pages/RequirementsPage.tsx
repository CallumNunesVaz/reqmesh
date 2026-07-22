import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, Search, X, Trash2, ChevronRight, ChevronDown, ChevronsDownUp, ChevronsUpDown,
  Zap, Gauge, Plug, User, Cpu, Briefcase, Shield, AlertTriangle, Leaf, CheckCircle, Inbox, Square, CheckSquare, ArrowUp,
} from 'lucide-react';
import { api, type Requirement, type EvalVerdict } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { useSelectedReq } from '../components/Layout';
import LoadingSplash from '../components/LoadingSplash';

const statusStyles: Record<string, { dot: string; text: string }> = {
  proposed: { dot: 'bg-cs-blue', text: 'text-cs-blue' },
  approved: { dot: 'bg-cs-green', text: 'text-cs-green' },
  implemented: { dot: 'bg-cs-purple', text: 'text-cs-purple' },
  verified: { dot: 'bg-cs-teal', text: 'text-cs-teal' },
  rejected: { dot: 'bg-cs-red', text: 'text-cs-red' },
  deprecated: { dot: 'bg-cs-grey', text: 'text-cs-grey' },
};

const priorityChips: Record<string, string> = {
  high: 'bg-cs-orange/10 text-cs-orange border-cs-orange/25',
  critical: 'bg-cs-red/10 text-cs-red border-cs-red/25',
};

const typeMeta: Record<string, { icon: typeof Zap; cls: string; label: string }> = {
  functional: { icon: Zap, cls: 'text-cs-blue', label: 'Functional' },
  non_functional_performance: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Performance' },
  non_functional_security: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Security' },
  non_functional_usability: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Usability' },
  non_functional_maintainability: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Maintainability' },
  non_functional_reliability: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Reliability' },
  non_functional_scalability: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Scalability' },
  non_functional_portability: { icon: Gauge, cls: 'text-cs-teal', label: 'Non-Functional \u2013 Portability' },
  interface: { icon: Plug, cls: 'text-cs-purple', label: 'Interface' },
  user: { icon: User, cls: 'text-cs-yellow', label: 'User' },
  system: { icon: Cpu, cls: 'text-cs-pink', label: 'System' },
  business: { icon: Briefcase, cls: 'text-cs-blue', label: 'Business' },
  regulatory_compliance: { icon: Shield, cls: 'text-cs-red', label: 'Regulatory/Compliance' },
  safety: { icon: AlertTriangle, cls: 'text-cs-orange', label: 'Safety' },
  environmental: { icon: Leaf, cls: 'text-cs-green', label: 'Environmental' },
  verification: { icon: CheckCircle, cls: 'text-cs-teal', label: 'Verification' },
};

interface Row {
  req: Requirement;
  depth: number;
  childCount: number;
}

const stripHtml = (s: string) => s.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

export default function RequirementsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { requirements, setRequirements } = useStore();
  const dataVersion = useStore((s) => s.dataVersion);
  const editMode = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');

  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [filterBaseline, setFilterBaseline] = useState('');
  const [filterVerStatus, setFilterVerStatus] = useState('');
  const [filterAllocated, setFilterAllocated] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [projectBaselines, setProjectBaselines] = useState<string[]>([]);
  const [bulkParent, setBulkParent] = useState('');
  const [moveReq, setMoveReq] = useState<{id: string, target: string} | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const [verdicts, setVerdicts] = useState<Map<string, EvalVerdict>>(new Map());
  // Splash only covers the very first fetch — SSE-triggered background
  // reloads swap the data in place without interrupting the reader.
  const [loading, setLoading] = useState(true);

  const load = () => {
    if (!projectId) return;
    api.listRequirements(projectId).then(setRequirements).catch(console.error)
      .finally(() => setLoading(false));
    // Constraint verdicts, so a failing parametric bound is visible from the
    // list without opening each requirement.
    api.getEvaluation(projectId)
      .then((ev) => setVerdicts(new Map(
        ev.requirements.filter((r) => r.verdict !== 'none').map((r) => [r.id, r.verdict]),
      )))
      .catch(() => {});
    api.getProject(projectId).then((p: any) => setProjectBaselines(p.baselines || [])).catch(() => {});
  };
  useEffect(load, [projectId, dataVersion]);

  // '/' focuses search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const byParent = useMemo(() => {
    const ids = new Set(requirements.map((r) => r.id));
    const m = new Map<string | null, Requirement[]>();
    for (const r of requirements) {
      const p = r.parent && ids.has(r.parent) ? r.parent : null;
      if (!m.has(p)) m.set(p, []);
      m.get(p)!.push(r);
    }
    for (const list of m.values()) list.sort((a, b) => a.id.localeCompare(b.id));
    return m;
  }, [requirements]);

  const filtering = !!(search || filterStatus || filterType || filterPriority || filterBaseline || filterVerStatus || filterAllocated);

  // IDs that match the current search/filters directly
  const matchIds = useMemo(() => {
    if (!filtering) return null;
    const q = search.toLowerCase();
    const allocatedQ = filterAllocated.toLowerCase();
    const ids = new Set<string>();
    for (const r of requirements) {
      if (filterStatus && r.status !== filterStatus) continue;
      if (filterType && r.type !== filterType) continue;
      if (filterPriority && r.priority !== filterPriority) continue;
      if (filterBaseline && (!r.baselines || !r.baselines.includes(filterBaseline))) continue;
      if (filterVerStatus && r.verification_status !== filterVerStatus) continue;
      if (allocatedQ) {
        const allocated = (r.allocated_to || '').toLowerCase();
        if (!allocated.includes(allocatedQ)) continue;
      }
      if (q) {
        const hay = `${r.id} ${r.name} ${stripHtml(r.description || '')} ${r.rationale || ''} ${r.allocated_to || ''}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      ids.add(r.id);
    }
    return ids;
  }, [requirements, filtering, search, filterStatus, filterType, filterPriority, filterBaseline, filterVerStatus, filterAllocated]);

  // Flatten the tree in DFS order. While filtering, keep ancestors of matches
  // for context and ignore manual collapse so results are always visible.
  const rows = useMemo(() => {
    const out: Row[] = [];
    const subtreeMatches = (r: Requirement): boolean => {
      if (!matchIds) return true;
      if (matchIds.has(r.id)) return true;
      return (byParent.get(r.id) || []).some(subtreeMatches);
    };
    const walk = (parent: string | null, depth: number) => {
      for (const r of byParent.get(parent) || []) {
        if (filtering && !subtreeMatches(r)) continue;
        const children = byParent.get(r.id) || [];
        out.push({ req: r, depth, childCount: children.length });
        if (children.length && (filtering || !collapsed.has(r.id))) walk(r.id, depth + 1);
      }
    };
    walk(null, 0);
    return out;
  }, [byParent, collapsed, filtering, matchIds]);

  const matchCount = matchIds ? matchIds.size : requirements.length;
  const parentIds = useMemo(
    () => requirements.filter((r) => (byParent.get(r.id) || []).length > 0).map((r) => r.id),
    [requirements, byParent],
  );
  const allCollapsed = parentIds.length > 0 && parentIds.every((id) => collapsed.has(id));

  const toggleCollapse = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const handleDelete = async (reqId: string) => {
    if (!projectId || !editMode) return;
    if (!confirm(`Delete requirement ${reqId}?`)) return;
    try {
      await api.deleteRequirement(projectId, reqId);
      load();
    } catch {
      // silently no-op when permissions insufficient
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedIds(new Set(rows.map((r) => r.req.id)));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBulkStatus = async (status: string) => {
    if (!projectId) return;
    await api.bulkUpdateRequirements(projectId, [...selectedIds], { status });
    clearSelection();
    load();
  };

  const handleBulkDelete = async () => {
    if (!projectId) return;
    if (!confirm(`Delete ${selectedIds.size} requirement(s)?`)) return;
    await api.bulkDeleteRequirements(projectId, [...selectedIds]);
    clearSelection();
    load();
  };

  const handleBulkBaseline = async (baseline: string) => {
    if (!projectId) return;
    await api.bulkUpdateRequirements(projectId, [...selectedIds], { baselines: [baseline] });
    clearSelection();
    load();
  };

  const handleBulkReparent = async () => {
    if (!bulkParent.trim()) return;
    await api.bulkReparentRequirements(projectId!, [...selectedIds], bulkParent.trim(), true);
    clearSelection();
    load();
    setBulkParent('');
  };

  const handleSingleReparent = async () => {
    if (!moveReq || !moveReq.target.trim()) return;
    await api.bulkReparentRequirements(projectId!, [moveReq.id], moveReq.target.trim(), true);
    setMoveReq(null);
    load();
  };

  return (
    <div className="relative max-w-4xl mx-auto px-6 py-6 min-h-[50vh]">
      {loading && requirements.length === 0 && <LoadingSplash label="Loading requirements…" />}
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Requirements</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {filtering ? `${matchCount} of ${requirements.length} requirements` : `${requirements.length} requirements`}
          </p>
        </div>
        {editMode && (
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus size={15} />
            New Requirement
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={searchRef}
              className="input pl-9 pr-14 h-9"
              placeholder="Search requirements…"
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
            <option value="proposed">Proposed</option>
            <option value="approved">Approved</option>
            <option value="implemented">Implemented</option>
            <option value="verified">Verified</option>
            <option value="rejected">Rejected</option>
            <option value="deprecated">Deprecated</option>
          </select>
          <select className="select w-36 h-9 text-xs" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">All types</option>
            {Object.entries(typeMeta).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          <select className="select w-32 h-9 text-xs" value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}>
            <option value="">All priorities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <select className="select w-36 h-9 text-xs" value={filterBaseline} onChange={(e) => setFilterBaseline(e.target.value)}>
            <option value="">All baselines</option>
            {projectBaselines.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <select className="select w-36 h-9 text-xs" value={filterVerStatus} onChange={(e) => setFilterVerStatus(e.target.value)}>
            <option value="">All ver. statuses</option>
            <option value="pending">Pending</option>
            <option value="passed">Passed</option>
            <option value="failed">Failed</option>
            <option value="na">N/A</option>
          </select>
          <input
            className="input text-xs w-28 h-9"
            placeholder="Allocated to…"
            value={filterAllocated}
            onChange={(e) => setFilterAllocated(e.target.value)}
          />
          <button
            onClick={() => setCollapsed(allCollapsed ? new Set() : new Set(parentIds))}
            className="btn-secondary h-9 px-3 text-xs"
            title={allCollapsed ? 'Expand all' : 'Collapse all'}
          >
            {allCollapsed ? <ChevronsUpDown size={14} /> : <ChevronsDownUp size={14} />}
          </button>
        </div>
      </div>

      {/* Tree list */}
      <div className="card mt-2 overflow-hidden divide-y divide-border/60">
        {rows.length === 0 ? (
          <div className="p-14 text-center">
            <Inbox size={28} className="mx-auto text-muted-foreground/50 mb-3" />
            <p className="text-sm text-muted-foreground">
              {filtering ? 'No requirements match your filters.' : 'No requirements yet.'}
            </p>
            {filtering ? (
              <button
                className="text-xs text-primary hover:underline mt-2"
                onClick={() => { setSearch(''); setFilterStatus(''); setFilterType(''); setFilterPriority(''); setFilterBaseline(''); setFilterVerStatus(''); setFilterAllocated(''); }}
              >
                Clear filters
              </button>
            ) : editMode && (
              <button className="text-xs text-primary hover:underline mt-2" onClick={() => setShowCreate(true)}>
                Create the first one
              </button>
            )}
          </div>
        ) : (
          <>
            {editMode && rows.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-2 border-b border-border/60 bg-muted/30">
                <span className="shrink-0 mr-0.5 cursor-pointer" onClick={() => selectedIds.size === rows.length ? clearSelection() : selectAllVisible()}>
                  {selectedIds.size === rows.length && rows.length > 0 ? (
                    <CheckSquare size={13} className="text-primary" />
                  ) : (
                    <Square size={13} className="text-muted-foreground/40 hover:text-muted-foreground" />
                  )}
                </span>
                <span className="text-[11px] text-muted-foreground">Select all</span>
              </div>
            )}
            {rows.map(({ req, depth, childCount }) => {
            const TypeIcon = (typeMeta[req.type] || typeMeta.functional).icon;
            const typeCls = (typeMeta[req.type] || typeMeta.functional).cls;
            const status = statusStyles[req.status] || statusStyles.proposed;
            const isCollapsed = collapsed.has(req.id);
            const dimByFilter = matchIds && !matchIds.has(req.id);
            return (
              <div
                key={req.id}
                onClick={() => navigate(`/project/${projectId}/requirements/${req.id}`)}
                className={`group flex items-center gap-2 pr-3 py-[7px] cursor-pointer transition-colors hover:bg-accent/40 ${dimByFilter ? 'opacity-45' : ''}`}
                style={{ paddingLeft: `${12 + depth * 22}px` }}
              >
                {/* Selection checkbox */}
                {editMode && (
                  <span className="shrink-0 mr-0.5" onClick={(e) => e.stopPropagation()}>
                    {selectedIds.has(req.id) ? (
                      <CheckSquare size={13} className="text-primary cursor-pointer" onClick={() => toggleSelect(req.id)} />
                    ) : (
                      <Square size={13} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={() => toggleSelect(req.id)} />
                    )}
                  </span>
                )}

                {/* Expand / collapse */}
                {childCount > 0 ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleCollapse(req.id); }}
                    className="p-0.5 rounded hover:bg-secondary text-muted-foreground shrink-0"
                    title={isCollapsed ? 'Expand' : 'Collapse'}
                  >
                    {isCollapsed && !filtering ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                  </button>
                ) : (
                  <span className="w-[18px] shrink-0" />
                )}

                <TypeIcon size={13} className={`shrink-0 ${typeCls}`} />

                <span className="font-mono text-[11px] text-muted-foreground shrink-0 w-[4.8rem]">{req.id}</span>

                <span className={`text-[13px] truncate shrink-0 max-w-[45%] ${childCount > 0 ? 'font-semibold' : 'font-medium'} text-foreground`}>
                  {req.name || 'Untitled'}
                </span>

                {req.description && (
                  <span className="text-xs text-muted-foreground/70 truncate flex-1 min-w-0 hidden md:inline">
                    {stripHtml(req.description)}
                  </span>
                )}
                <span className="flex-1" />

                {/* Meta */}
                <span className="flex items-center gap-2 shrink-0">
                  {childCount > 0 && isCollapsed && !filtering && (
                    <span className="text-[10px] text-muted-foreground bg-secondary rounded-full px-1.5 py-px">{childCount}</span>
                  )}
                  {priorityChips[req.priority] && (
                    <span className={`badge border text-[10px] px-1.5 py-px ${priorityChips[req.priority]}`}>{req.priority}</span>
                  )}
                  <span className="flex items-center gap-1.5 w-[5.6rem]">
                    <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                    <span className="text-[11px] text-muted-foreground capitalize">{req.status}</span>
                  </span>
                  {req.verification_status === 'passed' && <span className="w-1.5 h-1.5 rounded-full bg-cs-green" title="Verification passed" />}
                  {req.verification_status === 'failed' && <span className="w-1.5 h-1.5 rounded-full bg-cs-red" title="Verification failed" />}
                  {verdicts.has(req.id) && (
                    <span
                      className={`text-[10px] font-semibold leading-none ${
                        verdicts.get(req.id) === 'pass' ? 'text-cs-teal'
                          : verdicts.get(req.id) === 'unknown' ? 'text-cs-yellow'
                          : 'text-cs-red'
                      }`}
                      title={`Parametric constraints: ${verdicts.get(req.id)}`}
                    >
                      Σ
                    </span>
                  )}
                  {editMode && (
                    <>
                      {moveReq?.id === req.id ? (
                        <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <input
                            className="input text-[11px] w-20 h-6"
                            placeholder="Parent ID"
                            value={moveReq.target}
                            onChange={(e) => setMoveReq({ ...moveReq, target: e.target.value })}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleSingleReparent(); if (e.key === 'Escape') setMoveReq(null); }}
                            autoFocus
                          />
                          <button onClick={handleSingleReparent} className="btn-secondary text-[10px] px-1.5 py-0.5" disabled={!moveReq.target.trim()}>Move</button>
                          <button onClick={() => setMoveReq(null)} className="p-1 rounded hover:bg-accent text-muted-foreground"><X size={11} /></button>
                        </span>
                      ) : (
                        <button
                          onClick={(e) => { e.stopPropagation(); setMoveReq({ id: req.id, target: '' }); }}
                          className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Move to parent"
                        >
                          <ChevronRight size={13} />
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(req.id); }}
                        className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Delete"
                      >
                        <Trash2 size={13} />
                      </button>
                    </>
                  )}
                </span>
              </div>
            );
          })}
          </>
        )}
      </div>

      {selectedIds.size > 0 && editMode && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) handleBulkStatus(e.target.value); e.target.value = ''; }}
            value=""
          >
            <option value="">Set status...</option>
            <option value="proposed">Proposed</option>
            <option value="approved">Approved</option>
            <option value="implemented">Implemented</option>
            <option value="verified">Verified</option>
            <option value="rejected">Rejected</option>
            <option value="deprecated">Deprecated</option>
          </select>
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkBaseline(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set baseline...</option>
            {projectBaselines.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <input className="input text-xs w-20" placeholder="Parent ID" value={bulkParent} onChange={(e) => setBulkParent(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleBulkReparent(); }} />
          <button onClick={handleBulkReparent} className="btn-secondary text-xs" disabled={!bulkParent.trim()}>Move</button>
          <button onClick={handleBulkDelete} className="btn-danger text-xs">
            <Trash2 size={13} /> Delete
          </button>
          <button onClick={selectAllVisible} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearSelection} className="text-[10px] text-muted-foreground hover:text-foreground">
            <X size={13} />
          </button>
        </div>
      )}

      <CreateRequirementModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        projectId={projectId!}
        requirements={requirements}
        onCreated={load}
      />
    </div>
  );
}

function CreateRequirementModal({
  open, onClose, projectId, requirements, onCreated,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  requirements: Requirement[];
  onCreated: () => void;
}) {
  const [form, setForm] = useState({ id: '', name: '', type: 'functional', priority: 'medium', parent: '', description: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { selectedReqId } = useSelectedReq();

  useEffect(() => {
    if (!open) return;
    setError('');
    const parent = selectedReqId || '';
    setForm((f) => ({ ...f, parent }));
    const parentParam = parent || undefined;
    api.getNextUid(projectId, parentParam)
      .then((uid) => setForm((f) => ({ ...f, id: uid.next_id, parent })))
      .catch(() => {});
  }, [open, projectId, selectedReqId]);

  const jumpToParent = () => {
    if (!form.parent) return;
    const parentReq = requirements.find(r => r.id === form.parent);
    if (parentReq?.parent) {
      setForm((f) => ({ ...f, parent: parentReq.parent! }));
      api.getNextUid(projectId, parentReq.parent)
        .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
        .catch(() => {});
    } else {
      setForm((f) => ({ ...f, parent: '' }));
      api.getNextUid(projectId)
        .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
        .catch(() => {});
    }
  };

  const handleParentChange = (parentId: string) => {
    setForm((f) => ({ ...f, parent: parentId }));
    api.getNextUid(projectId, parentId || undefined)
      .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
      .catch(() => {});
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.id.trim()) return;
    setBusy(true);
    setError('');
    try {
      const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      await api.createRequirement(projectId, {
        ...form,
        description: form.description ? `<p>${esc(form.description)}</p>` : '',
        parent: form.parent || undefined,
      });
      setForm({ id: '', name: '', type: 'functional', priority: 'medium', parent: '', description: '' });
      onClose();
      onCreated();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const parentOptions = [...requirements].sort((a, b) => a.id.localeCompare(b.id));

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px] flex items-start justify-center pt-[12vh] px-4"
          onClick={onClose}
        >
          <motion.form
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="card w-full max-w-lg p-5 shadow-xl"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-foreground">New Requirement</h2>
              <button type="button" onClick={onClose} className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent">
                <X size={15} />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="label">Parent</label>
                <div className="flex gap-1.5">
                  <select className="select flex-1" value={form.parent} onChange={(e) => handleParentChange(e.target.value)}>
                    <option value="">None (top level)</option>
                    {parentOptions.map((r) => (
                      <option key={r.id} value={r.id}>{r.id} — {r.name || 'Untitled'}</option>
                    ))}
                  </select>
                  <button type="button" onClick={jumpToParent}
                    className="p-2 rounded-md border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                    title="Jump to parent group"
                    disabled={!form.parent || !requirements.find(r => r.id === form.parent)}>
                    <ArrowUp size={14} />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-[8rem_1fr] gap-3">
                <div>
                  <label className="label">ID</label>
                  <input className="input font-mono" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
                </div>
                <div>
                  <label className="label">Name</label>
                  <input className="input" placeholder="Requirement name" value={form.name} autoFocus
                    onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Type</label>
                  <select className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                    {Object.entries(typeMeta).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Priority</label>
                  <select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="label">Description <span className="normal-case font-normal">(optional)</span></label>
                <textarea
                  className="input min-h-[72px] resize-y"
                  placeholder="Describe the requirement…"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={busy || !form.id.trim()} className="btn-primary">
                {busy ? 'Creating…' : 'Create requirement'}
              </button>
            </div>
          </motion.form>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
