import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ChevronRight, Boxes, Square, CheckSquare, Trash2, X, Search } from 'lucide-react';
import { api, COMPONENT_TYPES, type Component, type ComponentTreeNode } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { COMPONENT_TYPE_META } from '../components/entities';
import { HelpTip } from '../components/HelpTip';

const EMPTY_DRAFT = { id: '', name: '', type: 'assembly', parent: '' };

export default function ComponentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkParent, setBulkParent] = useState('');
  const dataVersion = useStore((s) => s.dataVersion);

  const [components, setComponents] = useState<Component[]>([]);
  const [tree, setTree] = useState<ComponentTreeNode[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [error, setError] = useState('');

  const load = () => {
    if (!projectId) return;
    Promise.all([api.listComponents(projectId), api.getComponentTree(projectId)])
      .then(([list, t]) => { setComponents(list); setTree(t); })
      .catch((e) => setError(e.message));
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

  const filtering = !!(search || filterType);
  const filteredCount = filterMatchIds ? filterMatchIds.size : components.length;

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
      setShowCreate(false);
      setDraft(EMPTY_DRAFT);
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to create component');
    }
  };

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleComponent = (id: string) =>
    setSelectedIds((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const clearComponentSelection = () => setSelectedIds(new Set());
  const selectAllComponents = () => setSelectedIds(new Set(components.map((c) => c.id)));

  const handleBulkReparent = async () => {
    if (!bulkParent.trim()) return;
    await api.bulkReparentComponents(projectId!, [...selectedIds], bulkParent.trim());
    clearComponentSelection();
    load();
    setBulkParent('');
  };

  const handleBulkDelete = async () => {
    if (!projectId) return;
    if (!confirm(`Delete ${selectedIds.size} component(s)?`)) return;
    await api.bulkDeleteComponents(projectId, [...selectedIds]);
    clearComponentSelection();
    load();
  };

  const renderNode = (node: ComponentTreeNode, depth: number): React.ReactNode => {
    const hasKids = node.children.length > 0;
    const isCollapsed = collapsed.has(node.id);
    const typeMeta = COMPONENT_TYPE_META[node.type] || COMPONENT_TYPE_META.assembly;
    const TypeIcon = typeMeta.icon;

    const subtreeMatches = (n: ComponentTreeNode): boolean => {
      if (!filterMatchIds) return true;
      if (filterMatchIds.has(n.id)) return true;
      return n.children.some(subtreeMatches);
    };
    if (filtering && !subtreeMatches(node)) return null;
    return (
      <div key={node.id}>
        <div
          id={`entity-${node.id}`}
          onClick={() => navigate(`/project/${projectId}/components/${node.id}`)}
          className="flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-colors hover:bg-accent"
          style={{ paddingLeft: depth * 20 + 8 }}
        >
          {editable && (
            <span className="shrink-0" onClick={(e) => e.stopPropagation()}>
              {selectedIds.has(node.id) ? (
                <CheckSquare size={13} className="text-primary cursor-pointer" onClick={() => toggleComponent(node.id)} />
              ) : (
                <Square size={13} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={() => toggleComponent(node.id)} />
              )}
            </span>
          )}
          {hasKids ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggle(node.id); }}
              className="p-0.5 rounded hover:bg-accent text-muted-foreground shrink-0"
              title={isCollapsed ? 'Expand' : 'Collapse'}
            >
              <ChevronRight size={14} className={`transition-transform ${isCollapsed ? '' : 'rotate-90'}`} />
            </button>
          ) : (
            <span className="w-[22px] shrink-0" />
          )}
          <TypeIcon size={14} className={`${typeMeta.cls} shrink-0`} />
          <span className="font-mono text-xs text-muted-foreground shrink-0">{node.id}</span>
          <span className="text-sm text-card-foreground truncate">{node.name || 'Untitled'}</span>
          {node.quantity > 1 && <span className="text-xs text-muted-foreground shrink-0">×{node.quantity}</span>}
          {node.satisfies.length > 0 && (
            <span className="ml-auto text-[10px] text-muted-foreground shrink-0" title="Requirements satisfied">
              {node.satisfies.length} requirements
            </span>
          )}
        </div>
        {hasKids && !isCollapsed && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto p-8">
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

      {selectedIds.size > 0 && editable && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <select
            className="select text-xs py-1 w-32"
            onChange={async (e) => { if (e.target.value) { await api.bulkUpdateComponents(projectId!, [...selectedIds], { type: e.target.value }); clearComponentSelection(); load(); } }}
            value=""
          >
            <option value="">Set type...</option>
            {COMPONENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="input text-xs w-20" placeholder="Parent ID" value={bulkParent} onChange={(e) => setBulkParent(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleBulkReparent(); }} />
          <button onClick={handleBulkReparent} className="btn-secondary text-xs" disabled={!bulkParent.trim()}>Move</button>
          <button onClick={handleBulkDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
          <button onClick={selectAllComponents} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearComponentSelection} className="text-[10px] text-muted-foreground hover:text-foreground"><X size={13} /></button>
        </div>
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
                <label className="label">ID</label>
                <input className="input font-mono" placeholder="C-001" value={draft.id}
                  onChange={(e) => setDraft({ ...draft, id: e.target.value })} autoFocus />
              </div>
              <div className="flex-1 min-w-[160px]">
                <label className="label">Name</label>
                <input className="input" placeholder="Fuel pump" value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
              <div className="w-36">
                <label className="label">Type</label>
                <select className="input" value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>
                  {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="w-44">
                <label className="label">Parent</label>
                <select className="input" value={draft.parent} onChange={(e) => setDraft({ ...draft, parent: e.target.value })}>
                  <option value="">(top level)</option>
                  {components.map((c) => <option key={c.id} value={c.id}>{c.id} — {c.name}</option>)}
                </select>
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
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded border bg-muted text-[10px] font-mono text-muted-foreground pointer-events-none">/</kbd>
            )}
          </div>
          <select className="select w-36 h-9 text-xs" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">All types</option>
            {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}

      {components.length === 0 && !filtering ? (
        <div className="card p-12 text-center">
          <Boxes size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No components yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Components describe what the system <i>is</i>, and map onto the requirements they satisfy.
          </p>
        </div>
      ) : components.length > 0 && filteredCount === 0 ? (
        <div className="card p-12 text-center">
          <Boxes size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No components match your filters.</p>
          <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterType(''); }}>Clear filters</button>
        </div>
      ) : (
        <div className="card p-2 flex-1 min-w-[280px]">
          {tree.map((node) => renderNode(node, 0))}
        </div>
      )}
    </div>
  );
}
