import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, FileText, Trash2, ChevronDown, Square, CheckSquare, X } from 'lucide-react';
import { api, type Requirement } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';

export default function SpecificationsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { specifications, setSpecifications } = useStore();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const dataVersion = useStore((s) => s.dataVersion);
  const [showCreate, setShowCreate] = useState(false);
  const [newSpec, setNewSpec] = useState({ id: '', name: '', description: '' });
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const entityKinds = useEntityKinds(projectId);

  const load = () => {
    if (!projectId) return;
    api.listSpecifications(projectId).then(setSpecifications).catch(console.error);
    api.listRequirements(projectId).then(setRequirements).catch(() => {});
  };

  useEffect(load, [projectId, dataVersion]);

  const reqNames = useMemo(() => new Map(requirements.map((r) => [r.id, r.name])), [requirements]);
  const specNames = useMemo(() => new Map(specifications.map((s) => [s.id, s.name])), [specifications]);

  const toggleExpand = (specId: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(specId) ? next.delete(specId) : next.add(specId);
      return next;
    });

  // Landing here from a link elsewhere (?focus=SRS-001): open the card too,
  // so the contents the link pointed towards are actually visible.
  const focusId = useFocusedEntity(
    specifications.length > 0,
    useCallback((id: string) => setExpanded((prev) => new Set(prev).add(id)), []),
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !newSpec.id.trim() || !editable) return;
    try {
      await api.createSpecification(projectId, newSpec);
      setShowCreate(false);
      setNewSpec({ id: '', name: '', description: '' });
      load();
    } catch {
      // silently no-op when permissions insufficient
    }
  };

  const handleDelete = async (specId: string) => {
    if (!projectId) return;
    if (!confirm(`Delete specification ${specId}?`)) return;
    await api.deleteSpecification(projectId, specId);
    setSpecifications(specifications.filter((s) => s.id !== specId));
  };

  const toggleSpec = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSpecSelection = () => setSelectedIds(new Set());
  const selectAllSpecs = () => setSelectedIds(new Set(specifications.map(s => s.id)));

  const handleBulkSpecDelete = async () => {
    if (!projectId) return;
    if (!confirm(`Delete ${selectedIds.size} specification(s)?`)) return;
    await api.bulkDeleteSpecifications(projectId, [...selectedIds]);
    clearSpecSelection();
    load();
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Specifications</h1>
          <p className="text-sm text-muted-foreground mt-1">{specifications.length} specifications</p>
        </div>
        {editable && (
        <button onClick={() => setShowCreate(!showCreate)} className="btn-primary">
          <Plus size={16} /> New Specification
        </button>
        )}
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
                <label className="label">ID</label>
                <input className="input font-mono" placeholder="SRS-001" value={newSpec.id} onChange={(e) => setNewSpec({ ...newSpec, id: e.target.value })} autoFocus />
              </div>
              <div className="flex-1">
                <label className="label">Name</label>
                <input className="input" placeholder="Specification name" value={newSpec.name} onChange={(e) => setNewSpec({ ...newSpec, name: e.target.value })} />
              </div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {specifications.length === 0 ? (
        <div className="card p-12 text-center">
          <FileText size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No specifications yet</p>
          <p className="text-sm text-muted-foreground mt-1">Create your first specification to organize requirements.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {specifications.map((spec, i) => {
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
              <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => toggleExpand(spec.id)}>
                {editable && (
                  <span className="shrink-0" onClick={(e) => e.stopPropagation()}>
                    {selectedIds.has(spec.id) ? (
                      <CheckSquare size={14} className="text-primary cursor-pointer" onClick={() => toggleSpec(spec.id)} />
                    ) : (
                      <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={() => toggleSpec(spec.id)} />
                    )}
                  </span>
                )}
                <div className="w-9 h-9 bg-amber-500/10 text-amber-400 rounded-lg flex items-center justify-center">
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
                  </div>
                </div>
                {editable && (
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(spec.id); }}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={14} />
                </button>
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
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <button onClick={handleBulkSpecDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
          <button onClick={selectAllSpecs} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearSpecSelection} className="text-[10px] text-muted-foreground hover:text-foreground"><X size={13} /></button>
        </div>
      )}
    </div>
  );
}
