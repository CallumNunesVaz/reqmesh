import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Trash2, ArrowLeft, Save, X, ChevronRight, CheckCircle2 } from 'lucide-react';
import { api, COMPONENT_TYPES, type Component, type Requirement, type VerificationCase } from '../api/client';
import { CopyLinkButton, EntityLink, COMPONENT_TYPE_META, type EntityKind } from '../components/entities';
import { useEntityKinds } from '../components/entityIndex';
import { AutoLinkText } from '../components/autoLink';
import { ParameterEditor } from '../components/parametrics';
import ParametricsGuide from '../components/ParametricsGuide';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import LoadingSplash from '../components/LoadingSplash';

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

/* Linked entities render as chips that navigate to the entity itself */
function LinkEditor({ label, hint, kind, linked, options, editable, onAdd, onRemove, nameOf }: {
  label: string; hint: string; kind: EntityKind;
  linked: string[]; options: { id: string; name: string }[];
  editable: boolean; onAdd: (id: string) => void; onRemove: (id: string) => void;
  nameOf: (id: string) => string;
}) {
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

export default function ComponentDetailPage() {
  const { projectId, componentId } = useParams<{ projectId: string; componentId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const entityKinds = useEntityKinds(projectId);

  const [component, setComponent] = useState<Component | null>(null);
  const [allComponents, setAllComponents] = useState<Component[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<VerificationCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [form, setForm] = useState({
    name: '', description: '', type: 'assembly', part_number: '', supplier: '',
    quantity: 1, parent: '',
  });

  const load = () => {
    if (!projectId || !componentId) return;
    setLoading(true);
    Promise.all([
      api.getComponent(projectId, componentId),
      api.listComponents(projectId),
      api.listRequirements(projectId),
      api.listVerificationCases(projectId),
    ]).then(([comp, comps, reqs, vcs]) => {
      if (!comp) { setError('Component not found'); return; }
      setComponent(comp);
      setAllComponents(comps.filter((c) => c.id !== componentId));
      setRequirements(reqs);
      setCases(vcs);
      setForm({
        name: comp.name, description: comp.description, type: comp.type,
        part_number: comp.part_number, supplier: comp.supplier,
        quantity: comp.quantity, parent: comp.parent ?? '',
      });
      setLoading(false);
    }).catch((err) => { setError(err.message); setLoading(false); });
  };

  useEffect(load, [projectId, componentId]);

  const save = async (data: Partial<Component>) => {
    if (!projectId || !componentId) return;
    setError('');
    try {
      const updated = await api.updateComponent(projectId, componentId, data);
      setComponent(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      bumpGraphVersion();
    } catch (err: any) {
      setError(err.message || 'Save failed');
      setTimeout(() => setError(''), 5000);
    }
  };

  const handleDelete = async () => {
    if (!projectId || !componentId) return;
    const kids = allComponents.filter((c) => c.parent === componentId).length;
    const warning = kids
      ? `Delete "${componentId}"? Its ${kids} child component(s) will move up to its parent.`
      : `Delete component "${componentId}"?`;
    if (!confirm(warning)) return;
    setError('');
    try {
      await api.deleteComponent(projectId, componentId);
      navigate(`/project/${projectId}/components`);
    } catch (err: any) {
      setError(err.message || 'Failed to delete component');
    }
  };

  useKeyboardShortcuts(projectId, {
    onDetailSave: () => component && save({ ...form, parent: form.parent || null }),
    onDetailDelete: handleDelete,
    onDetailEscape: () => { if (window.history.length > 1) navigate(-1); else navigate(`/project/${projectId}/components`); },
  });

  const link = (field: 'satisfies' | 'verification_cases', id: string) => {
    if (!component || component[field].includes(id)) return;
    save({ [field]: [...component[field], id] } as any);
  };
  const unlink = (field: 'satisfies' | 'verification_cases', id: string) => {
    if (!component) return;
    save({ [field]: component[field].filter((x) => x !== id) } as any);
  };
  const nameOf = (id: string, list: { id: string; name: string }[]) =>
    list.find((x) => x.id === id)?.name ?? '';

  const ownBranch = component ? branchIds(allComponents, component.id) : new Set<string>();
  const parentOptions = allComponents.filter((c) => !ownBranch.has(c.id));

  // Ancestor chain for breadcrumb
  const ancestors = useMemo(() => {
    if (!component) return [];
    const chain = [];
    let cursor = component.parent;
    const byId = new Map(allComponents.map((c) => [c.id, c]));
    const visited = new Set<string>();
    while (cursor && !visited.has(cursor)) {
      visited.add(cursor);
      const c = byId.get(cursor);
      if (c) { chain.unshift(c); cursor = c.parent ?? null; }
      else break;
    }
    return chain;
  }, [component, allComponents]);

  if (loading) {
    return <div className="relative h-[60vh]"><LoadingSplash label="Loading component…" /></div>;
  }

  if (!component) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground">{error || 'Component not found.'}</p>
        <button onClick={() => navigate(`/project/${projectId}/components`)} className="btn-secondary mt-4">
          <ArrowLeft size={14} /> Back to components
        </button>
      </div>
    );
  }

  const typeMeta = COMPONENT_TYPE_META[component.type] || COMPONENT_TYPE_META.assembly;
  const TypeIcon = typeMeta.icon;

  return (
    <div className="max-w-4xl mx-auto p-8">
      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2">
          <Trash2 size={14} /> {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400/50 hover:text-red-400"><X size={14} /></button>
        </div>
      )}
      {saveSuccess && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm flex items-center gap-2">
          <CheckCircle2 size={14} /> Saved
        </div>
      )}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/project/${projectId}/components`)} className="btn-secondary p-2">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          {ancestors.length > 0 && (
            <nav className="flex items-center gap-1 text-[11px] text-muted-foreground mb-0.5 flex-wrap">
              {ancestors.map((a) => (
                <span key={a.id} className="inline-flex items-center gap-1">
                  <EntityLink kind="component" id={a.id} showIcon={false} className="hover:text-primary" />
                  <ChevronRight size={10} className="shrink-0" />
                </span>
              ))}
            </nav>
          )}
          <div className="flex items-center gap-2">
            <TypeIcon size={16} className={typeMeta.cls} />
            <h1 className="text-xl font-bold tracking-tight font-mono text-foreground">{component.id}</h1>
            <CopyLinkButton kind="component" id={component.id} />
          </div>
        </div>
        <button onClick={handleDelete} className="btn-danger" disabled={!editable}>
          <Trash2 size={14} /> Delete
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main content area */}
        <div className="lg:col-span-2 space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
            <label className="label">Name</label>
            <input
              className="input text-lg font-medium"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              onBlur={(e) => save({ name: e.target.value })}
              disabled={!editable}
            />
            <label className="label mt-4">Description</label>
            {editable ? (
              <textarea
                className="input min-h-[80px]"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                onBlur={(e) => save({ description: e.target.value })}
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[80px] opacity-90">
                {component.description ? <AutoLinkText text={component.description} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No description</span>}
              </div>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5">
            <LinkEditor label="Satisfies requirements" hint="What this component exists to deliver" kind="requirement"
              linked={component.satisfies || []} options={requirements} editable={editable}
              onAdd={(id) => link('satisfies', id)} onRemove={(id) => unlink('satisfies', id)}
              nameOf={(id) => nameOf(id, requirements)} />
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card p-5">
            <LinkEditor label="Verification cases" hint="How this component is verified" kind="verification"
              linked={component.verification_cases || []} options={cases} editable={editable}
              onAdd={(id) => link('verification_cases', id)} onRemove={(id) => unlink('verification_cases', id)}
              nameOf={(id) => nameOf(id, cases)} />
          </motion.div>

          <ParametricsGuide />
          <ParameterEditor
            parameters={component.parameters || []}
            editable={editable}
            onChange={(next) => save({ parameters: next as any })}
          />
        </div>

        {/* Properties sidebar */}
        <div className="space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Properties</h2>
            <div className="space-y-3">
              <div>
                <label className="label">Type</label>
                <select className="input" value={form.type} onChange={(e) => { setForm({ ...form, type: e.target.value }); save({ type: e.target.value }); }} disabled={!editable}>
                  {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Parent</label>
                <select className="input" value={form.parent} onChange={(e) => { setForm({ ...form, parent: e.target.value }); save({ parent: e.target.value || null }); }} disabled={!editable}>
                  <option value="">(top level)</option>
                  {parentOptions.map((c) => <option key={c.id} value={c.id}>{c.id} — {c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Quantity</label>
                <input className="input" type="number" min={1} value={form.quantity}
                  onBlur={(e) => save({ quantity: Number(e.target.value) || 1 })}
                  onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) || 1 })}
                  disabled={!editable} />
              </div>
              <div>
                <label className="label">Part number</label>
                <input className="input" value={form.part_number}
                  onChange={(e) => setForm({ ...form, part_number: e.target.value })}
                  onBlur={(e) => save({ part_number: e.target.value })}
                  disabled={!editable} />
              </div>
              <div>
                <label className="label">Supplier</label>
                <input className="input" value={form.supplier}
                  onChange={(e) => setForm({ ...form, supplier: e.target.value })}
                  onBlur={(e) => save({ supplier: e.target.value })}
                  disabled={!editable} />
              </div>
            </div>
          </motion.div>

          {/* Backlinks — children */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Children</h2>
            {allComponents.filter((c) => c.parent === componentId).length === 0 ? (
              <p className="text-xs text-muted-foreground">No children</p>
            ) : (
              <div className="space-y-1">
                {allComponents.filter((c) => c.parent === componentId).map((c) => (
                  <div key={c.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                    <EntityLink kind="component" id={c.id} name={c.name} className="hover:text-primary" />
                    <span className="text-muted-foreground">{c.type}{c.quantity > 1 ? ` ×${c.quantity}` : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>

          {editable && (
            <button onClick={() => { const d = form; save({ ...d, parent: d.parent || null } as any); }} className="btn-primary w-full justify-center">
              <Save size={14} /> Save all changes
            </button>
          )}

          <div className="text-xs text-muted-foreground space-y-1">
            <div>Created: {new Date(component.created).toLocaleString()}</div>
            <div>Modified: {new Date(component.modified).toLocaleString()}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
