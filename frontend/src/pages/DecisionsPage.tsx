import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Scale, Trash2, ChevronDown, X, Search, Edit3, Square, CheckSquare } from 'lucide-react';
import { api, type Requirement, type Component, type DecisionRecord } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import MentionTextarea from '../components/MentionTextarea';
import { useEntityKinds } from '../components/entityIndex';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { LinkEditor } from '../components/LinkEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { deleteWithReferenceCheck } from '../lib/forceDelete';
import { useConfirm } from '../components/ConfirmDialog';
import { useToasts } from '../components/Toast';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import { useListSelection } from '../hooks/useListSelection';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';
import EmptyState from '../components/EmptyState';

/**
 * Architecture decision records.
 *
 * Decisions had full CRUD, client methods, search coverage and an export
 * section, but no page and no route — so one not linked to a requirement was
 * unreachable in the UI. The four ADR fields stay four separate fields:
 * collapsing context, decision, rationale and consequences into one blob is
 * what makes an ADR stop being an ADR.
 */

/** Offered as a convenience — `status` is a free string on the model. */
const COMMON_STATUSES = ['proposed', 'accepted', 'superseded', 'deprecated', 'rejected'];

const STATUS_CLS: Record<string, string> = {
  proposed: 'text-cs-yellow border-cs-yellow/30',
  accepted: 'text-cs-green border-cs-green/30',
  superseded: 'text-cs-grey border-cs-grey/30',
  deprecated: 'text-cs-orange border-cs-orange/30',
  rejected: 'text-cs-red border-cs-red/30',
};

const EMPTY = {
  id: '', title: '', context: '', decision: '', rationale: '',
  consequences: '', status: 'accepted', decided_by: '',
};

export default function DecisionsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const editable = useAuthStore((s) => s.canEdit());
  const dataVersion = useStore((s) => s.dataVersion);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState('');
  const pk = (field: string) => (projectId ? `rt-decisions-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const searchRef = useRef<HTMLInputElement>(null);
  const [expanded, setExpanded] = usePersistedState<Set<string>>(pk('expanded'), new Set(), setCodec<string>());
  const entityKinds = useEntityKinds(projectId);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();

  const load = () => {
    if (!projectId) return;
    api.listDecisions(projectId).then(setDecisions).catch(() => setDecisions([]))
      .finally(() => setLoading(false));
    api.listRequirements(projectId).then(setRequirements).catch(() => {});
    api.listComponents(projectId).then(setComponents).catch(() => {});
  };

  useEffect(load, [projectId, dataVersion]);

  const reqNames = useMemo(() => new Map(requirements.map((r) => [r.id, r.name])), [requirements]);
  const compNames = useMemo(() => new Map(components.map((c) => [c.id, c.name])), [components]);

  const filtered = useMemo(() => {
    if (!search) return decisions;
    const q = search.toLowerCase();
    return decisions.filter((d) =>
      d.id.toLowerCase().includes(q) || (d.title || '').toLowerCase().includes(q));
  }, [decisions, search]);
  const filtering = !!search;

  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const focusId = useFocusedEntity(
    decisions.length > 0,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useCallback((id: string) => setExpanded((prev) => new Set(prev).add(id)), []),
  );

  const { focusId: selectedId, onListDown, onListUp, onListOpen, onListEscape } = useListSelection(
    useMemo(() => filtered.map((d) => d.id), [filtered]),
    toggleExpand,
  );

  useKeyboardShortcuts(projectId, {
    onListDown,
    onListUp,
    onListOpen,
    onListEscape,
    onListNew: () => { if (editable) { setEditingId(null); setDraft(EMPTY); setShowCreate(true); } },
    onListSearch: () => searchRef.current?.focus(),
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !editable || !draft.id.trim()) return;
    try {
      if (editingId) {
        const { id: _id, ...rest } = draft;
        await api.updateDecision(projectId, editingId, rest);
        addToast('success', `Decision ${editingId} updated`);
      } else {
        const newId = draft.id.trim();
        await api.createDecision(projectId, { ...draft, id: newId });
        addToast('success', `Decision ${newId} created`);
      }
      setShowCreate(false);
      setEditingId(null);
      setDraft(EMPTY);
      setError('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save decision');
    }
  };

  const openEdit = (d: DecisionRecord) => {
    setDraft({
      id: d.id, title: d.title || '', context: d.context || '', decision: d.decision || '',
      rationale: d.rationale || '', consequences: d.consequences || '',
      status: d.status || 'accepted', decided_by: d.decided_by || '',
    });
    setEditingId(d.id);
    setShowCreate(true);
  };

  const setLinks = async (id: string, patch: Partial<DecisionRecord>) => {
    if (!projectId) return;
    setDecisions((prev) => prev.map((d) => (d.id === id ? { ...d, ...patch } : d)));
    try {
      await api.updateDecision(projectId, id, patch);
    } catch (err) {
      console.error(err);
      load();
    }
  };

  const handleDelete = async (id: string) => {
    if (!projectId) return;
    const ok = await showConfirm(`Delete decision ${id}?`, 'Delete Decision', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    const done = await deleteWithReferenceCheck(
      (force) => api.deleteDecision(projectId, id, force),
      (message) => showConfirm(message),
    );
    if (done) {
      addToast('success', `Decision ${id} deleted`);
      load();
    }
  };

  // The stored status may be anything, so the picker must offer whatever is
  // already set as well as the common values — otherwise editing a decision
  // silently rewrites a status the model permits.
  const statusOptions = useMemo(() => {
    const s = draft.status.trim();
    return s && !COMMON_STATUSES.includes(s) ? [s, ...COMMON_STATUSES] : COMMON_STATUSES;
  }, [draft.status]);

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
    const saved = decisions.filter((d) => selectedIds.has(d.id)).map((d) => ({ ...d }));
    await runBulkDelete({
      noun: 'decision',
      ids,
      saved,
      idOf: (d) => d.id,
      remove: (idsToRemove) => api.bulkDeleteDecisions(projectId, idsToRemove),
      recreate: (item) => api.createDecision(projectId, item),
    });
  };

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && decisions.length === 0 && <LoadingSplash label="Loading decisions…" />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Decisions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filtered.length} of ${decisions.length} decisions` : `${decisions.length} decisions`}
          </p>
        </div>
        {editable && (
          <button
            onClick={() => { setEditingId(null); setDraft(EMPTY); setShowCreate(!showCreate); }}
            className="btn-primary"
          >
            <Plus size={16} /> New Decision
          </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            className="input pl-9 pr-14 h-9"
            placeholder="Search decisions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search ? (
            <button
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setSearch('')}
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
            <div className="flex items-end gap-3">
              <div className="w-44">
                <label className="label">ID <input className="input font-mono" placeholder="ADR-001" value={draft.id}
                  onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                  disabled={!!editingId} /></label>
              </div>
              <div className="flex-1">
                <label className="label">Title <input className="input" placeholder="Decision title" value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
              </div>
              <div className="w-40">
                <label className="label">Status <select className="input" value={draft.status}
                  onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                  {statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                </select></label>
              </div>
              <div className="w-44">
                <label className="label">Decided by <input className="input" placeholder="Name" value={draft.decided_by}
                  onChange={(e) => setDraft({ ...draft, decided_by: e.target.value })} /></label>
              </div>
            </div>
            {/* The four ADR fields, each its own box — see the file header. */}
            {([
              ['context', 'Context', 'What forced a decision to be made?'],
              ['decision', 'Decision', 'What was decided?'],
              ['rationale', 'Rationale', 'Why this option over the others?'],
              ['consequences', 'Consequences', 'What follows from it, good and bad?'],
            ] as const).map(([field, label, hint]) => (
              <div key={field}>
                <label className="label">{label}</label>
                <MentionTextarea
                  className="input text-sm h-20 resize-y"
                  placeholder={hint}
                  value={draft[field]}
                  onChange={(v) => setDraft({ ...draft, [field]: v })}
                />
              </div>
            ))}
            <div className="flex gap-2">
              <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create'}</button>
              <button type="button" className="btn-secondary"
                onClick={() => { setShowCreate(false); setEditingId(null); setDraft(EMPTY); setError(''); }}>
                Cancel
              </button>
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
          </motion.form>
        )}
      </AnimatePresence>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Scale}
          title={filtering ? 'No decisions match your search.' : 'No decisions yet'}
          hint={filtering ? undefined : 'Record why the architecture is the way it is, so the reasoning outlives the people who had it.'}
          action={!filtering && editable ? { label: 'New Decision', onClick: () => { setEditingId(null); setDraft(EMPTY); setShowCreate(!showCreate); } } : undefined}
        >
          {filtering && (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => setSearch('')}>Clear filters</button>
          )}
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {filtered.map((d, i) => {
            const isExpanded = expanded.has(d.id);
            return (
              <motion.div
                key={d.id}
                id={`entity-${d.id}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`card hover:shadow-md transition-shadow group ${focusId === d.id || selectedId === d.id ? 'ring-2 ring-primary/50' : ''}`}
              >
                <div className="flex items-center gap-3 p-4">
                    {editable && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggleSelect(d.id, e); }}
                        aria-pressed={selectedIds.has(d.id)}
                        aria-label="Select decision"
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
                    <div className="w-9 h-9 bg-cs-teal/10 text-cs-teal rounded-lg flex items-center justify-center shrink-0">
                      <Scale size={18} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{d.id}</span>
                        <h3 className="font-medium text-card-foreground">{d.title || 'Untitled'}</h3>
                        <CopyLinkButton kind="decision" id={d.id} className="opacity-0 group-hover:opacity-100" />
                      </div>
                      {d.decision && (
                        <p className="text-sm text-muted-foreground mt-0.5 line-clamp-1">
                          <AutoLinkText text={d.decision} kinds={entityKinds} />
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span className={`badge border ${STATUS_CLS[d.status] || 'text-cs-grey border-cs-grey/30'}`}>
                          {d.status || 'unset'}
                        </span>
                        {d.decided_by && <span>by {d.decided_by}</span>}
                        <span>{(d.linked_requirements || []).length} requirement{(d.linked_requirements || []).length === 1 ? '' : 's'}</span>
                        <span>{(d.linked_components || []).length} component{(d.linked_components || []).length === 1 ? '' : 's'}</span>
                      </div>
                    </div>
                  </button>
                  {editable && (
                    <>
                      <button
                        onClick={() => openEdit(d)}
                        className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                        title="Edit"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(d.id)}
                        className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
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
                        {([
                          ['context', 'Context'],
                          ['decision', 'Decision'],
                          ['rationale', 'Rationale'],
                          ['consequences', 'Consequences'],
                        ] as const).map(([field, label]) => (
                          <div key={field}>
                            <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">{label}</h4>
                            {d[field] ? (
                              <p className="text-sm text-card-foreground whitespace-pre-wrap">
                                <AutoLinkText text={d[field]} kinds={entityKinds} />
                              </p>
                            ) : (
                              <p className="text-xs text-muted-foreground italic">Not recorded.</p>
                            )}
                          </div>
                        ))}

                        <LinkEditor
                          label="Requirements" hint="Requirements this decision governs." kind="requirement"
                          linked={d.linked_requirements || []}
                          options={requirements.map((r) => ({ id: r.id, name: r.name }))}
                          editable={editable}
                          onAdd={(id) => setLinks(d.id, { linked_requirements: [...(d.linked_requirements || []), id] })}
                          onRemove={(id) => setLinks(d.id, { linked_requirements: (d.linked_requirements || []).filter((x) => x !== id) })}
                          nameOf={(id) => reqNames.get(id) ?? ''}
                        />
                        <LinkEditor
                          label="Decides On" hint="Components this decision settles." kind="component"
                          linked={d.linked_components || []}
                          options={components.map((c) => ({ id: c.id, name: c.name }))}
                          editable={editable}
                          onAdd={(id) => setLinks(d.id, { linked_components: [...(d.linked_components || []), id] })}
                          onRemove={(id) => setLinks(d.id, { linked_components: (d.linked_components || []).filter((x) => x !== id) })}
                          nameOf={(id) => compNames.get(id) ?? ''}
                        />

                        <div className="pt-3 border-t border-border">
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Comments</h4>
                          <CommentThread entityKind="decisions" entityId={d.id} />
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
