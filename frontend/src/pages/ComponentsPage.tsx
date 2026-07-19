import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ChevronRight, Boxes } from 'lucide-react';
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
  const dataVersion = useStore((s) => s.dataVersion);

  const [components, setComponents] = useState<Component[]>([]);
  const [tree, setTree] = useState<ComponentTreeNode[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [error, setError] = useState('');

  const load = () => {
    if (!projectId) return;
    Promise.all([api.listComponents(projectId), api.getComponentTree(projectId)])
      .then(([list, t]) => { setComponents(list); setTree(t); })
      .catch((e) => setError(e.message));
  };

  useEffect(load, [projectId, dataVersion]);

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

  const renderNode = (node: ComponentTreeNode, depth: number): React.ReactNode => {
    const hasKids = node.children.length > 0;
    const isCollapsed = collapsed.has(node.id);
    const typeMeta = COMPONENT_TYPE_META[node.type] || COMPONENT_TYPE_META.assembly;
    const TypeIcon = typeMeta.icon;
    return (
      <div key={node.id}>
        <div
          id={`entity-${node.id}`}
          onClick={() => navigate(`/project/${projectId}/components/${node.id}`)}
          className="flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-colors hover:bg-accent"
          style={{ paddingLeft: depth * 20 + 8 }}
        >
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
            {components.length} components — the synthesised design
          </p>
        </div>
        {editable && (
          <button onClick={() => { setShowCreate((s) => !s); setError(''); }} className="btn-primary">
            <Plus size={16} /> New Component
          </button>
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

      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}

      {components.length === 0 ? (
        <div className="card p-12 text-center">
          <Boxes size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No components yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Components describe what the system <i>is</i>, and map onto the requirements they satisfy.
          </p>
        </div>
      ) : (
        <div className="card p-2 flex-1 min-w-[280px]">
          {tree.map((node) => renderNode(node, 0))}
        </div>
      )}
    </div>
  );
}
