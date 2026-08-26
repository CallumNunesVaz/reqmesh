import { useEffect, useState, useCallback, useId } from 'react';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Reveal from '../components/Reveal';
import { Plus, Trash2, Edit3, Check, X, Snowflake, GitBranch, Clock, Layers, ArrowRight, ChevronDown, ChevronUp, ChevronRight, Loader, Eye, EyeOff, Calendar, GripVertical } from 'lucide-react';
import { api, type BaselineInfo, type BaselineDiff } from '../api/client';
import { EntityLink } from '../components/entities';
import RichTextEditor from '../components/RichTextEditor';
import { AutoLinkHtml } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { DndContext, DragOverlay, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors, type DragStartEvent, type DragEndEvent } from '@dnd-kit/core';
import { useSortable, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { CSSProperties } from 'react';
import { moveInSequence, moveToIndex } from '../lib/reorder';
import { useConfirm } from '../components/ConfirmDialog';
import { useToasts } from '../components/Toast';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import { useListSelection } from '../hooks/useListSelection';
import LoadingSplash from '../components/LoadingSplash';

/**
 * One draggable row.
 *
 * This has to be a component rather than a callback inside the map: `useSortable`
 * is a hook, and calling it in a loop makes the hook count depend on how many
 * baselines exist. Creating or deleting one then changes that count between
 * renders and React throws, taking the whole page down — which is exactly what
 * happened to the two allocation-matrix tests that create a baseline first.
 */
function SortableBaselineRow({ name, children }: { name: string; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: name });
  const style: CSSProperties = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    transition,
    opacity: isDragging ? 0.4 : undefined,
    position: 'relative',
    zIndex: isDragging ? 10 : undefined,
  };
  return (
    <div ref={setNodeRef} style={style}>
      <div className="flex items-start gap-1">
        <div className="pt-3">
          <button
            {...attributes}
            {...listeners}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-grab active:cursor-grabbing"
            title="Drag to reorder"
          >
            <GripVertical size={14} />
          </button>
        </div>
        <div className="flex-1 min-w-0">{children}</div>
      </div>
    </div>
  );
}

export default function BaselinesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [baselines, setBaselines] = useState<BaselineInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const editable = useAuthStore((s) => s.canEdit());
  const entityKinds = useEntityKinds(projectId);
  const bumpGraph = useStore((s) => s.bumpGraphVersion);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();
  const hiddenBaselines = useStore((s) => s.hiddenBaselines);
  const toggleHiddenBaseline = useStore((s) => s.toggleHiddenBaseline);
  const [activeDragName, setActiveDragName] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  // Create / edit form state
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formSymbol, setFormSymbol] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formDueDate, setFormDueDate] = useState('');
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);
  const descriptionId = useId();

  // Freeze / diff state
  const [freezing, setFreezing] = useState<string | null>(null);
  const [diffing, setDiffing] = useState<string | null>(null);
  const [diffResult, setDiffResult] = useState<BaselineDiff | null>(null);
  const [diffAgainst, setDiffAgainst] = useState<string | undefined>(undefined);
  // Which baseline rows are expanded — persisted per project for the same
  // reason as the other list pages; the create/edit form state above it stays
  // a plain useState, since re-opening a stale draft on return would be wrong.
  const [expanded, setExpanded] = usePersistedState<Set<string>>(
    projectId ? `rt-baselines-expanded-${projectId}` : null, new Set(), setCodec<string>(),
  );

  const load = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await api.listBaselines(projectId);
      setBaselines(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load baselines');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setFormName('');
    setFormSymbol('');
    setFormDesc('');
    setFormDueDate('');
    setEditingName(null);
    setShowForm(true);
  };

  const openEdit = (b: BaselineInfo) => {
    setFormName(b.name);
    setFormSymbol(b.symbol);
    setFormDesc(b.description);
    setFormDueDate(b.due_date);
    setEditingName(b.name);
    setShowForm(true);
  };

  const saveBaseline = async () => {
    if (!projectId || !formName.trim()) return;
    setFormSaving(true);
    setError('');
    try {
      if (editingName) {
        const newName = formName.trim() !== editingName ? formName.trim() : editingName;
        await api.renameBaseline(projectId, editingName, newName, formSymbol, formDesc, formDueDate);
        addToast('success', `Baseline ${newName} updated`);
      } else {
        await api.createBaseline(projectId, formName.trim(), formSymbol, formDesc, undefined, formDueDate);
        addToast('success', `Baseline ${formName.trim()} created`);
      }
      setShowForm(false);
      await load();
      bumpGraph();
    } catch (err: any) {
      setError(err.message || 'Save failed');
    } finally {
      setFormSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!projectId) return;
    const ok = await showConfirm(
      `Delete baseline "${name}"? This will clear it from all requirements.`,
      'Delete Baseline',
      { resultLabel: 'Delete', destructive: true },
    );
    if (!ok) return;
    try {
      await api.deleteBaseline(projectId, name);
      addToast('success', `Baseline ${name} deleted`);
      await load();
      bumpGraph();
    } catch (err: any) {
      setError(err.message || 'Delete failed');
    }
  };

  const handleFreeze = async (name: string) => {
    if (!projectId) return;
    setFreezing(name);
    setError('');
    try {
      await api.freezeBaseline(projectId, name);
      addToast('success', `Baseline ${name} frozen`);
      await load();
    } catch (err: any) {
      setError(err.message || 'Freeze failed');
    } finally {
      setFreezing(null);
    }
  };

  const handleDiff = async (name: string) => {
    if (!projectId) return;
    setDiffing(name);
    setDiffAgainst(undefined);
    setError('');
    try {
      const d = await api.diffBaseline(projectId, name);
      setDiffResult(d);
    } catch (err: any) {
      setError(err.message || 'Diff failed');
    } finally {
      setDiffing(null);
    }
  };

  // Re-fetch when the comparison target changes — including back to undefined,
  // which is "current state". Bailing on a falsy `diffAgainst` left the previous
  // baseline-to-baseline result on screen while the select claimed otherwise.
  //
  // `projectId` and `diffResult.baseline` are read but deliberately omitted from
  // the deps: this effect calls `setDiffResult`, so including either would
  // re-run it on its own output. `diffResult.baseline` is the name of the
  // baseline being diffed (stable across a re-fetch), and `projectId` is a
  // route param that only changes on navigation; both are correct in the
  // closure at the moment `diffAgainst` changes.
  useEffect(() => {
    if (!projectId || !diffResult) return;
    setError('');
    api.diffBaseline(projectId, diffResult.baseline, diffAgainst)
      .then(setDiffResult)
      .catch((err: any) => setError(err.message || 'Diff failed'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diffAgainst]);

  const commitReorder = async (newOrder: string[]) => {
    if (!projectId || !editable) return;
    const prev = baselines;
    setBaselines((current) =>
      current.map((b) => {
        const idx = newOrder.indexOf(b.name);
        return idx === -1 ? b : { ...b, order: idx + 1 };
      }),
    );
    try {
      const result = await api.reorderBaselines(projectId, newOrder);
      setBaselines((current) =>
        current.map((b) => {
          const updated = result.baselines.find((def) => def.name === b.name);
          return updated ? { ...b, order: updated.order } : b;
        }),
      );
    } catch (err: any) {
      setBaselines(prev);
      setError(err.message || 'Reorder failed');
    }
  };

  const handleReorder = async (name: string, direction: 'up' | 'down') => {
    if (!projectId || !editable) return;
    setError('');
    const inSequence = baselines
      .filter((b) => b.order > 0)
      .sort((a, b) => a.order - b.order)
      .map((b) => b.name);
    const newOrder = moveInSequence(inSequence, name, direction);
    if (!newOrder) return;
    await commitReorder(newOrder);
  };

  const handleDragStart = (e: DragStartEvent) => {
    setActiveDragName(String(e.active.id));
  };

  const handleDragEnd = (e: DragEndEvent) => {
    setActiveDragName(null);
    const { active, over } = e;
    if (!over || active.id === over.id) return;

    const inSequence = baselines
      .filter((b) => b.order > 0)
      .sort((a, b) => a.order - b.order)
      .map((b) => b.name);
    const fromIdx = inSequence.indexOf(String(active.id));
    const toIdx = inSequence.indexOf(String(over.id));
    if (fromIdx === -1 || toIdx === -1) return;

    commitReorder(moveToIndex(inSequence, fromIdx, toIdx));
  };

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const renderRow = (b: BaselineInfo) => (
    <Reveal
      key={b.name}
      id={`entity-${b.name}`}
      className={`card p-4 ${selectedId === b.name ? 'ring-2 ring-primary/50' : ''}`}
    >
      {/* Row header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {b.symbol && (
              <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-cs-blue/10 text-cs-blue font-mono font-bold text-xs border border-cs-blue/25">
                {b.symbol}
              </span>
            )}
            <h3 className="font-semibold text-card-foreground font-mono">{b.name}</h3>
            {b.frozen && (
              <span className="badge bg-cs-green/10 text-cs-green text-[10px] gap-1">
                <Snowflake size={10} /> Frozen
              </span>
            )}
          </div>
          {b.description && (
            // The app's own read-only renderer, as used for the same text in
            // the edit form below and for every other stored HTML field: it
            // parses to React through a tag whitelist and drops every
            // attribute, so nothing executes. This was the one place left
            // injecting stored HTML directly.
            <AutoLinkHtml
              html={b.description}
              kinds={entityKinds}
              className="text-sm text-muted-foreground mt-1 prose prose-sm dark:prose-invert max-w-none line-clamp-2 opacity-80"
            />
          )}
          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <GitBranch size={12} />
              {b.frozen ? `${b.frozen_count} frozen` : ''} {b.count} requirement{b.count !== 1 ? 's' : ''}
            </span>
            <span className="flex items-center gap-1">
              <Layers size={12} />
              {b.component_count} component{b.component_count !== 1 ? 's' : ''}
            </span>
            {b.frozen_at && (
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {new Date(b.frozen_at).toLocaleDateString()}
              </span>
            )}
            {b.due_date && (
              <span className="flex items-center gap-1">
                <Calendar size={12} />
                {b.due_date}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => { toggleHiddenBaseline(b.name); bumpGraph(); }}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title={hiddenBaselines.includes(b.name) ? 'Hidden in graph' : 'Shown in graph'}
          >
            {hiddenBaselines.includes(b.name) ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
          {editable && (
            <>
              {b.order > 0 && (
                <>
                  <button
                    onClick={() => handleReorder(b.name, 'up')}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    title="Move up"
                    disabled={b.name === firstSeqName}
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    onClick={() => handleReorder(b.name, 'down')}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    title="Move down"
                    disabled={b.name === lastSeqName}
                  >
                    <ChevronDown size={14} />
                  </button>
                </>
              )}
              <button
                onClick={() => openEdit(b)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                title="Edit baseline"
              >
                <Edit3 size={14} />
              </button>
              <button
                onClick={() => handleFreeze(b.name)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-cs-teal hover:bg-cs-teal/10 transition-colors"
                title="Freeze snapshot"
                disabled={freezing === b.name}
              >
                {freezing === b.name ? <Loader size={14} className="animate-spin" /> : <Snowflake size={14} />}
              </button>
              {b.frozen && (
                <button
                  onClick={() => handleDiff(b.name)}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-cs-purple hover:bg-cs-purple/10 transition-colors"
                  title="Diff against current"
                  disabled={diffing === b.name}
                >
                  {diffing === b.name ? <Loader size={14} className="animate-spin" /> : <GitBranch size={14} />}
                </button>
              )}
              <button
                onClick={() => handleDelete(b.name)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                title="Delete baseline"
              >
                <Trash2 size={14} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Requirements list */}
      {b.requirements.length > 0 && (
        <div className="mt-3 pt-3 border-t border-border/50">
          <button
            onClick={() => toggleExpand(b.name)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded.has(b.name) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Requirements ({b.count})
          </button>
          <AnimatePresence>
            {expanded.has(b.name) && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {b.requirements.map((rid) => (
                    <EntityLink
                      key={rid}
                      kind="requirement"
                      id={rid}
                      className="badge bg-muted text-muted-foreground hover:text-foreground transition-colors text-xs"
                      showIcon
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
      {/* Components list */}
      {b.components.length > 0 && (
        <div className={`${b.requirements.length > 0 ? 'pt-2' : 'mt-3 pt-3 border-t border-border/50'}`}>
          {/* Show a toggle only when there are no requirements — otherwise
              the requirements toggle above also reveals this section. */}
          {b.requirements.length === 0 && (
            <button
              onClick={() => toggleExpand(b.name)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {expanded.has(b.name) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              Components ({b.component_count})
            </button>
          )}
          <AnimatePresence>
            {expanded.has(b.name) && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {b.components.map((cid) => (
                    <EntityLink
                      key={cid}
                      kind="component"
                      id={cid}
                      className="badge bg-muted text-muted-foreground hover:text-foreground transition-colors text-xs"
                      showIcon
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </Reveal>
  );

  const inSequence = baselines.filter((b) => b.order > 0).sort((a, b) => a.order - b.order);
  const orphans = baselines.filter((b) => b.order === 0);
  const firstSeqName = inSequence.length > 0 ? inSequence[0].name : null;
  const lastSeqName = inSequence.length > 0 ? inSequence[inSequence.length - 1].name : null;
  const activeDrag = activeDragName ? baselines.find((b) => b.name === activeDragName) ?? null : null;

  const { focusId: selectedId, onListDown, onListUp, onListOpen, onListEscape } = useListSelection(
    [...inSequence, ...orphans].map((b) => b.name),
    toggleExpand,
  );

  useKeyboardShortcuts(projectId, {
    onListDown,
    onListUp,
    onListOpen,
    onListEscape,
    onListNew: () => { if (editable) openCreate(); },
  });

  return (
    <div className="relative flex flex-col h-full overflow-y-auto">
      {loading && <LoadingSplash label="Loading baselines…" />}
      <div className="p-6 space-y-6 max-w-6xl mx-auto w-full">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Baselines</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Configuration baselines represent snapshots of the system at a point in time.
              Define baselines with a name, symbol, and description, then freeze them to
              capture the current state of all requirements.
            </p>
          </div>
          {editable && (
            <button onClick={openCreate} className="btn-primary gap-1.5">
              <Plus size={16} /> New Baseline
            </button>
          )}
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm border border-destructive/20">
            {error}
          </div>
        )}

        {/* Create / Edit form */}
        <AnimatePresence>
          {showForm && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="card p-5 space-y-4 border-2 border-primary/20">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <Layers size={16} />
                  {editingName ? `Edit "${editingName}"` : 'New Baseline'}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_150px] gap-3">
                  <div>
                    <label className="label">Name * <input
                      className="input"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="e.g. PDR, CDR, TRR"
                      disabled={formSaving}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveBaseline(); }}
                    /></label>
                  </div>
                  <div>
                    <label className="label">Symbol <input
                      className="input font-mono"
                      value={formSymbol}
                      onChange={(e) => setFormSymbol(e.target.value)}
                      placeholder="e.g. P"
                      maxLength={8}
                      disabled={formSaving}
                    /></label>
                  </div>
                </div>
                <div>
                  <label className="label">Due Date <input
                    className="input"
                    type="date"
                    value={formDueDate}
                    onChange={(e) => setFormDueDate(e.target.value)}
                    disabled={formSaving}
                  /></label>
                </div>
                <div>
                  <label className="label" htmlFor={descriptionId}>Description</label>
                  {editable ? (
                    <RichTextEditor
                      id={descriptionId}
                      content={formDesc}
                      onChange={setFormDesc}
                      onBlur={() => {}}
                      disabled={formSaving}
                      placeholder="Write a baseline description…"
                    />
                  ) : (
                    <div className="min-h-[80px] border rounded-lg p-3 text-sm text-muted-foreground">
                      {formDesc ? <AutoLinkHtml html={formDesc} kinds={entityKinds} />
                                : <span className="italic">No description</span>}
                    </div>
                  )}
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setShowForm(false)}
                    className="btn-secondary text-xs"
                    disabled={formSaving}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={saveBaseline}
                    className="btn-primary text-xs gap-1.5"
                    disabled={formSaving || !formName.trim()}
                  >
                    {formSaving ? <Loader size={14} className="animate-spin" /> : <Check size={14} />}
                    {editingName ? 'Save' : 'Create'}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Baseline list */}
        {baselines.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Layers size={32} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">No baselines defined yet.</p>
            {editable && (
              <p className="text-xs mt-1">
                Create a baseline definition, then assign requirements and freeze snapshots.
              </p>
            )}
          </div>
        ) : (
          <>
            {inSequence.length > 0 && (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
                <SortableContext items={inSequence.map((b) => b.name)} strategy={verticalListSortingStrategy}>
                  <div className="space-y-3">
                    {inSequence.map((b) => (
                      <SortableBaselineRow key={b.name} name={b.name}>
                        {renderRow(b)}
                      </SortableBaselineRow>
                    ))}
                  </div>
                </SortableContext>
                <DragOverlay>
                  {activeDrag && (
                    <div className="flex items-start gap-1">
                      <div className="pt-3">
                        <button className="p-1 rounded-md text-muted-foreground bg-muted/40 cursor-grabbing" title="Drag to reorder">
                          <GripVertical size={14} />
                        </button>
                      </div>
                      <div className="flex-1 min-w-0 opacity-90">
                        {renderRow(activeDrag)}
                      </div>
                    </div>
                  )}
                </DragOverlay>
              </DndContext>
            )}
            {orphans.length > 0 && (
              <div className={inSequence.length > 0 ? 'space-y-3 mt-3' : 'space-y-3'}>
                {inSequence.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    These baselines are referenced by requirements but not part of the sequence — define them under Project Settings to include them in ordering.
                  </p>
                )}
                {orphans.map((b) => renderRow(b))}
              </div>
            )}
          </>
        )}

        {/* Diff result */}
        <AnimatePresence>
          {diffResult && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="card p-5 border-l-2 border-l-cs-purple"
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-sm flex items-center gap-2">
                    <GitBranch size={16} className="text-cs-purple" />
                    Diff: {diffResult.baseline}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Frozen {new Date(diffResult.frozen_at).toLocaleString()} —{' '}
                    {diffResult.changed_count} change{diffResult.changed_count !== 1 ? 's' : ''}
                  </p>
                </div>
                <button
                  onClick={() => { setDiffResult(null); setDiffAgainst(undefined); }}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="mb-3">
                <select
                  className="input text-sm"
                  value={diffAgainst ?? ''}
                  onChange={(e) => setDiffAgainst(e.target.value || undefined)}
                >
                  <option value="">Current state</option>
                  {baselines
                    .filter((b) => b.frozen && b.name !== diffResult.baseline)
                    .map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.symbol ? `${b.symbol} — ` : ''}{b.name}
                      </option>
                    ))}
                </select>
              </div>

              {diffResult.changes.length === 0 ? (
                <p className="text-sm text-muted-foreground">No changes — everything matches.</p>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {diffResult.changes.map((c) => (
                    <div key={c.id} className="flex items-start gap-2 p-2 rounded-md bg-muted/30 text-sm">
                      <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${
                        c.type === 'added' ? 'bg-cs-green' :
                        c.type === 'removed' ? 'bg-cs-red' : 'bg-cs-orange'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <EntityLink kind="requirement" id={c.id} className="font-mono text-xs" />
                          <span className={`text-[10px] font-medium uppercase tracking-wider ${
                            c.type === 'added' ? 'text-cs-green' :
                            c.type === 'removed' ? 'text-cs-red' : 'text-cs-orange'
                          }`}>
                            {c.type}
                          </span>
                        </div>
                        {c.diffs && (
                          <div className="mt-1 space-y-0.5 text-xs">
                            {Object.entries(c.diffs).map(([field, diff]) => (
                              <div key={field} className="flex gap-2">
                                <span className="text-muted-foreground shrink-0">{field}:</span>
                                <span className="text-cs-red/80 line-through">{diff.before}</span>
                                <ArrowRight size={12} className="shrink-0 mt-0.5 text-muted-foreground" />
                                <span className="text-cs-green/80">{diff.after}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
