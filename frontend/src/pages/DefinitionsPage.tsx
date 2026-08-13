import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Sigma, Boxes, Trash2, X, Search, Edit3, ChevronDown, Square, CheckSquare } from 'lucide-react';
import { api, type Definition } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useToasts } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import { useListSelection } from '../hooks/useListSelection';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';

/**
 * Reusable SysML v2-style constraint and calc definitions.
 *
 * These had full CRUD, client methods and export coverage but no page: a
 * requirement could bind `constraint_def: MassBudget` with nothing in the UI
 * saying what MassBudget computes. The expression is the substance here, so it
 * is rendered in the mono style the parametrics card uses rather than as plain
 * prose.
 *
 * Deliberately no client-side evaluation or validation of `expr` — the backend
 * owns the solver, and a half-implemented parser here that disagreed with it
 * would be worse than none.
 */

const EMPTY = {
  id: '', type: 'constraint' as 'constraint' | 'calc', name: '',
  parameters: '', expr: '', unit: '', doc: '',
};

export default function DefinitionsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const editable = useAuthStore((s) => s.canEdit());
  const dataVersion = useStore((s) => s.dataVersion);
  const { addToast } = useToasts();
  const showConfirm = useConfirm();
  const [defs, setDefs] = useState<Definition[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const pk = (field: string) => (projectId ? `rt-definitions-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [expanded, setExpanded] = usePersistedState<Set<string>>(pk('expanded'), new Set(), setCodec<string>());
  const searchRef = useRef<HTMLInputElement>(null);

  const load = () => {
    if (!projectId) return;
    api.listDefinitions(projectId).then(setDefs).catch(() => setDefs([]))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId, dataVersion]);

  const filtered = useMemo(() => {
    if (!search) return defs;
    const q = search.toLowerCase();
    return defs.filter((d) =>
      d.id.toLowerCase().includes(q)
      || (d.name || '').toLowerCase().includes(q)
      || d.expr.toLowerCase().includes(q));
  }, [defs, search]);
  const filtering = !!search;

  const focusId = useFocusedEntity(defs.length > 0, useCallback(() => {}, []));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !editable || !draft.id.trim() || !draft.expr.trim()) return;
    const payload: Definition = {
      id: draft.id.trim(),
      type: draft.type,
      name: draft.name.trim(),
      parameters: draft.parameters.split(',').map((s) => s.trim()).filter(Boolean),
      expr: draft.expr.trim(),
      unit: draft.unit.trim(),
      doc: draft.doc.trim(),
    };
    try {
      if (editingId) {
        const { id: _id, ...rest } = payload;
        await api.updateDefinition(projectId, editingId, rest);
        addToast('success', `Definition ${editingId} updated`);
      } else {
        await api.createDefinition(projectId, payload);
        addToast('success', `Definition ${payload.id} created`);
      }
      setShowCreate(false);
      setEditingId(null);
      setDraft(EMPTY);
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save definition');
    }
  };

  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const openEdit = (d: Definition) => {
    setDraft({
      id: d.id, type: d.type, name: d.name || '',
      parameters: (d.parameters || []).join(', '),
      expr: d.expr, unit: d.unit || '', doc: d.doc || '',
    });
    setEditingId(d.id);
    setShowCreate(true);
  };

  const handleDelete = async (id: string) => {
    if (!projectId) return;
    const ok = await showConfirm(`Delete definition ${id}?`, 'Delete Definition', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      await api.deleteDefinition(projectId, id);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Delete failed');
      return;
    }
    addToast('success', `Definition ${id} deleted`);
    load();
  };

  // `filtered` is the list as displayed, which is the only ordering a
  // Shift range may span.
  const { selectedIds, select: toggleSelect, setSelectedIds } =
    useRangeSelection(useMemo(() => filtered.map((d) => d.id), [filtered]));
  const clearSelection = () => setSelectedIds(new Set());
  const selectAll = () => setSelectedIds(new Set(filtered.map((d) => d.id)));

  const { runBulkDelete } = useBulkActions({
    clearSelection,
    reload: load,
  });

  const handleBulkDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const saved = defs.filter((d) => selectedIds.has(d.id)).map((d) => ({ ...d }));
    await runBulkDelete({
      noun: 'definition',
      ids,
      saved,
      idOf: (d) => d.id,
      remove: (idsToRemove) => api.bulkDeleteDefinitions(projectId, idsToRemove),
      recreate: (item) => api.createDefinition(projectId, item),
    });
  };

  const { focusId: selectedId, onListDown, onListUp, onListOpen, onListEscape } = useListSelection(
    useMemo(() => filtered.map((d) => d.id), [filtered]),
    (id) => { const d = defs.find((x) => x.id === id); if (d) openEdit(d); },
  );

  useKeyboardShortcuts(projectId, {
    onListDown,
    onListUp,
    onListOpen,
    onListEscape,
    onListNew: () => { if (editable) { setEditingId(null); setDraft(EMPTY); setShowCreate(true); } },
    onListSearch: () => searchRef.current?.focus(),
  });

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && defs.length === 0 && <LoadingSplash label="Loading definitions…" />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Definitions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filtered.length} of ${defs.length} definitions` : `${defs.length} definitions`}
          </p>
        </div>
        {editable && (
          <button
            onClick={() => { setEditingId(null); setDraft(EMPTY); setShowCreate(!showCreate); }}
            className="btn-primary"
          >
            <Plus size={16} /> New Definition
          </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            className="input pl-9 pr-14 h-9"
            placeholder="Search definitions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search ? (
            <button
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setSearch('')}
              title="Clear search"
            >
              <X size={14} />
            </button>
          ) : (
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded border bg-muted text-[10px] font-mono text-muted-foreground pointer-events-none">/</kbd>
          )}
        </div>
      </div>

      <AnimatePresence>
        {showCreate && editable && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={handleSubmit}
            className="card p-4 mb-4 overflow-hidden space-y-3"
          >
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-32">
                <label className="label">Type
                  <select className="input" value={draft.type}
                    onChange={(e) => setDraft({ ...draft, type: e.target.value as 'constraint' | 'calc' })}>
                    <option value="constraint">constraint</option>
                    <option value="calc">calc</option>
                  </select>
                </label>
              </div>
              <div className="w-40">
                <label className="label">ID
                  <input className="input font-mono" placeholder="MassBudget" value={draft.id}
                    onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                    autoFocus disabled={!!editingId} />
                </label>
              </div>
              <div className="flex-1 min-w-[10rem]">
                <label className="label">Name
                  <input className="input" placeholder="Human-readable name" value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </label>
              </div>
              {draft.type === 'calc' && (
                <div className="w-24">
                  <label className="label">Unit
                    <input className="input" placeholder="kg" value={draft.unit}
                      onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
                  </label>
                </div>
              )}
            </div>
            <div>
              <label className="label">Formal parameters
                <input className="input font-mono text-sm" placeholder="actual, limit" value={draft.parameters}
                  onChange={(e) => setDraft({ ...draft, parameters: e.target.value })} />
              </label>
              <p className="text-[11px] text-muted-foreground mt-1">
                Comma-separated names the expression binds.
              </p>
            </div>
            <div>
              <label className="label">Expression
                <input
                  className="input font-mono text-sm"
                  placeholder={draft.type === 'calc' ? 'w * h' : 'actual <= limit'}
                  value={draft.expr}
                  onChange={(e) => setDraft({ ...draft, expr: e.target.value })}
                />
              </label>
            </div>
            <div>
              <label className="label">Notes
                <textarea className="input text-sm h-16 resize-y" placeholder="What this is for"
                  value={draft.doc} onChange={(e) => setDraft({ ...draft, doc: e.target.value })} />
              </label>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary"
                disabled={!draft.id.trim() || !draft.expr.trim()}>
                {editingId ? 'Save' : 'Create'}
              </button>
              <button type="button" className="btn-secondary"
                onClick={() => { setShowCreate(false); setEditingId(null); setDraft(EMPTY); }}>
                Cancel
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {filtered.length === 0 ? (
        <div className="card p-12 text-center">
          <Sigma size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">
            {filtering ? 'No definitions match your search.' : 'No definitions yet'}
          </p>
          {filtering ? (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => setSearch('')}>Clear filters</button>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">
              Write a rule once over formal parameters, then bind it on any requirement.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((d, i) => {
            const isExpanded = expanded.has(d.id);
            return (
            <motion.div
              key={d.id}
              id={`entity-${d.id}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className={`card hover:shadow-md transition-shadow group ${
                focusId === d.id || selectedId === d.id ? 'ring-2 ring-primary/50' : ''
              }`}
            >
              <div className="flex items-center gap-3 p-4">
                  {editable && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); toggleSelect(d.id, e); }}
                      aria-pressed={selectedIds.has(d.id)}
                      aria-label="Select definition"
                      className="shrink-0 cursor-pointer"
                    >
                      {selectedIds.has(d.id) ? (
                        <CheckSquare size={14} className="text-primary" />
                      ) : (
                        <Square size={14} className="text-muted-foreground/40 hover:text-muted-foreground" />
                      )}
                    </button>
                  )}
                <button
                  type="button"
                  onClick={() => toggleExpand(d.id)}
                  aria-expanded={isExpanded}
                  className="flex flex-1 min-w-0 items-center gap-3 text-left cursor-pointer"
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                    d.type === 'calc' ? 'bg-cs-purple/10 text-cs-purple' : 'bg-cs-teal/10 text-cs-teal'
                  }`}>
                    {d.type === 'calc' ? <Sigma size={18} /> : <Boxes size={18} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`badge border ${
                        d.type === 'calc' ? 'text-cs-purple border-cs-purple/30' : 'text-cs-teal border-cs-teal/30'
                      }`}>{d.type}</span>
                      <span className="font-mono text-xs text-muted-foreground">{d.id}</span>
                      <h3 className="font-medium text-card-foreground">{d.name || 'Untitled'}</h3>
                      <CopyLinkButton kind="definition" id={d.id} className="opacity-0 group-hover:opacity-100" />
                    </div>
                    {/* The expression is the substance — mono, like the parametrics card. */}
                    <p className="font-mono text-sm text-foreground mt-1 break-words">
                      ({(d.parameters || []).join(', ')}) = {d.expr}
                      {d.unit ? <span className="text-muted-foreground"> [{d.unit}]</span> : null}
                    </p>
                    {d.doc && <p className="text-xs text-muted-foreground mt-1">{d.doc}</p>}
                  </div>
                </button>
                {editable && (
                  <>
                    <button
                      onClick={() => openEdit(d)}
                      className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all"
                      title="Edit"
                    >
                      <Edit3 size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => toggleExpand(d.id)}
                  aria-expanded={isExpanded}
                  aria-label={isExpanded ? 'Collapse' : 'Expand'}
                  className="shrink-0 p-0.5 -m-0.5 rounded"
                >
                  <ChevronDown
                    size={15}
                    className={`text-muted-foreground transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                  />
                </button>
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
                      <div>
                        <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Comments</h4>
                        <CommentThread entityKind="definitions" entityId={d.id} />
                      </div>
                      <div className="pt-3 border-t border-border">
                        <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Change History</h4>
                        <HistoryPanel itemId={d.id} />
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
            );
          })}
        </div>
      )}
      {selectedIds.size > 0 && editable && (
        <BulkActionBar
          count={selectedIds.size}
          onSelectAll={selectAll}
          onClear={clearSelection}
        >
          <button onClick={handleBulkDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
  );
}
