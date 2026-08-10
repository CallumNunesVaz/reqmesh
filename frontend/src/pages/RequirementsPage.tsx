import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CreateRequirementModal, { type CreateIntent } from '../components/CreateRequirementModal';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, Search, X, Trash2, ChevronRight, ChevronDown, ChevronsDownUp, ChevronsUpDown,
  Inbox, Square, CheckSquare, ArrowUp, SlidersHorizontal, Copy, AlertTriangle,
} from 'lucide-react';
import { api, baselineNames, getTruncationInfo, type Requirement, type EvalVerdict, type TruncationInfo } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { useUndoStore } from '../store/undo';
import { useSelectedReq } from '../components/Layout';
import LoadingSplash from '../components/LoadingSplash';
import RichTextEditor from '../components/RichTextEditor';
import { useConfirm } from '../components/ConfirmDialog';
import { deleteWithReferenceCheck } from '../lib/forceDelete';
import { REQUIREMENT_TYPES, REQUIREMENT_TYPE_META, reqTypeClass, reqTypeIcon } from '../lib/requirementTypes';
import BodyPortal from '../components/BodyPortal';
import { useToasts } from '../components/Toast';
import TruncationBanner from '../components/TruncationBanner';
import ReparentDialog from '../components/ReparentDialog';
import { DndContext, DragOverlay, closestCenter } from '@dnd-kit/core';
import { useTreeDrag } from '../hooks/useTreeDrag';
import { DropRow, DragGrip, TopLevelDropZone } from '../components/TreeDragRow';

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

// Types live in ../lib/requirementTypes \u2014 see the note there on why they used
// to be declared in six places.

interface Row {
  req: Requirement;
  depth: number;
  childCount: number;
}

const stripHtml = (s: string) => s.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

export default function RequirementsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { requirements, setRequirements } = useStore();
  const dataVersion = useStore((s) => s.dataVersion);
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const editMode = useAuthStore((s) => s.canEdit());
  // Role alone, without the edit-mode toggle — see the deep-link effect below.
  const canEditRole = useAuthStore((s) => s.user?.role === 'maintainer' || s.user?.role === 'admin');
  const setEditMode = useAuthStore((s) => s.setEditMode);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();
  const { selectedReqId, selectReq } = useSelectedReq();

  // Search, filters and the collapsed-tree state persist per project, so
  // navigating to another requirement (or another page) and back does not
  // silently reset a list the operator just spent time configuring — the
  // same reset that made "collapse everything, drill into one, come back"
  // undo itself on every visit.
  const pk = (field: string) => (projectId ? `rt-reqs-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterStatus, setFilterStatus] = usePersistedState(pk('filter-status'), '');
  const [filterType, setFilterType] = usePersistedState(pk('filter-type'), '');
  const [filterPriority, setFilterPriority] = usePersistedState(pk('filter-priority'), '');
  const [filterBaseline, setFilterBaseline] = usePersistedState(pk('filter-baseline'), '');
  const [filterVerStatus, setFilterVerStatus] = usePersistedState(pk('filter-verstatus'), '');
  const [filterAllocated, setFilterAllocated] = usePersistedState(pk('filter-allocated'), '');
  const [collapsed, setCollapsed] = usePersistedState<Set<string>>(pk('collapsed'), new Set(), setCodec<string>());
  const [createIntent, setCreateIntent] = useState<CreateIntent | null>(null);
  const [projectBaselines, setProjectBaselines] = useState<string[]>([]);
  // Which rows the reparent dialog is currently moving. Replaces two
  // free-text "Parent ID" boxes that accepted any string, including a
  // descendant (a cycle) or a typo (an orphan).
  const [movingIds, setMovingIds] = useState<string[] | null>(null);
  const [showBulkEdit, setShowBulkEdit] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const [verdicts, setVerdicts] = useState<Map<string, EvalVerdict>>(new Map());
  // Splash only covers the very first fetch — SSE-triggered background
  // reloads swap the data in place without interrupting the reader.
  const [loading, setLoading] = useState(true);
  const [truncation, setTruncation] = useState<TruncationInfo | null>(null);

  const load = () => {
    if (!projectId) return;
    api.listRequirements(projectId).then(setRequirements).catch(console.error)
      .finally(() => { setLoading(false); setTruncation(getTruncationInfo('requirements')); });
    // Constraint verdicts, so a failing parametric bound is visible from the
    // list without opening each requirement.
    api.getEvaluation(projectId)
      .then((ev) => setVerdicts(new Map(
        ev.requirements.filter((r) => r.verdict !== 'none').map((r) => [r.id, r.verdict]),
      )))
      .catch(() => {});
    api.getProject(projectId).then((p) => setProjectBaselines(baselineNames(p.baselines))).catch(() => {});
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Open create form from ?new=1[&parent=<id>] after requirements are loaded
  useEffect(() => {
    const newParam = searchParams.get('new');
    if (newParam !== '1') return;
    if (requirements.length === 0) return;
    // Gate on the *role*, not canEdit(). canEdit() is role AND the edit-mode
    // toggle, and that toggle defaults off and does not survive a page load —
    // so gating on it would make every cold-loaded link a no-op, which is the
    // one case these links exist for. A viewer still gets nothing: the form
    // would be unsubmittable, and its overlay covers the edit toggle they would
    // need. The params are cleared either way so a reload cannot resurrect it.
    if (!canEditRole) { setSearchParams({}, { replace: true }); return; }
    // Following a create link is an explicit intent to edit.
    if (!editMode) setEditMode(true);

    const parentParam = searchParams.get('parent');
    let intent: CreateIntent = { mode: 'blank' };

    if (parentParam) {
      const parentExists = requirements.some((r) => r.id === parentParam);
      if (parentExists) {
        intent = { mode: 'child', parent: parentParam };
      }
    }

    setCreateIntent(intent);
    setSearchParams({}, { replace: true });
  }, [searchParams, requirements, setSearchParams, editMode, canEditRole, setEditMode]);

  // 'n' shortcut opens create form (edit mode only)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'n') return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) return;
      if (!editMode) return;
      if (createIntent !== null) return;
      e.preventDefault();
      navigate(`/project/${projectId}/requirements?new=1`);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [editMode, createIntent, navigate, projectId]);

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
    const ok = await showConfirm(`Delete requirement ${reqId}?`, 'Delete Requirement');
    if (!ok) return;
    try {
      const before = requirements.find((r) => r.id === reqId);
      const done = await deleteWithReferenceCheck(
        (force) => api.deleteRequirement(projectId, reqId, force),
        (msg) => showConfirm(msg, 'Referenced by other records'),
      );
      if (!done) return;
      if (before) {
        const snap = { ...before };
        useUndoStore.getState().push({
          description: `Delete ${reqId}`,
          undo: async () => { await api.createRequirement(projectId, snap); },
          redo: async () => { await api.deleteRequirement(projectId, reqId, true); },
        });
      }
      bumpGraphVersion();
      bumpDataVersion();
      if (selectedReqId === reqId) selectReq(null);
      load();
    } catch (e: any) {
      addToast('error', e?.message || 'Delete failed');
    }
  };

  // `rows` is the tree as displayed — filtered, and with collapsed branches
  // omitted — which is the only ordering a Shift range may span.
  const { selectedIds, select: toggleSelect, setSelectedIds, clear: clearSelection } =
    useRangeSelection(useMemo(() => rows.map((r) => r.req.id), [rows]));

  const selectAllVisible = () => {
    setSelectedIds(new Set(rows.map((r) => r.req.id)));
  };

  const handleBulkDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const ok = await showConfirm(`Delete ${ids.length} requirement(s)?`, 'Bulk Delete');
    if (!ok) return;
    const saved = requirements.filter((r) => ids.includes(r.id)).map((r) => ({ ...r }));
    try {
      await api.bulkDeleteRequirements(projectId, ids);
      useUndoStore.getState().push({
        description: `Delete ${ids.length} requirements`,
        undo: async () => {
          for (const r of saved) {
            await api.createRequirement(projectId, r);
          }
        },
        redo: async () => { await api.bulkDeleteRequirements(projectId, ids); },
      });
      bumpGraphVersion();
      bumpDataVersion();
      if (selectedReqId && ids.includes(selectedReqId)) selectReq(null);
      clearSelection();
      load();
    } catch (e: any) {
      addToast('error', e?.message || 'Bulk delete failed');
    }
  };

  // Add or remove one baseline across the selection, leaving every other
  // baseline those rows carry alone. This used to send `{ baselines: [name] }`,
  // which replaced the whole list — ticking twenty rows and picking "PDR"
  // silently dropped their other milestones, with no undo entry to get them back.
  const handleBulkBaseline = async (baseline: string, op: 'add' | 'remove') => {
    if (!projectId) return;
    const ids = [...selectedIds];
    try {
      const res = await api.setRequirementBaselines(projectId, ids, op === 'add' ? { add: [baseline] } : { remove: [baseline] });
      if (res.updated === 0) {
        addToast('success', op === 'add'
          ? `All ${ids.length} already in ${baseline}`
          : `None of the ${ids.length} were in ${baseline}`);
      } else {
        // Invert over the ids that actually changed, so undo cannot strip the
        // baseline from a row that already had it before this ran.
        const touched = res.ids;
        useUndoStore.getState().push({
          description: `${op === 'add' ? 'Add' : 'Remove'} ${baseline} on ${touched.length} requirement(s)`,
          undo: async () => {
            await api.setRequirementBaselines(projectId, touched, op === 'add' ? { remove: [baseline] } : { add: [baseline] });
          },
          redo: async () => {
            await api.setRequirementBaselines(projectId, touched, op === 'add' ? { add: [baseline] } : { remove: [baseline] });
          },
        });
      }
      bumpDataVersion();
      clearSelection();
      load();
    } catch (e: any) {
      addToast('error', e?.message || 'Bulk baseline update failed');
    }
  };

  const previewReparent = useCallback(
    async (parent: string | null, rePrefix: boolean) => {
      const res = await api.bulkReparentRequirements(projectId!, movingIds ?? [], parent, rePrefix, true);
      return res.renames ?? [];
    },
    [projectId, movingIds],
  );

  // A drop opens the same dialog the menu does, rather than moving straight
  // away: dragging must not be the one path to an id rewrite that skips the
  // warning. `pendingParent` seeds the dialog with the dropped-on row.
  const [pendingParent, setPendingParent] = useState<string | null | undefined>(undefined);
  const { sensors, draggingIds, overId, dropIsValid, isDragging, dndHandlers } = useTreeDrag({
    items: requirements,
    selectedIds,
    onDrop: (ids, parent) => { setMovingIds(ids); setPendingParent(parent); },
  });

  const confirmReparent = async (parent: string | null, rePrefix: boolean) => {
    const ids = movingIds ?? [];
    const res = await api.bulkReparentRequirements(projectId!, ids, parent, rePrefix);
    // A re-prefixed move cannot be undone: there is no rename endpoint, so the
    // old ids are gone. Undo the parentage only, and say so in the label.
    const renamed = (res.renames ?? []).length > 0;
    useUndoStore.getState().push({
      description: renamed
        ? `Move ${ids.length} requirement(s) (ids not restorable)`
        : `Move ${ids.length} requirement(s)`,
      undo: async () => {
        const byId = new Map(requirements.map((r) => [r.id, r]));
        for (const id of res.ids) {
          const original = byId.get(id);
          await api.bulkReparentRequirements(projectId!, [id], original?.parent ?? null, false);
        }
      },
      redo: async () => {
        await api.bulkReparentRequirements(projectId!, res.ids, parent, false);
      },
    });
    bumpGraphVersion();
    bumpDataVersion();
    clearSelection();
    load();
  };

  return (
    <div className="relative max-w-4xl mx-auto px-6 py-6 min-h-[50vh]">
      {loading && requirements.length === 0 && <LoadingSplash label="Loading requirements…" />}
      {truncation && <TruncationBanner info={truncation} />}
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Requirements</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {filtering ? `${matchCount} of ${requirements.length} requirements` : `${requirements.length} requirements`}
          </p>
        </div>
        {editMode && (
          <button onClick={() => setCreateIntent({ mode: 'blank' })} className="btn-primary">
            <Plus size={15} />
            <span className="hidden @sm:inline">New Requirement</span>
            <span className="@sm:hidden">New</span>
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm">
        {/* flex-wrap + min-w on the search: on a narrow pane the fixed-width
            selects fold onto extra rows instead of crushing the search box. */}
        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[180px]">
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
            {REQUIREMENT_TYPES.map((k) => (
              <option key={k} value={k}>{REQUIREMENT_TYPE_META[k].label}</option>
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
              <button className="text-xs text-primary hover:underline mt-2" onClick={() => setCreateIntent({ mode: 'blank' })}>
                Create the first one
              </button>
            )}
          </div>
        ) : (
          <>
            {editMode && rows.length > 0 && (
              // The whole row toggles, not just the 13px icon — the label sat
              // next to a checkbox and looked clickable while doing nothing.
              <div
                role="button"
                tabIndex={0}
                onClick={() => selectedIds.size === rows.length ? clearSelection() : selectAllVisible()}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectedIds.size === rows.length ? clearSelection() : selectAllVisible(); } }}
                className="flex items-center gap-2 px-3 py-2 border-b border-border/60 bg-muted/30 cursor-pointer hover:bg-muted/50"
              >
                <span className="shrink-0 mr-0.5">
                  {selectedIds.size === rows.length && rows.length > 0 ? (
                    <CheckSquare size={13} className="text-primary" />
                  ) : (
                    <Square size={13} className="text-muted-foreground/40" />
                  )}
                </span>
                <span className="text-[11px] text-muted-foreground">Select all</span>
              </div>
            )}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              {...dndHandlers}
            >
            {editMode && <TopLevelDropZone active={isDragging} isOver={overId === '__top_level__'} />}
            {rows.map(({ req, depth, childCount }) => {
            const TypeIcon = reqTypeIcon(req.type);
            const typeCls = reqTypeClass(req.type);
            const status = statusStyles[req.status] || statusStyles.proposed;
            const isCollapsed = collapsed.has(req.id);
            const dimByFilter = matchIds && !matchIds.has(req.id);
            return (
              <DropRow
                key={req.id}
                id={req.id}
                disabled={!editMode}
                isOver={overId === req.id}
                valid={dropIsValid}
              >
              <div
                onClick={() => navigate(`/project/${projectId}/requirements/${req.id}`)}
                className={`group flex items-center gap-2 pr-3 py-[7px] cursor-pointer transition-colors hover:bg-accent/40 ${dimByFilter ? 'opacity-45' : ''} ${draggingIds.includes(req.id) ? 'opacity-40' : ''}`}
                style={{ paddingLeft: `${12 + depth * 22}px` }}
              >
                {editMode && <DragGrip id={req.id} label={req.id} />}
                {/* Selection checkbox */}
                {editMode && (
                  <span className="shrink-0 mr-0.5" onClick={(e) => e.stopPropagation()}>
                    {selectedIds.has(req.id) ? (
                      <CheckSquare size={13} className="text-primary cursor-pointer" onClick={(e) => { e.stopPropagation(); toggleSelect(req.id, e); }} />
                    ) : (
                      <Square size={13} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={(e) => { e.stopPropagation(); toggleSelect(req.id, e); }} />
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

                <span className="font-mono text-[11px] text-muted-foreground shrink-0 w-auto @md:w-[4.8rem]">{req.id}</span>

                {/* min-w-0 (not shrink-0): on a narrow pane the name compresses
                    and truncates instead of pushing the row past the edge. */}
                <span
                  className={`text-[13px] truncate min-w-0 max-w-[55%] ${childCount > 0 ? 'font-semibold' : 'font-medium'} text-foreground`}
                  title={req.name || 'Untitled'}
                >
                  {req.name || 'Untitled'}
                </span>

                {/* Pane-width tiers: description only on wide panes; priority
                    chip and the status *word* drop next, leaving the dot. */}
                {req.description && (
                  <span className="text-xs text-muted-foreground/70 truncate flex-1 min-w-0 hidden @2xl:inline">
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
                    <span className={`badge border text-[10px] px-1.5 py-px hidden @sm:inline-flex ${priorityChips[req.priority]}`}>{req.priority}</span>
                  )}
                  <span className="flex items-center gap-1.5 w-auto @md:w-[5.6rem]" title={req.status}>
                    <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                    <span className="text-[11px] text-muted-foreground capitalize hidden @md:inline">{req.status}</span>
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
                      <button
                        onClick={(e) => { e.stopPropagation(); setCreateIntent({ mode: 'child', parent: req.id }); }}
                        className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Add child requirement"
                      >
                        <Plus size={13} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setCreateIntent({ mode: 'duplicate', source: req }); }}
                        className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Duplicate requirement"
                      >
                        <Copy size={13} />
                      </button>
                      {(
                        <button
                          onClick={(e) => { e.stopPropagation(); setMovingIds([req.id]); }}
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
              </DropRow>
            );
          })}
            <DragOverlay dropAnimation={null}>
              {draggingIds.length > 0 && (
                <div className="px-2 py-1 rounded-md bg-card border shadow-lg text-[11px] font-mono text-foreground">
                  {draggingIds.length === 1 ? draggingIds[0] : `${draggingIds.length} requirements`}
                </div>
              )}
            </DragOverlay>
            </DndContext>
          </>
        )}
      </div>

      {selectedIds.size > 0 && editMode && (
        <div className="sticky bottom-6 z-40 mx-auto w-fit max-w-full flex flex-wrap items-center justify-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <button onClick={() => setShowBulkEdit(true)} className="btn-primary text-xs">
            <SlidersHorizontal size={13} /> Bulk Edit
          </button>
          <select
            className="select text-xs py-1 w-36"
            title="Adds this baseline to the selection, leaving their other baselines in place"
            onChange={(e) => { if (e.target.value) { handleBulkBaseline(e.target.value, 'add'); e.target.value = ''; } }}
            value=""
          >
            <option value="">Add to baseline...</option>
            {projectBaselines.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <select
            className="select text-xs py-1 w-40"
            title="Removes only this baseline from the selection"
            onChange={(e) => { if (e.target.value) { handleBulkBaseline(e.target.value, 'remove'); e.target.value = ''; } }}
            value=""
          >
            <option value="">Remove from baseline...</option>
            {projectBaselines.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <button onClick={() => setMovingIds([...selectedIds])} className="btn-secondary text-xs">Move to...</button>
          <button onClick={handleBulkDelete} className="btn-danger text-xs">
            <Trash2 size={13} /> Delete
          </button>
          <button onClick={selectAllVisible} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearSelection} className="text-[10px] text-muted-foreground hover:text-foreground">
            <X size={13} />
          </button>
        </div>
      )}

      <ReparentDialog
        open={movingIds !== null}
        onClose={() => { setMovingIds(null); setPendingParent(undefined); }}
        items={requirements}
        movingIds={movingIds ?? []}
        initialParent={pendingParent}
        supportsRePrefix
        preview={previewReparent}
        onConfirm={confirmReparent}
      />

      <BulkEditModal
        open={showBulkEdit}
        onClose={() => setShowBulkEdit(false)}
        projectId={projectId!}
        selectedIds={[...selectedIds]}
        projectBaselines={projectBaselines}
        onSaved={() => { clearSelection(); load(); }}
        allReqs={requirements}
      />

      <CreateRequirementModal
        open={createIntent !== null}
        onClose={() => setCreateIntent(null)}
        projectId={projectId!}
        requirements={requirements}
        intent={createIntent ?? undefined}
        onCreated={load}
      />
    </div>
  );
}

function BulkEditModal({
  open, onClose, projectId, selectedIds, projectBaselines, onSaved, allReqs,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  selectedIds: string[];
  projectBaselines: string[];
  onSaved: () => void;
  allReqs: Requirement[];
}) {
  const INITIAL = {
    type: '',
    priority: '',
    status: '',
    rationale: '',
    source: '',
    allocated_to: '',
    baselines: null as string[] | null,
    normative: null as boolean | null,
    system_states: '',
    subject: '',
    needs: '',
    priorities: '',
    cascade_from: '',
    description: '',
  };

  const [form, setForm] = useState(INITIAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setForm(INITIAL); setError(''); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const hasChanges = Object.entries(form).some(([k, v]) => {
    const init = (INITIAL as any)[k];
    if (init === null) return v !== null;
    if (typeof init === 'boolean') return v !== null;
    return v !== '' && v !== init;
  });

  const buildUpdates = (): Record<string, any> => {
    const updates: Record<string, any> = {};
    if (form.type) updates.type = form.type;
    if (form.priority) updates.priority = form.priority;
    if (form.status) updates.status = form.status;
    if (form.rationale) updates.rationale = form.rationale;
    if (form.source) updates.source = form.source;
    if (form.allocated_to) updates.allocated_to = form.allocated_to;
    if (form.baselines !== null) updates.baselines = form.baselines;
    if (form.normative !== null) updates.normative = form.normative;
    if (form.system_states) updates.system_states = form.system_states.split(',').map(s => s.trim()).filter(Boolean);
    if (form.subject) updates.subject = form.subject;
    if (form.needs) updates.needs = form.needs.split(',').map(s => s.trim()).filter(Boolean);
    if (form.priorities) {
      const prio: Record<string, number> = {};
      for (const line of form.priorities.split('\n')) {
        const [k, v] = line.split(':').map(s => s.trim());
        if (k && v && !isNaN(Number(v))) prio[k] = Number(v);
      }
      if (Object.keys(prio).length > 0) updates.priorities = prio;
    }
    // '' means "leave unchanged"; the sentinel clears the field, which the old
    // free-text box could not express at all — you could opt into a cascade but
    // never out of one.
    if (form.cascade_from === '__none__') updates.cascade_from = null;
    else if (form.cascade_from) updates.cascade_from = form.cascade_from;
    if (form.description) updates.description = form.description;
    return updates;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const updates = buildUpdates();
    if (Object.keys(updates).length === 0) { setError('Select at least one field to update.'); return; }
    setBusy(true);
    setError('');
    try {
      const savedBefore: Record<string, Record<string, any>> = {};
      for (const id of selectedIds) {
        const r = allReqs.find((x) => x.id === id);
        if (r) savedBefore[id] = {};
        for (const k of Object.keys(updates)) {
          if (r) savedBefore[id][k] = (r as any)[k];
        }
      }
      await api.bulkUpdateRequirements(projectId, selectedIds, updates);
      useUndoStore.getState().push({
        description: `Update ${selectedIds.length} requirements`,
        undo: async () => {
          for (const [id, before] of Object.entries(savedBefore)) {
            await api.updateRequirement(projectId, id, before);
          }
        },
        redo: async () => { await api.bulkUpdateRequirements(projectId, selectedIds, updates); },
      });
      onSaved();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Bulk update failed');
    } finally {
      setBusy(false);
    }
  };

  const fieldCount = Object.entries(form).filter(([k, v]) => {
    const init = (INITIAL as any)[k];
    if (init === null) return v !== null;
    if (typeof init === 'boolean') return v !== null;
    return v !== '' && v !== init;
  }).length;

  return (
    <BodyPortal>
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px] flex items-start justify-center pt-[4vh] px-4"
          onClick={onClose}
        >
          <motion.form
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            onSubmit={handleSubmit}
            onClick={(e) => e.stopPropagation()}
            className="card w-full max-w-2xl p-6 shadow-xl max-h-[92vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between mb-5 sticky top-0 bg-card z-10 pb-3 border-b border-border/50">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Bulk Edit Requirements</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {selectedIds.length} requirement(s) selected — only filled-in fields will be changed
                </p>
              </div>
              <button type="button" onClick={onClose} className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-5">
              {/* Row 1: Type / Priority / Status */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="label">Type</label>
                  <select className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                    <option value="">No change</option>
                    {REQUIREMENT_TYPES.map((k) => <option key={k} value={k}>{REQUIREMENT_TYPE_META[k].label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Priority</label>
                  <select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                    <option value="">No change</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="label">Status</label>
                  <select className="select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                    <option value="">No change</option>
                    <option value="proposed">Proposed</option>
                    <option value="approved">Approved</option>
                    <option value="implemented">Implemented</option>
                    <option value="verified">Verified</option>
                    <option value="rejected">Rejected</option>
                    <option value="deprecated">Deprecated</option>
                  </select>
                </div>
              </div>

              {/* Row 2: Rationale / Source / Allocated To */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="label">Rationale</label>
                  <input className="input" placeholder="Why this requirement exists..." value={form.rationale}
                    onChange={(e) => setForm({ ...form, rationale: e.target.value })} />
                </div>
                <div>
                  <label className="label">Source</label>
                  <input className="input" placeholder="Stakeholder/document ref..." value={form.source}
                    onChange={(e) => setForm({ ...form, source: e.target.value })} />
                </div>
                <div>
                  <label className="label">Allocated To</label>
                  <input className="input" placeholder="System element..." value={form.allocated_to}
                    onChange={(e) => setForm({ ...form, allocated_to: e.target.value })} />
                </div>
              </div>

              {/* Row 4: Subject / Cascade From / Effort */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="label">Subject</label>
                  <input className="input font-mono text-xs" placeholder="e.g. WING" value={form.subject}
                    onChange={(e) => setForm({ ...form, subject: e.target.value })} />
                </div>
                <div>
                  <label className="label">Cascade From</label>
                  {/* Was a free-text id box. Setting this is not a label: the
                      master's name, description, priority, status and type
                      overwrite this requirement's on every future edit of the
                      master. A typo silently pointed at nothing; picking from
                      the list cannot. */}
                  <select
                    className="select font-mono text-xs"
                    value={form.cascade_from}
                    onChange={(e) => setForm({ ...form, cascade_from: e.target.value })}
                  >
                    <option value="">Leave unchanged</option>
                    <option value="__none__">None — break the cascade</option>
                    {allReqs
                      .filter((r) => !selectedIds.includes(r.id))
                      .map((r) => <option key={r.id} value={r.id}>{r.id} — {r.name}</option>)}
                  </select>
                </div>
              </div>

              {form.cascade_from && form.cascade_from !== '__none__' && (
                <div className="flex items-start gap-2 text-xs text-cs-orange bg-cs-orange/10 rounded-lg p-3">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                  <span>
                    The {selectedIds.length} selected requirement{selectedIds.length === 1 ? '' : 's'} will
                    be overwritten by <b className="font-mono">{form.cascade_from}</b> — its name, description,
                    priority, status and type replace theirs now and again every time it is edited.
                  </span>
                </div>
              )}

              {/* Row 5: System States / Coverage Needs */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">System States</label>
                  <input className="input font-mono text-xs" placeholder="takeoff, cruise, landing" value={form.system_states}
                    onChange={(e) => setForm({ ...form, system_states: e.target.value })} />
                  <div className="text-[10px] text-muted-foreground mt-0.5">Comma-separated OOSEM modes</div>
                </div>
                <div>
                  <label className="label">Coverage Needs</label>
                  <input className="input font-mono text-xs" placeholder="design, verification_case" value={form.needs}
                    onChange={(e) => setForm({ ...form, needs: e.target.value })} />
                  <div className="text-[10px] text-muted-foreground mt-0.5">Comma-separated artifact types</div>
                </div>
              </div>

              {/* Stakeholder Priorities */}
              <div>
                <label className="label">Stakeholder Priorities</label>
                <textarea
                  className="input font-mono text-xs h-16 resize-none"
                  placeholder="development: 5\ncustomers: 8\nsafety: 10"
                  value={form.priorities}
                  onChange={(e) => setForm({ ...form, priorities: e.target.value })}
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">One per line, format: stakeholder: score</div>
              </div>

              {/* Description */}
              <div>
                <label className="label">Description</label>
                <RichTextEditor
                  content={form.description}
                  onChange={(html) => setForm({ ...form, description: html })}
                  onBlur={() => {}}
                  disabled={false}
                  placeholder="Write a requirement description…"
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">Overwrites the description on every selected requirement</div>
              </div>

              {/* Booleans */}
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <span className="text-muted-foreground">Normative:</span>
                  <select className="select text-xs py-0.5 w-24" value={form.normative === null ? '' : String(form.normative)}
                    onChange={(e) => {
                      const v = e.target.value;
                      setForm({ ...form, normative: v === '' ? null : v === 'true' });
                    }}>
                    <option value="">No change</option>
                    <option value="true">True</option>
                    <option value="false">False</option>
                  </select>
                </label>
              </div>

              {/* Baselines */}
              {projectBaselines.length > 0 && (
                <div>
                  <label className="label">Baselines</label>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {projectBaselines.map((b) => {
                      const active = (form.baselines || []).includes(b);
                      const anySet = form.baselines !== null;
                      return (
                        <button
                          key={b}
                          type="button"
                          onClick={() => {
                            const current = anySet ? [...(form.baselines || [])] : [...(projectBaselines)];
                            const next = active ? current.filter(x => x !== b) : [...current, b];
                            setForm({ ...form, baselines: next });
                          }}
                          className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                            active
                              ? 'bg-primary/15 text-primary border-primary/30'
                              : anySet ? 'bg-muted text-muted-foreground border-transparent hover:border-primary/20' : 'bg-muted/50 text-muted-foreground/50 border-transparent'
                          }`}
                        >
                          {b}
                        </button>
                      );
                    })}
                    {form.baselines !== null && (
                      <button
                        type="button"
                        onClick={() => setForm({ ...form, baselines: null })}
                        className="text-[10px] text-muted-foreground hover:text-foreground underline ml-1"
                      >
                        clear selection
                      </button>
                    )}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    Click a baseline to toggle it. When any baseline is set, the new set replaces all existing baselines.
                  </div>
                </div>
              )}

              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>

            <div className="flex justify-between items-center mt-6 pt-4 border-t border-border/50">
              <span className="text-[11px] text-muted-foreground">{fieldCount > 0 ? `${fieldCount} field(s) will be updated` : 'No fields selected'}</span>
              <div className="flex gap-2">
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button
                  type="submit"
                  disabled={busy || !hasChanges}
                  className="btn-primary"
                >
                  {busy ? `Updating ${selectedIds.length}…` : `Update ${selectedIds.length} requirement(s)`}
                </button>
              </div>
            </div>
          </motion.form>
        </motion.div>
      )}
    </AnimatePresence>
    </BodyPortal>
  );
}
