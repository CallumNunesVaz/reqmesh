import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, FlaskConical, Trash2, X, Search, Edit3, ChevronDown } from 'lucide-react';
import { api, type AnalysisCase, type Requirement, type Component } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton, SECTION_TITLES } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { LinkEditor } from '../components/LinkEditor';
import { useToasts } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';
import LoadingSplash from '../components/LoadingSplash';

/**
 * Scoped what-if analysis cases.
 *
 * Deliberately no Run button. Analysis cases are evaluated from the
 * parametrics/what-if surface, which owns the solver and the result rendering;
 * a run action here would imply an endpoint and a result panel this page does
 * not have.
 */

const EMPTY = { id: '', name: '', doc: '', overrides: '' };

/** `overrides` is `Record<string, number>` keyed "ENTITY.param" — edited as
 *  one `key = value` per line, which round-trips cleanly and keeps the shape
 *  obvious. Lines that are not a number are dropped rather than stored as NaN. */
function parseOverrides(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const line of text.split('\n')) {
    const [k, v] = line.split('=').map((s) => s.trim());
    if (k && v !== undefined && v !== '' && !Number.isNaN(Number(v))) out[k] = Number(v);
  }
  return out;
}

const formatOverrides = (o: Record<string, number>) =>
  Object.entries(o).map(([k, v]) => `${k} = ${v}`).join('\n');

export default function AnalysisPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const editable = useAuthStore((s) => s.canEdit());
  const dataVersion = useStore((s) => s.dataVersion);
  const { addToast } = useToasts();
  const showConfirm = useConfirm();
  const [cases, setCases] = useState<AnalysisCase[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const pk = (field: string) => (projectId ? `rt-analysis-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [expanded, setExpanded] = usePersistedState<Set<string>>(pk('expanded'), new Set(), setCodec<string>());

  const load = () => {
    if (!projectId) return;
    api.listAnalysisCases(projectId).then(setCases).catch(() => setCases([]))
      .finally(() => setLoading(false));
    api.listRequirements(projectId).then(setRequirements).catch(() => {});
    api.listComponents(projectId).then(setComponents).catch(() => {});
  };

  useEffect(load, [projectId, dataVersion]);

  const reqNames = useMemo(() => new Map(requirements.map((r) => [r.id, r.name])), [requirements]);
  const compNames = useMemo(() => new Map(components.map((c) => [c.id, c.name])), [components]);

  const filtered = useMemo(() => {
    if (!search) return cases;
    const q = search.toLowerCase();
    return cases.filter((c) => c.id.toLowerCase().includes(q) || (c.name || '').toLowerCase().includes(q));
  }, [cases, search]);
  const filtering = !!search;

  const toggleExpand = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const focusId = useFocusedEntity(
    cases.length > 0,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useCallback((id: string) => setExpanded((prev) => new Set(prev).add(id)), []),
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !editable || !draft.id.trim()) return;
    try {
      if (editingId) {
        await api.updateAnalysisCase(projectId, editingId, {
          name: draft.name.trim(), doc: draft.doc.trim(),
          overrides: parseOverrides(draft.overrides),
        });
        addToast('success', `Analysis case ${editingId} updated`);
      } else {
        await api.createAnalysisCase(projectId, {
          id: draft.id.trim(), name: draft.name.trim(), doc: draft.doc.trim(),
          scope: [], scope_components: [],
          overrides: parseOverrides(draft.overrides),
        });
        addToast('success', `Analysis case ${draft.id.trim()} created`);
      }
      setShowCreate(false);
      setEditingId(null);
      setDraft(EMPTY);
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save analysis case');
    }
  };

  const openEdit = (c: AnalysisCase) => {
    setDraft({
      id: c.id, name: c.name || '', doc: c.doc || '',
      overrides: formatOverrides(c.overrides || {}),
    });
    setEditingId(c.id);
    setShowCreate(true);
  };

  const setLinks = async (id: string, patch: Partial<AnalysisCase>) => {
    if (!projectId) return;
    setCases((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
    try {
      await api.updateAnalysisCase(projectId, id, patch);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const handleDelete = async (id: string) => {
    if (!projectId) return;
    const ok = await showConfirm(`Delete analysis case ${id}?`, 'Delete Analysis Case', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      await api.deleteAnalysisCase(projectId, id);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Delete failed');
      return;
    }
    addToast('success', `Analysis case ${id} deleted`);
    load();
  };

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && cases.length === 0 && <LoadingSplash label="Loading analysis cases…" />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{SECTION_TITLES.analysis}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filtered.length} of ${cases.length} cases` : `${cases.length} cases`}
          </p>
        </div>
        {editable && (
          <button
            onClick={() => { setEditingId(null); setDraft(EMPTY); setShowCreate(!showCreate); }}
            className="btn-primary"
          >
            <Plus size={16} /> New Analysis Case
          </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="input pl-9 pr-14 h-9"
            placeholder="Search analysis cases…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setSearch('')}
              title="Clear search"
            >
              <X size={14} />
            </button>
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
              <div className="w-48">
                <label className="label">ID</label>
                <input className="input font-mono" placeholder="heavy-config" value={draft.id}
                  onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                  autoFocus disabled={!!editingId} />
              </div>
              <div className="flex-1">
                <label className="label">Name</label>
                <input className="input" placeholder="Heavy configuration" value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
            </div>
            <div>
              <label className="label">Overrides</label>
              <textarea
                className="input font-mono text-sm h-24 resize-y"
                placeholder={'One per line:\nGROS0001.mass = 1200'}
                value={draft.overrides}
                onChange={(e) => setDraft({ ...draft, overrides: e.target.value })}
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                Hypothetical parameter values, keyed <code className="font-mono">ENTITY.param</code>.
              </p>
            </div>
            <div>
              <label className="label">Notes</label>
              <textarea className="input text-sm h-16 resize-y" value={draft.doc}
                onChange={(e) => setDraft({ ...draft, doc: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary" disabled={!draft.id.trim()}>
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
          <FlaskConical size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">
            {filtering ? 'No analysis cases match your search.' : 'No analysis cases yet'}
          </p>
          {filtering ? (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => setSearch('')}>Clear filters</button>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">
              Define a scoped set of hypothetical parameter values, then evaluate it against the live solver.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((c, i) => {
            const isExpanded = expanded.has(c.id);
            const overrideCount = Object.keys(c.overrides || {}).length;
            return (
              <motion.div
                key={c.id}
                id={`entity-${c.id}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`card hover:shadow-md transition-shadow group ${
                  focusId === c.id ? 'ring-2 ring-primary/50' : ''
                }`}
              >
                <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => toggleExpand(c.id)}>
                  <div className="w-9 h-9 bg-cs-purple/10 text-cs-purple rounded-lg flex items-center justify-center">
                    <FlaskConical size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{c.id}</span>
                      <h3 className="font-medium text-card-foreground">{c.name || 'Untitled'}</h3>
                      <CopyLinkButton kind="analysis" id={c.id} className="opacity-0 group-hover:opacity-100" />
                    </div>
                    <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                      <span>{(c.scope || []).length} requirement{(c.scope || []).length === 1 ? '' : 's'}</span>
                      <span>{(c.scope_components || []).length} component{(c.scope_components || []).length === 1 ? '' : 's'}</span>
                      <span>{overrideCount} override{overrideCount === 1 ? '' : 's'}</span>
                    </div>
                  </div>
                  {editable && (
                    <>
                      <button
                        onClick={(e) => { e.stopPropagation(); openEdit(c); }}
                        className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all"
                        title="Edit"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(c.id); }}
                        className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </>
                  )}
                  <ChevronDown
                    size={15}
                    className={`text-muted-foreground transition-transform duration-200 shrink-0 ${isExpanded ? 'rotate-180' : ''}`}
                  />
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
                        {c.doc && <p className="text-sm text-muted-foreground">{c.doc}</p>}

                        <div>
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Overrides</h4>
                          {overrideCount === 0 ? (
                            <p className="text-xs text-muted-foreground italic">None — the case evaluates the model as stored.</p>
                          ) : (
                            <div className="space-y-1">
                              {Object.entries(c.overrides).map(([k, v]) => (
                                <div key={k} className="flex items-center gap-2 text-xs font-mono">
                                  <span className="text-muted-foreground">{k}</span>
                                  <span className="text-muted-foreground">=</span>
                                  <span className="text-foreground">{v}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        <LinkEditor
                          label="Scope (requirements)" hint="Requirements this case evaluates." kind="requirement"
                          linked={c.scope || []}
                          options={requirements.map((r) => ({ id: r.id, name: r.name }))}
                          editable={editable}
                          onAdd={(id) => setLinks(c.id, { scope: [...(c.scope || []), id] })}
                          onRemove={(id) => setLinks(c.id, { scope: (c.scope || []).filter((x) => x !== id) })}
                          nameOf={(id) => reqNames.get(id) ?? ''}
                        />
                        <LinkEditor
                          label="Scope (components)" hint="Components this case evaluates." kind="component"
                          linked={c.scope_components || []}
                          options={components.map((x) => ({ id: x.id, name: x.name }))}
                          editable={editable}
                          onAdd={(id) => setLinks(c.id, { scope_components: [...(c.scope_components || []), id] })}
                          onRemove={(id) => setLinks(c.id, { scope_components: (c.scope_components || []).filter((x) => x !== id) })}
                          nameOf={(id) => compNames.get(id) ?? ''}
                        />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
