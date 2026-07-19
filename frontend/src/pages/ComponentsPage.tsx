import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, ChevronRight, Boxes, X, Save } from 'lucide-react';
import {
  api,
  COMPONENT_TYPES,
  type Component,
  type ComponentTreeNode,
  type Requirement,
  type VerificationCase,
} from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { COMPONENT_TYPE_META, CopyLinkButton, EntityLink, type EntityKind } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';
import { ParameterEditor } from '../components/parametrics';
import { HelpTip } from '../components/HelpTip';
import ParametricsGuide from '../components/ParametricsGuide';

const EMPTY_DRAFT = { id: '', name: '', type: 'assembly', parent: '' };

/** Ids of a component and everything beneath it — a component may not be
 *  reparented into its own branch, so those options must be excluded. */
function branchIds(components: Component[], rootId: string): Set<string> {
  const ids = new Set([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of components) {
      if (c.parent && ids.has(c.parent) && !ids.has(c.id)) {
        ids.add(c.id);
        grew = true;
      }
    }
  }
  return ids;
}

export default function ComponentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const dataVersion = useStore((s) => s.dataVersion);

  const [components, setComponents] = useState<Component[]>([]);
  const [tree, setTree] = useState<ComponentTreeNode[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<VerificationCase[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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

  useEffect(() => {
    if (!projectId) return;
    api.listRequirements(projectId).then(setRequirements).catch(() => {});
    api.listVerificationCases(projectId).then(setCases).catch(() => {});
  }, [projectId]);

  const selected = useMemo(
    () => components.find((c) => c.id === selectedId) ?? null,
    [components, selectedId],
  );

  // Arriving from a link elsewhere (?focus=SPAR): select it, and un-collapse
  // every ancestor — otherwise the target sits inside a closed branch and the
  // link appears to do nothing.
  const focusComponent = useCallback((id: string) => {
    setSelectedId(id);
    setCollapsed((prev) => {
      const next = new Set(prev);
      const byId = new Map(components.map((c) => [c.id, c]));
      let cursor = byId.get(id)?.parent ?? null;
      while (cursor) {
        next.delete(cursor);
        cursor = byId.get(cursor)?.parent ?? null;
      }
      return next;
    });
  }, [components]);

  useFocusedEntity(components.length > 0, focusComponent);

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

  const handleDelete = async (id: string) => {
    if (!projectId) return;
    const kids = components.filter((c) => c.parent === id).length;
    const warning = kids
      ? `Delete "${id}"? Its ${kids} child component(s) will move up to its parent.`
      : `Delete component "${id}"?`;
    if (!confirm(warning)) return;
    setError('');
    try {
      await api.deleteComponent(projectId, id);
      if (selectedId === id) setSelectedId(null);
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to delete component');
    }
  };

  const patch = async (id: string, data: Partial<Component>) => {
    if (!projectId) return;
    setError('');
    try {
      await api.updateComponent(projectId, id, data);
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to update component');
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
          onClick={() => setSelectedId(node.id)}
          className={`flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-colors ${
            selectedId === node.id ? 'bg-primary/10' : 'hover:bg-accent'
          }`}
          style={{ paddingLeft: depth * 20 + 8 }}
        >
          {/* Expansion lives on the chevron alone: the row itself selects. */}
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
              {node.satisfies.length} req
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
          <HelpTip>Components represent the physical design — what the system IS. Each component can satisfy requirements and carry numeric parameters for budget rollups (e.g. mass, current draw). Build a tree from system → subsystem → assembly → part to enable automated rollups in the parametrics engine.</HelpTip>
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
        // Wraps rather than shrinks: the graph pane can take ~40% of the
        // window, and a squeezed tree truncates every component name.
        <div className="flex flex-wrap gap-4 items-start">
          <div className="card p-2 flex-1 min-w-[280px]">
            {tree.map((node) => renderNode(node, 0))}
          </div>

          {selected && (
            <ComponentDetail
              key={selected.id}
              component={selected}
              components={components}
              requirements={requirements}
              cases={cases}
              editable={editable}
              onPatch={patch}
              onDelete={handleDelete}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

interface DetailProps {
  component: Component;
  components: Component[];
  requirements: Requirement[];
  cases: VerificationCase[];
  editable: boolean;
  onPatch: (id: string, data: Partial<Component>) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

function ComponentDetail({ component, components, requirements, cases, editable, onPatch, onDelete, onClose }: DetailProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const entityKinds = useEntityKinds(projectId);
  const [form, setForm] = useState({
    name: component.name,
    description: component.description,
    type: component.type,
    part_number: component.part_number,
    supplier: component.supplier,
    quantity: component.quantity,
    parent: component.parent ?? '',
  });

  const _orig = {name: component.name, description: component.description, type: component.type,
    part_number: component.part_number, supplier: component.supplier,
    quantity: component.quantity, parent: component.parent ?? ''};
  const dirty = editable && (
    form.name !== _orig.name || form.description !== _orig.description ||
    form.type !== _orig.type || form.part_number !== _orig.part_number ||
    form.supplier !== _orig.supplier || form.quantity !== _orig.quantity ||
    form.parent !== _orig.parent
  );

  // A component cannot be reparented into its own branch — the API rejects it,
  // so don't offer it.
  const ownBranch = branchIds(components, component.id);
  const parentOptions = components.filter((c) => !ownBranch.has(c.id));

  const link = (field: 'satisfies' | 'verification_cases', id: string) => {
    if (!id || component[field].includes(id)) return;
    onPatch(component.id, { [field]: [...component[field], id] });
  };
  const unlink = (field: 'satisfies' | 'verification_cases', id: string) => {
    onPatch(component.id, { [field]: component[field].filter((x) => x !== id) });
  };

  const nameOf = (id: string, list: { id: string; name: string }[]) =>
    list.find((x) => x.id === id)?.name ?? '';

  return (
    <motion.div
      initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
      className="card p-4 w-full sm:w-96 shrink-0 space-y-4"
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
            {component.id}
            <CopyLinkButton kind="component" id={component.id} />
          </div>
          <h2 className="font-semibold text-card-foreground truncate">{component.name || 'Untitled'}</h2>
        </div>
        <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground"><X size={16} /></button>
      </div>

      {editable ? (
        <>
          <div>
            <label className="label">Name</label>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input min-h-[60px]" value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="label">Type</label>
              <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="w-24">
              <label className="label">Qty</label>
              <input className="input" type="number" min={1} value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="label">Part number</label>
              <input className="input" value={form.part_number} onChange={(e) => setForm({ ...form, part_number: e.target.value })} />
            </div>
            <div className="flex-1">
              <label className="label">Supplier</label>
              <input className="input" value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="label">Parent</label>
            <select className="input" value={form.parent} onChange={(e) => setForm({ ...form, parent: e.target.value })}>
              <option value="">(top level)</option>
              {parentOptions.map((c) => <option key={c.id} value={c.id}>{c.id} — {c.name}</option>)}
            </select>
          </div>
          <button
            onClick={() => onPatch(component.id, { ...form, parent: form.parent || null })}
            className={`btn-primary w-full justify-center ${dirty ? 'ring-2 ring-amber-500/50' : ''}`}
          >
            <Save size={14} /> {dirty ? 'Save *' : 'Save'}
          </button>
        </>
      ) : (
        <dl className="text-sm space-y-1">
          {component.description && (
            <p className="text-muted-foreground"><AutoLinkText text={component.description} kinds={entityKinds} /></p>
          )}
          <div className="flex justify-between"><dt className="text-muted-foreground">Type</dt><dd>{component.type}</dd></div>
          <div className="flex justify-between"><dt className="text-muted-foreground">Quantity</dt><dd>{component.quantity}</dd></div>
          {component.parent && (
            <div className="flex justify-between items-center">
              <dt className="text-muted-foreground">Parent</dt>
              <dd><EntityLink kind="component" id={component.parent} className="text-xs hover:text-primary" /></dd>
            </div>
          )}
          {component.part_number && <div className="flex justify-between"><dt className="text-muted-foreground">Part number</dt><dd className="font-mono text-xs">{component.part_number}</dd></div>}
          {component.supplier && <div className="flex justify-between"><dt className="text-muted-foreground">Supplier</dt><dd>{component.supplier}</dd></div>}
        </dl>
      )}

      <ParametricsGuide />

      <ParameterEditor
        parameters={component.parameters || []}
        editable={editable}
        onChange={(next) => onPatch(component.id, { parameters: next })}
      />

      <LinkEditor
        label="Satisfies requirements"
        hint="What this component is here to deliver"
        kind="requirement"
        linked={component.satisfies}
        options={requirements}
        editable={editable}
        onAdd={(id) => link('satisfies', id)}
        onRemove={(id) => unlink('satisfies', id)}
        nameOf={(id) => nameOf(id, requirements)}
      />

      <LinkEditor
        label="Verification cases"
        hint="How this component is shown to work"
        kind="verification"
        linked={component.verification_cases}
        options={cases}
        editable={editable}
        onAdd={(id) => link('verification_cases', id)}
        onRemove={(id) => unlink('verification_cases', id)}
        nameOf={(id) => nameOf(id, cases)}
      />

      {editable && (
        <button
          onClick={() => onDelete(component.id)}
          className="btn-secondary w-full justify-center text-destructive hover:bg-destructive/10"
        >
          <Trash2 size={14} /> Delete component
        </button>
      )}
    </motion.div>
  );
}

interface LinkEditorProps {
  label: string;
  hint: string;
  kind: EntityKind;
  linked: string[];
  options: { id: string; name: string }[];
  editable: boolean;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
  nameOf: (id: string) => string;
}

/**
 * Linked entities render as chips that navigate to the entity itself; the
 * `<select>` below stays the way to add one, since an option in a native
 * dropdown can't be a link.
 */
function LinkEditor({ label, hint, kind, linked, options, editable, onAdd, onRemove, nameOf }: LinkEditorProps) {
  const available = options.filter((o) => !linked.includes(o.id));
  return (
    <div>
      <label className="label">{label}</label>
      <p className="text-[11px] text-muted-foreground -mt-1 mb-1.5">{hint}</p>
      {linked.length === 0 && <p className="text-xs text-muted-foreground italic mb-1.5">None linked</p>}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {linked.map((id) => (
          <span key={id} className="inline-flex items-center gap-1 pl-2 pr-1.5 py-0.5 rounded-full bg-muted text-xs">
            <EntityLink kind={kind} id={id} name={nameOf(id) || undefined} className="max-w-[140px] hover:text-foreground" />
            {editable && (
              <button onClick={() => onRemove(id)} className="text-muted-foreground hover:text-destructive" title="Unlink">
                <X size={11} />
              </button>
            )}
          </span>
        ))}
      </div>
      {editable && available.length > 0 && (
        <select className="input text-xs" value="" onChange={(e) => onAdd(e.target.value)}>
          <option value="">+ link…</option>
          {available.map((o) => <option key={o.id} value={o.id}>{o.id} — {o.name}</option>)}
        </select>
      )}
    </div>
  );
}
