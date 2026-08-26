import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ChevronRight, Boxes, Square, CheckSquare, Trash2, X, Search, Eye, EyeOff, Download, Copy } from 'lucide-react';
import { api, COMPONENT_TYPES, getTruncationInfo, type Component, type ComponentTreeNode, type TruncationInfo } from '../api/client';
import { useStore } from '../store';
import { useHoveredEntityBus, useHoverHighlight } from '../components/Layout';
import { componentsSatisfyingRequirement } from '../lib/crossHighlight';
import { useAuthStore } from '../store/auth';
import { COMPONENT_TYPE_META } from '../components/entities';
import { HelpTip } from '../components/HelpTip';
import { useToasts } from '../components/Toast';
import TruncationBanner from '../components/TruncationBanner';
import { effectiveHiddenComponents, hiddenAncestors } from '../lib/graphFilters';
import { rollupQuantities } from '../lib/quantityRollup';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useBulkActions } from '../hooks/useBulkActions';
import { useUndoStore } from '../store/undo';
import ReparentDialog from '../components/ReparentDialog';
import BulkActionBar from '../components/BulkActionBar';
import { DndContext, DragOverlay } from '@dnd-kit/core';
import { useTreeDrag, TOP_LEVEL_ID } from '../hooks/useTreeDrag';
import { DropRow, DragGrip, TopLevelDropZone } from '../components/TreeDragRow';
import LoadingSplash from '../components/LoadingSplash';
import EmptyState from '../components/EmptyState';

const EMPTY_DRAFT = { id: '', name: '', type: 'assembly', parent: '' };

export default function ComponentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canEdit());
  // Rows the reparent dialog is moving. Components are never renamed, so
  // there is no re-prefix step — only the cycle-safe parent choice.
  const [movingIds, setMovingIds] = useState<string[] | null>(null);
  const dataVersion = useStore((s) => s.dataVersion);
  const hiddenComponents = useStore((s) => s.hiddenComponents);
  const toggleHiddenComponent = useStore((s) => s.toggleHiddenComponent);
  const setHiddenComponents = useStore((s) => s.setHiddenComponents);

  const [components, setComponents] = useState<Component[]>([]);
  const [tree, setTree] = useState<ComponentTreeNode[]>([]);
  // Persisted per project: navigating to a component's detail (or off the
  // page entirely) and back used to reset the collapsed tree and any filter,
  // undoing exactly the configuration the operator was there to set up.
  const pk = (field: string) => (projectId ? `rt-components-${field}-${projectId}` : null);
  const [collapsed, setCollapsed] = usePersistedState<Set<string>>(pk('collapsed'), new Set(), setCodec<string>());
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterType, setFilterType] = usePersistedState(pk('filter-type'), '');
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [error, setError] = useState('');
  const [truncation, setTruncation] = useState<TruncationInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToasts();
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const treeContainerRef = useRef<HTMLDivElement>(null);

  const hasUnsavedChanges = showCreate && !!(draft.id.trim() || draft.name.trim() || draft.parent);

  // Cross-highlight with the canvas. Hovering a component row lights the
  // requirements it satisfies on the canvas; hovering a canvas node lights the
  // component(s) that satisfy it here. Applied imperatively so a hover never
  // re-renders the whole tree.
  const { set: setHoveredEntity } = useHoveredEntityBus();
  const litRowRef = useRef<Element[]>([]);
  useHoverHighlight((hovered) => {
    for (const el of litRowRef.current) el.classList.remove('rt-cross-hover');
    litRowRef.current = [];
    if (hovered?.kind === 'requirement') {
      for (const cid of componentsSatisfyingRequirement(hovered.id, components)) {
        const el = document.getElementById(`entity-${cid}`);
        if (el) { el.classList.add('rt-cross-hover'); litRowRef.current.push(el); }
      }
    }
  });

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsavedChanges]);

  const load = () => {
    if (!projectId) return;
    Promise.all([api.listComponents(projectId), api.getComponentTree(projectId)])
      .then(([list, t]) => { setComponents(list); setTree(t); setTruncation(getTruncationInfo('components')); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId, dataVersion]);

  const filterMatchIds = useMemo(() => {
    if (!search && !filterType) return null;
    const q = search.toLowerCase();
    const ids = new Set<string>();
    for (const c of components) {
      if (filterType && c.type !== filterType) continue;
      if (q) {
        const hay = `${c.id} ${c.name || ''}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      ids.add(c.id);
    }
    return ids;
  }, [components, search, filterType]);

  /** Clear every ancestor hiding `id`, in one update rather than a toggle each. */
  const revealComponent = (id: string) => {
    const ancestors = hiddenAncestors(components, hiddenComponents, id);
    if (ancestors.length === 0) return;
    const drop = new Set(ancestors);
    setHiddenComponents(hiddenComponents.filter((h) => !drop.has(h)));
  };

  const effectiveHidden = useMemo(
    () => effectiveHiddenComponents(components, hiddenComponents),
    [components, hiddenComponents],
  );

  // Effective (rolled-up) quantity per component, computed once for the list
  // rather than per row. Own quantity × every ancestor's, up to the root.
  const quantityRollup = useMemo(() => rollupQuantities(components), [components]);

  const filtering = !!(search || filterType);
  const filteredCount = filterMatchIds ? filterMatchIds.size : components.length;

  const flatNodes = useMemo(() => {
    const result: { id: string; depth: number }[] = [];
    const walk = (nodes: ComponentTreeNode[], depth: number) => {
      for (const n of nodes) {
        if (filtering) {
          if (filterMatchIds?.has(n.id) || n.children.some((c) => {
            const check = (x: ComponentTreeNode): boolean => filterMatchIds?.has(x.id) || x.children.some(check);
            return check(c);
          })) {
            result.push({ id: n.id, depth });
            if (!collapsed.has(n.id)) walk(n.children, depth + 1);
          }
        } else {
          result.push({ id: n.id, depth });
          if (!collapsed.has(n.id)) walk(n.children, depth + 1);
        }
      }
    };
    walk(tree, 0);
    return result;
  }, [tree, collapsed, filtering, filterMatchIds]);

  const handleTreeKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (flatNodes.length === 0) return;
    let next = focusedIndex;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        next = Math.min(next + 1, flatNodes.length - 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        next = Math.max(next - 1, 0);
        break;
      case 'ArrowRight': {
        e.preventDefault();
        const id = flatNodes[next]?.id;
        if (id && collapsed.has(id)) {
          setCollapsed((prev) => { const s = new Set(prev); s.delete(id); return s; });
        }
        return;
      }
      case 'ArrowLeft': {
        e.preventDefault();
        const id = flatNodes[next]?.id;
        if (id && !collapsed.has(id)) {
          setCollapsed((prev) => { const s = new Set(prev); s.add(id); return s; });
        }
        return;
      }
      case 'Enter':
        e.preventDefault();
        if (next >= 0 && next < flatNodes.length) {
          navigate(`/project/${projectId}/components/${flatNodes[next].id}`);
        }
        return;
      default:
        return;
    }

    if (next !== focusedIndex) {
      setFocusedIndex(next);
      const target = document.getElementById(`entity-${flatNodes[next]?.id}`);
      target?.scrollIntoView({ block: 'nearest' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flatNodes, focusedIndex, collapsed, navigate, projectId]);

  const handleExportBom = async () => {
    if (!projectId) return;
    try {
      const url = api.exportBom(projectId);
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${projectId}-bom.csv`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    } catch (err: any) {
      addToast('error', err.message || 'Export failed');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !draft.id.trim()) return;
    setError('');
    try {
      await api.createComponent(projectId, {
        id: draft.id.trim(),
        name: draft.name.trim(),
        type: draft.type,
        parent: draft.parent || null,
      });
      addToast('success', `Component ${draft.id.trim()} created`);
      setShowCreate(false);
      setDraft(EMPTY_DRAFT);
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to create component');
    }
  };

  const handleDuplicate = async (src: Component) => {
    if (!projectId) return;
    const existing = new Set(components.map((c) => c.id));
    // Numbered from 1, not bare `-copy`, because the project's naming
    // standard is enforced on create and a numeric-suffix scheme refuses an
    // id that does not end in a digit. `-copy` was silently rejected with a
    // 422 the moment enforcement went in, which broke Duplicate outright.
    let n = 1;
    let id = `${src.id}-copy${n}`;
    while (existing.has(id)) { id = `${src.id}-copy${++n}`; }
    try {
      await api.createComponent(projectId, {
        id,
        name: `${src.name} (copy)`,
        type: src.type,
        parent: src.parent,
        description: src.description,
        part_number: src.part_number,
        supplier: src.supplier,
        quantity: src.quantity,
      });
      addToast('success', `Component ${id} created`);
      load();
    } catch (err: any) {
      addToast('error', err.message || 'Failed to duplicate component');
    }
  };

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // `flatNodes` is the tree as actually displayed — filtered and with collapsed
  // branches omitted — which is the only ordering a Shift range may span.
  const { selectedIds, select: toggleComponent, setSelectedIds, clear: clearComponentSelection } =
    useRangeSelection(useMemo(() => flatNodes.map((n) => n.id), [flatNodes]));
  const selectAllComponents = () => setSelectedIds(new Set(components.map((c) => c.id)));

  const { runBulkDelete, runBulkUpdate } = useBulkActions({
    clearSelection: clearComponentSelection,
    reload: load,
  });

  // These three bulk handlers had no error handling at all. A reparent that
  // would create a cycle, or a delete refused because the components are
  // referenced, rejected as an unhandled promise: no message, and the
  // selection-clearing and reload below never ran, so the page looked frozen
  // rather than refused.
  const [pendingParent, setPendingParent] = useState<string | null | undefined>(undefined);
  const { sensors, draggingIds, overId, dropIsValid, isDragging, dndHandlers, collisionDetection } = useTreeDrag({
    items: components,
    selectedIds,
    onDrop: (ids, parent) => { setMovingIds(ids); setPendingParent(parent); },
  });

  const confirmReparent = async (parent: string | null) => {
    const ids = movingIds ?? [];
    const before = new Map(components.map((c) => [c.id, c.parent ?? null]));
    await api.bulkReparentComponents(projectId!, ids, parent);
    useUndoStore.getState().push({
      description: `Move ${ids.length} component(s)`,
      undo: async () => {
        // Per id: they may not have shared a parent before the move.
        for (const id of ids) {
          await api.bulkReparentComponents(projectId!, [id], before.get(id) ?? null);
        }
      },
      redo: async () => { await api.bulkReparentComponents(projectId!, ids, parent); },
    });
    clearComponentSelection();
    load();
  };

  const handleBulkDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const saved = components.filter((c) => selectedIds.has(c.id)).map((c) => ({ ...c }));
    await runBulkDelete({
      noun: 'component',
      ids,
      saved,
      idOf: (c) => c.id,
      remove: (idsToRemove) => api.bulkDeleteComponents(projectId, idsToRemove),
      recreate: (item) => api.createComponent(projectId, item),
    });
  };

  const handleBulkSetType = async (type: string) => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const before = Object.fromEntries(
      components.filter((c) => selectedIds.has(c.id)).map((c) => [c.id, { type: c.type }]),
    );
    await runBulkUpdate({
      label: `${type} on ${ids.length} components`,
      noun: 'component',
      ids,
      before,
      updates: { type },
      apply: (updateIds, updates) => api.bulkUpdateComponents(projectId, updateIds, updates),
      applyOne: (id, updates) => api.updateComponent(projectId, id, updates),
    });
  };

  const renderNode = (node: ComponentTreeNode, depth: number): React.ReactNode => {
    const hasKids = node.children.length > 0;
    const isCollapsed = collapsed.has(node.id);
    const typeMeta = COMPONENT_TYPE_META[node.type] || COMPONENT_TYPE_META.assembly;
    const TypeIcon = typeMeta.icon;
    const inherited = effectiveHidden.has(node.id) && !hiddenComponents.includes(node.id);

    const subtreeMatches = (n: ComponentTreeNode): boolean => {
      if (!filterMatchIds) return true;
      if (filterMatchIds.has(n.id)) return true;
      return n.children.some(subtreeMatches);
    };
    if (filtering && !subtreeMatches(node)) return null;
    const isFocused = flatNodes[focusedIndex]?.id === node.id;
    const comp = components.find((c) => c.id === node.id);
    const ownQty = node.quantity > 0 ? node.quantity : 1;
    const effQty = quantityRollup.get(node.id) ?? ownQty;
    const qtyLabel = [ownQty > 1 ? `×${ownQty}` : '', effQty !== ownQty ? `(${effQty}×)` : '']
      .filter(Boolean)
      .join(' ');
    return (
      <div key={node.id}>
        <DropRow id={node.id} disabled={!editable} isOver={overId === node.id} valid={dropIsValid}>
        <div
          id={`entity-${node.id}`}
          role="treeitem"
          tabIndex={-1}
          onClick={() => navigate(`/project/${projectId}/components/${node.id}`)}
          onMouseEnter={() => setHoveredEntity({ kind: 'component', id: node.id })}
          onMouseLeave={() => setHoveredEntity(null)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate(`/project/${projectId}/components/${node.id}`);
            }
          }}
          className={`group rt-row flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-colors hover:bg-accent ${isFocused ? 'bg-accent ring-1 ring-ring/30' : ''} ${draggingIds.includes(node.id) ? 'opacity-40' : ''}`}
        >
          {/* Left cell. The tree indent lives here, not on the row, so the
              quantity, satisfies and action columns to its right start at the
              same x on every row whatever its depth. */}
          <div className="flex items-center gap-2 min-w-0 flex-1" style={{ paddingLeft: depth * 20 }}>
          {editable && <DragGrip id={node.id} label={node.id} />}
          {editable && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); toggleComponent(node.id, e); }}
              aria-pressed={selectedIds.has(node.id)}
              aria-label="Select component"
              className="shrink-0 cursor-pointer"
            >
              {selectedIds.has(node.id) ? (
                <CheckSquare size={13} className="text-primary" />
              ) : (
                <Square size={13} className="text-muted-foreground/40 hover:text-muted-foreground" />
              )}
            </button>
          )}
          {hasKids ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggle(node.id); }}
              className="p-0.5 rounded-md hover:bg-accent text-muted-foreground shrink-0"
              title={isCollapsed ? 'Expand' : 'Collapse'}
            >
              <ChevronRight size={14} className={`transition-transform ${isCollapsed ? '' : 'rotate-90'}`} />
            </button>
          ) : (
            <span className="w-[22px] shrink-0" />
          )}
          <TypeIcon size={14} className={`${typeMeta.cls} shrink-0`} />
          <span className="font-mono text-xs text-muted-foreground shrink-0">{node.id}</span>
          <span className="text-sm text-card-foreground truncate flex-1 min-w-0">{node.name || 'Untitled'}</span>
          </div>
          {/* Fixed-width slots, rendered whether or not they carry content, so
              a row without a quantity or a satisfies count does not pull the
              rows around it out of column. */}
          <span
            className="w-14 shrink-0 text-right text-xs text-muted-foreground"
            title={qtyLabel && effQty !== ownQty ? `${effQty}× in the build (${ownQty}× in this row)` : undefined}
          >
            {qtyLabel}
          </span>
          <span className="w-[5.5rem] shrink-0 text-right text-3xs text-muted-foreground">
            {node.satisfies.length > 0 ? `satisfies ${node.satisfies.length}` : ''}
          </span>
          {/* The trailing controls sit in a shrink-0 cluster so they hold a
              stable column however many optional badges a row carries. Hover-
              revealed buttons use opacity (not `hidden`), so they keep their
              space and the column does not shift on hover. */}
          <div className="flex items-center shrink-0">
            {editable && comp && (
              <button
                onClick={(e) => { e.stopPropagation(); handleDuplicate(comp); }}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Duplicate component"
              >
                <Copy size={13} />
              </button>
            )}
            {editable && (
              <button
                onClick={(e) => { e.stopPropagation(); setDraft({ ...EMPTY_DRAFT, parent: node.id }); setShowCreate(true); }}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label={`Add child component to ${node.id}`}
                title="Add child component"
              >
                <Plus size={13} />
              </button>
            )}
            {/* An inherited-hidden node used to render this button disabled, which
                left no way back: nothing is set on the node itself, so its own
                toggle is a no-op, and the only control that would reveal it was
                on an ancestor the user had to go and find. Clicking now clears
                whichever ancestors are doing the hiding. */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (inherited) revealComponent(node.id);
                else toggleHiddenComponent(node.id);
              }}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
              title={
                inherited
                  ? `Hidden by ${hiddenAncestors(components, hiddenComponents, node.id).join(', ')} — click to show`
                  : effectiveHidden.has(node.id) ? 'Hidden in graph' : 'Shown in graph'
              }
            >
              {effectiveHidden.has(node.id) ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>
        </DropRow>
        {hasKids && !isCollapsed && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="relative max-w-6xl mx-auto p-8">
      {loading && components.length === 0 && <LoadingSplash label="Loading components…" />}
      {truncation && <TruncationBanner info={truncation} />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Components</h1>
          <HelpTip>Components represent the physical design — what the system IS. Each component can satisfy requirements and carry numeric parameters for budget rollups (e.g. mass, current draw). Click a component to open its detail page.</HelpTip>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filteredCount} of ${components.length} components` : `${components.length} components`} — the synthesised design
          </p>
        </div>
        {editable && (
          <button onClick={() => { setShowCreate((s) => !s); setError(''); }} className="btn-primary">
            <Plus size={16} /> New Component
          </button>
      )}

      <ReparentDialog
        open={movingIds !== null}
        onClose={() => { setMovingIds(null); setPendingParent(undefined); }}
        items={components}
        movingIds={movingIds ?? []}
        initialParent={pendingParent}
        onConfirm={confirmReparent}
      />

      {selectedIds.size > 0 && editable && (
        <BulkActionBar
          count={selectedIds.size}
          onSelectAll={selectAllComponents}
          onClear={clearComponentSelection}
        >
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkSetType(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set type...</option>
            {COMPONENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <button onClick={() => setMovingIds([...selectedIds])} className="btn-secondary text-xs">Move to...</button>
          <button onClick={handleBulkDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
      <AnimatePresence>
        {showCreate && (
          <motion.form
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate}
            className="card p-4 mb-4 overflow-hidden"
          >
            <div className="flex items-end gap-3 flex-wrap">
              <div className="w-36">
                <label className="label">ID <input className="input font-mono" placeholder="C-001" value={draft.id}
                  onChange={(e) => setDraft({ ...draft, id: e.target.value })} /></label>
              </div>
              <div className="flex-1 min-w-[160px]">
                <label className="label">Name <input className="input" placeholder="Fuel pump" value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
              </div>
              <div className="w-36">
                <label className="label">Type <select className="select" value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>
                  {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select></label>
              </div>
              <div className="w-44">
                <label className="label">Parent component <select className="select" value={draft.parent} onChange={(e) => setDraft({ ...draft, parent: e.target.value })}>
                  <option value="">(top level)</option>
                  {/* Type in the label: component names routinely match
                      requirement group names — the seeded project has a
                      component and a requirement both called "Wing Assembly" —
                      so a bare name here reads as a requirement group. */}
                  {components.map((c) => <option key={c.id} value={c.id}>{c.id} — {c.name} ({c.type})</option>)}
                </select></label>
              </div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="input pl-9 pr-14 h-9"
              placeholder="Search components…"
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
          <select className="select w-36 h-9 text-xs" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">All types</option>
            {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button
            className="btn-secondary text-xs h-9"
            title="Download an indented bill of materials (CSV)"
            disabled={components.length === 0}
            onClick={handleExportBom}
          >
            <Download size={14} /> Export BOM
          </button>
        </div>
      </div>

      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}

      {components.length === 0 && !filtering ? (
        <EmptyState
          icon={Boxes}
          title="No components yet"
          hint="Components describe what the system is, and map onto the requirements they satisfy."
          action={editable ? { label: 'New Component', onClick: () => { setShowCreate((s) => !s); setError(''); } } : undefined}
        />
      ) : components.length > 0 && filteredCount === 0 ? (
        <EmptyState icon={Boxes} title="No components match your filters.">
          <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterType(''); }}>Clear filters</button>
        </EmptyState>
      ) : (
        <div className="card p-2 flex-1 min-w-[280px]" role="tree" tabIndex={0} ref={treeContainerRef} onKeyDown={handleTreeKeyDown}>
          <DndContext sensors={sensors} collisionDetection={collisionDetection} {...dndHandlers}>
            {editable && <TopLevelDropZone active={isDragging} isOver={overId === TOP_LEVEL_ID} />}
            {tree.map((node) => renderNode(node, 0))}
            <DragOverlay dropAnimation={null}>
              {draggingIds.length > 0 && (
                <div className="px-2 py-1 rounded-md bg-card border shadow-lg text-2xs font-mono text-foreground">
                  {draggingIds.length === 1 ? draggingIds[0] : `${draggingIds.length} components`}
                </div>
              )}
            </DragOverlay>
          </DndContext>
        </div>
      )}
    </div>
  );
}
