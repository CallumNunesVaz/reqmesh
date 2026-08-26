import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePersistedState, setCodec } from '../hooks/usePersistedState';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, FileText, Trash2, ChevronDown, Square, CheckSquare, X, Search, ExternalLink, Edit3, Copy } from 'lucide-react';
import { api, type Requirement, type Component, type Specification } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { useToasts } from '../components/Toast';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { isSafeExternalUrl } from '../lib/safeUrl';
import { LinkEditor } from '../components/LinkEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useRangeSelection } from '../hooks/useRangeSelection';
import { useConfirm } from '../components/ConfirmDialog';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';

export default function SpecificationsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { specifications, setSpecifications } = useStore();
  const editable = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const dataVersion = useStore((s) => s.dataVersion);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [newSpec, setNewSpec] = useState({ id: '', name: '', description: '', url: '' });
  const [idExample, setIdExample] = useState('');
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [loading, setLoading] = useState(true);
  // Persisted per project — see RequirementsPage/ComponentsPage for why.
  const pk = (field: string) => (projectId ? `rt-specs-${field}-${projectId}` : null);
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [expanded, setExpanded] = usePersistedState<Set<string>>(pk('expanded'), new Set(), setCodec<string>());
  const entityKinds = useEntityKinds(projectId);

  const load = () => {
    if (!projectId) return;
    api.listSpecifications(projectId).then(setSpecifications).catch(console.error)
      .finally(() => setLoading(false));
    api.listRequirements(projectId).then(setRequirements).catch(() => {});
    api.listComponents(projectId).then(setComponents).catch(() => {});
  };

 // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [projectId, dataVersion]);

  const reqNames = useMemo(() => new Map(requirements.map((r) => [r.id, r.name])), [requirements]);
  const specNames = useMemo(() => new Map(specifications.map((s) => [s.id, s.name])), [specifications]);

  const filteredSpecs = useMemo(() => {
    if (!search) return specifications;
    const q = search.toLowerCase();
    return specifications.filter((s) =>
      s.id.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q),
    );
  }, [specifications, search]);
  const filtering = !!search;

  const toggleExpand = (specId: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(specId)) next.delete(specId);
      else next.add(specId);
      return next;
    });

  // Landing here from a link elsewhere (?focus=SRS-001): open the card too,
  // so the contents the link pointed towards are actually visible.
  const focusId = useFocusedEntity(
    specifications.length > 0,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useCallback((id: string) => setExpanded((prev) => new Set(prev).add(id)), []),
  );

  const openCreate = () => {
    setEditingId(null);
    setNewSpec({ id: '', name: '', description: '', url: '' });
    setShowCreate(true);
    if (!projectId) return;
    api.getNextId(projectId, 'specifications')
      .then((r) => {
        setNewSpec((v) => (v.id ? v : { ...v, id: r.next_id }));
        setIdExample(r.next_id);
      })
      .catch(() => {});
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !editable) return;
    try {
      if (editingId) {
        if (!newSpec.id.trim()) return;
        await api.updateSpecification(projectId, editingId, {
          name: newSpec.name, description: newSpec.description, url: newSpec.url,
        });
        addToast('success', `Specification ${editingId} updated`);
      } else {
        if (!newSpec.id.trim()) return;
        await api.createSpecification(projectId, newSpec);
        addToast('success', `Specification ${newSpec.id.trim()} created`);
      }
      setShowCreate(false);
      setEditingId(null);
      setNewSpec({ id: '', name: '', description: '', url: '' });
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to save specification');
    }
  };

  const openEdit = (spec: Specification) => {
    setNewSpec({
      id: spec.id,
      name: spec.name || '',
      description: spec.description || '',
      url: spec.url || '',
    });
    setEditingId(spec.id);
    setShowCreate(true);
  };

  const handleDuplicate = async (spec: Specification) => {
    if (!projectId) return;
    const existing = new Set(specifications.map((s) => s.id));
    // Numbered from 1, not bare `-copy`, because the project's naming
    // standard is enforced on create and a numeric-suffix scheme refuses an
    // id that does not end in a digit. `-copy` was silently rejected with a
    // 422 the moment enforcement went in, which broke Duplicate outright.
    let n = 1;
    let id = `${spec.id}-copy${n}`;
    while (existing.has(id)) { id = `${spec.id}-copy${++n}`; }
    try {
      await api.createSpecification(projectId, {
        id,
        name: `${spec.name} (copy)`,
        description: spec.description,
        url: spec.url,
      });
      addToast('success', `Specification ${id} created`);
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to duplicate specification');
    }
  };

  const setSpecComponents = async (specId: string, linked: string[]) => {
    if (!projectId) return;
    setSpecifications(specifications.map((s) => (s.id === specId ? { ...s, components: linked } : s)));
    try {
      await api.updateSpecification(projectId, specId, { components: linked } as any);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Save failed');
      load();
    }
  };

  const showConfirm = useConfirm();

  const handleDelete = async (specId: string) => {
    if (!projectId) return;
    const ok = await showConfirm(`Delete specification ${specId}?`, 'Delete Specification', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    await api.deleteSpecification(projectId, specId);
    setSpecifications(specifications.filter((s) => s.id !== specId));
    addToast('success', `Specification ${specId} deleted`);
  };

  // `filteredSpecs` is the list as displayed, which is the only ordering a
  // Shift range may span.
  const { selectedIds, select: toggleSpec, setSelectedIds } =
    useRangeSelection(useMemo(() => filteredSpecs.map((s) => s.id), [filteredSpecs]));
  const clearSpecSelection = () => setSelectedIds(new Set());

  const { runBulkDelete } = useBulkActions({
    clearSelection: clearSpecSelection,
    reload: load,
  });
  const selectAllSpecs = () => setSelectedIds(new Set(filteredSpecs.map(s => s.id)));

  const handleBulkSpecDelete = async () => {
    if (!projectId) return;
    const ids = [...selectedIds];
    const saved = specifications.filter((s) => selectedIds.has(s.id)).map((s) => ({ ...s }));
    await runBulkDelete({
      noun: 'specification',
      ids,
      saved,
      idOf: (s) => s.id,
      remove: (idsToRemove) => api.bulkDeleteSpecifications(projectId, idsToRemove),
      recreate: (item) => api.createSpecification(projectId, item),
    });
  };

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && specifications.length === 0 && <LoadingSplash label="Loading specifications…" />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Specifications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filteredSpecs.length} of ${specifications.length} specifications` : `${specifications.length} specifications`}
          </p>
        </div>
        {editable && (
        <button onClick={openCreate} className="btn-primary">
          <Plus size={16} /> New Specification
        </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="input pl-9 pr-14 h-9"
              placeholder="Search specifications…"
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
        </div>
      </div>

      <AnimatePresence>
        {showCreate && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate}
            className="card p-4 mb-4 overflow-hidden"
          >
            <div className="flex items-end gap-3">
              <div className="w-40">
                <label className="label">ID
                  <input className="input font-mono" placeholder="SRS-001" value={newSpec.id} onChange={(e) => setNewSpec({ ...newSpec, id: e.target.value })} disabled={!!editingId} />
                </label>
                {!editingId && idExample && <span className="text-[10px] text-muted-foreground">e.g. {idExample}</span>}
              </div>
              <div className="flex-1">
                <label className="label">Name
                  <input className="input" placeholder="Specification name" value={newSpec.name} onChange={(e) => setNewSpec({ ...newSpec, name: e.target.value })} />
                </label>
              </div>
              <div className="w-60">
                <label className="label">Source URL
                  <input className="input" placeholder="https://…" value={newSpec.url} onChange={(e) => setNewSpec({ ...newSpec, url: e.target.value })} />
                </label>
              </div>
              <button type="submit" className="btn-primary">{editingId ? 'Save' : 'Create'}</button>
              <button type="button" onClick={() => { setShowCreate(false); setEditingId(null); setNewSpec({ id: '', name: '', description: '', url: '' }); }} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {filteredSpecs.length === 0 ? (
        <div className="card p-12 text-center">
          <FileText size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">
            {filtering ? 'No specifications match your filters.' : 'No specifications yet'}
          </p>
          {filtering ? (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => setSearch('')}>Clear filters</button>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">Create your first specification to organize requirements.</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredSpecs.map((spec, i) => {
            const isExpanded = expanded.has(spec.id);
            return (
            <motion.div
              key={spec.id}
              id={`entity-${spec.id}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className={`card hover:shadow-md transition-shadow group ${
                focusId === spec.id ? 'ring-2 ring-primary/50' : ''
              }`}
            >
              <div className="flex items-center gap-3 p-4">
                {editable && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); toggleSpec(spec.id, e); }}
                    aria-pressed={selectedIds.has(spec.id)}
                    aria-label="Select specification"
                    className="shrink-0 cursor-pointer"
                  >
                    {selectedIds.has(spec.id) ? (
                      <CheckSquare size={14} className="text-primary" />
                    ) : (
                      <Square size={14} className="text-muted-foreground/40 hover:text-muted-foreground" />
                    )}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => toggleExpand(spec.id)}
                  aria-expanded={isExpanded}
                  className="flex flex-1 min-w-0 items-center gap-3 text-left cursor-pointer"
                >
                  <div className="w-9 h-9 bg-cs-amber/10 text-cs-amber rounded-lg flex items-center justify-center shrink-0">
                    <FileText size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{spec.id}</span>
                      <h3 className="font-medium text-card-foreground">{spec.name || 'Untitled'}</h3>
                      <CopyLinkButton kind="specification" id={spec.id} className="opacity-0 group-hover:opacity-100" />
                    </div>
                    {spec.description && (
                      <p className="text-sm text-muted-foreground mt-0.5 line-clamp-1">
                        <AutoLinkText text={spec.description} kinds={entityKinds} />
                      </p>
                    )}
                    <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                      <span>{spec.requirements.length} requirements</span>
                      <span>{spec.children.length} sub-specs</span>
                      {spec.url && isSafeExternalUrl(spec.url) && (
                        <a
                          href={spec.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline inline-flex items-center gap-1"
                        >
                          <ExternalLink size={12} /> Source
                        </a>
                      )}
                    </div>
                  </div>
                </button>
                {editable && (
                  <>
                <button
                  onClick={() => handleDuplicate(spec)}
                  className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all"
                  title="Duplicate specification"
                >
                  <Copy size={14} />
                </button>
                <button
                  onClick={() => openEdit(spec)}
                  className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all"
                  title="Edit"
                >
                  <Edit3 size={14} />
                </button>
                <button
                  onClick={() => handleDelete(spec.id)}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => toggleExpand(spec.id)}
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
                        <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Requirements</h4>
                        {spec.requirements.length === 0 ? (
                          <p className="text-xs text-muted-foreground">None assigned.</p>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {spec.requirements.map((rid) => (
                              <span key={rid} className="inline-flex items-center px-2 py-1 rounded-md bg-muted text-xs">
                                <EntityLink kind="requirement" id={rid} name={reqNames.get(rid)} className="max-w-[240px] hover:text-primary" />
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <LinkEditor
                          label="Components" hint="" kind="component"
                          linked={(spec.components || [])}
                          options={components}
                          editable={editable}
                          onAdd={(id) => setSpecComponents(spec.id, [...(spec.components || []), id])}
                          onRemove={(id) => setSpecComponents(spec.id, (spec.components || []).filter((x) => x !== id))}
                          nameOf={(id) => components.find((c) => c.id === id)?.name ?? ''}
                        />
                      </div>
                      {spec.children.length > 0 && (
                        <div>
                          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Sub-specifications</h4>
                          <div className="flex flex-wrap gap-1.5">
                            {spec.children.map((cid) => (
                              <span key={cid} className="inline-flex items-center px-2 py-1 rounded-md bg-muted text-xs">
                                <EntityLink kind="specification" id={cid} name={specNames.get(cid)} className="max-w-[240px] hover:text-primary" />
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="pt-3 border-t border-border">
                        <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Comments</h4>
                        <CommentThread entityKind="specifications" entityId={spec.id} />
                      </div>
                      <div className="pt-3 border-t border-border">
                        <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Change History</h4>
                        <HistoryPanel itemId={spec.id} />
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
          onSelectAll={selectAllSpecs}
          onClear={clearSpecSelection}
        >
          <button onClick={handleBulkSpecDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
        </BulkActionBar>
      )}
    </div>
  );
}
