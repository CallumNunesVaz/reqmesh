import { useEffect, useState, useCallback } from 'react';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Edit3, Check, X, Snowflake, History, GitBranch, Clock, Layers, ArrowRight, ChevronDown, ChevronUp, ChevronRight, Loader, Eye, EyeOff, Calendar } from 'lucide-react';
import { api, type BaselineInfo, type BaselineDiff } from '../api/client';
import { EntityLink } from '../components/entities';
import RichTextEditor from '../components/RichTextEditor';
import { AutoLinkHtml } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { HelpTip } from '../components/HelpTip';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';

export default function BaselinesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [baselines, setBaselines] = useState<BaselineInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const editable = useAuthStore((s) => s.canEdit());
  const entityKinds = useEntityKinds(projectId);
  const bumpGraph = useStore((s) => s.bumpGraphVersion);
  const hiddenBaselines = useStore((s) => s.hiddenBaselines);
  const toggleHiddenBaseline = useStore((s) => s.toggleHiddenBaseline);

  // Create / edit form state
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formSymbol, setFormSymbol] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formDueDate, setFormDueDate] = useState('');
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  // Freeze / diff state
  const [freezing, setFreezing] = useState<string | null>(null);
  const [diffing, setDiffing] = useState<string | null>(null);
  const [diffResult, setDiffResult] = useState<BaselineDiff | null>(null);
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
      } else {
        await api.createBaseline(projectId, formName.trim(), formSymbol, formDesc, undefined, formDueDate);
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
    if (!projectId || !confirm(`Delete baseline "${name}"? This will clear it from all requirements.`)) return;
    try {
      await api.deleteBaseline(projectId, name);
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

  const handleReorder = async (name: string, direction: 'up' | 'down') => {
    if (!projectId || !editable) return;
    setError('');
    const inSequence = baselines
      .filter((b) => b.order > 0)
      .sort((a, b) => a.order - b.order)
      .map((b) => b.name);
    const idx = inSequence.indexOf(name);
    if (idx === -1) return;
    const newOrder = [...inSequence];
    if (direction === 'up' && idx > 0) {
      [newOrder[idx - 1], newOrder[idx]] = [newOrder[idx], newOrder[idx - 1]];
    } else if (direction === 'down' && idx < newOrder.length - 1) {
      [newOrder[idx], newOrder[idx + 1]] = [newOrder[idx + 1], newOrder[idx]];
    } else {
      return;
    }
    try {
      const result = await api.reorderBaselines(projectId, newOrder);
      setBaselines((prev) =>
        prev.map((b) => {
          const updated = result.baselines.find((def) => def.name === b.name);
          return updated ? { ...b, order: updated.order } : b;
        }),
      );
    } catch (err: any) {
      setError(err.message || 'Reorder failed');
    }
  };

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader size={20} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto w-full">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-card-foreground">Baselines</h1>
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
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_100px] gap-3">
                  <div>
                    <label className="label">Name *</label>
                    <input
                      className="input"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="e.g. PDR, CDR, TRR"
                      disabled={formSaving}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveBaseline(); }}
                    />
                  </div>
                  <div>
                    <label className="label">Symbol</label>
                    <input
                      className="input font-mono"
                      value={formSymbol}
                      onChange={(e) => setFormSymbol(e.target.value)}
                      placeholder="e.g. P"
                      maxLength={8}
                      disabled={formSaving}
                    />
                  </div>
                </div>
                <div>
                  <label className="label">Due Date</label>
                  <input
                    className="input"
                    type="date"
                    value={formDueDate}
                    onChange={(e) => setFormDueDate(e.target.value)}
                    disabled={formSaving}
                  />
                </div>
                <div>
                  <label className="label">Description</label>
                  {editable ? (
                    <RichTextEditor
                      content={formDesc}
                      onChange={setFormDesc}
                      onBlur={() => {}}
                      disabled={formSaving}
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
          <div className="space-y-3">
            {(() => {
              const seq = baselines.filter((b) => b.order > 0).sort((a, b) => a.order - b.order);
              const firstSeqName = seq.length > 0 ? seq[0].name : null;
              const lastSeqName = seq.length > 0 ? seq[seq.length - 1].name : null;
              return baselines.map((b) => (
              <motion.div
                key={b.name}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="card p-4"
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
                      <div
                        className="text-sm text-muted-foreground mt-1 prose prose-sm dark:prose-invert max-w-none line-clamp-2 opacity-80"
                        dangerouslySetInnerHTML={{ __html: b.description }}
                      />
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <GitBranch size={12} />
                        {b.frozen ? `${b.frozen_count} frozen` : ''} {b.count} requirement{b.count !== 1 ? 's' : ''}
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
              </motion.div>
              ));
            })()}
          </div>
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
                  onClick={() => setDiffResult(null)}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground"
                >
                  <X size={16} />
                </button>
              </div>

              {diffResult.changes.length === 0 ? (
                <p className="text-sm text-muted-foreground">No changes since freeze — everything matches.</p>
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
