import { useEffect, useState, useMemo, useId } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Trash2, ArrowLeft, Save, X, ChevronRight, AlertTriangle, Tag } from 'lucide-react';
import { api, baselineNames, COMPONENT_TYPES, type Component, type Requirement, type VerificationCase, type Backlinks } from '../api/client';
import { CopyLinkButton, EntityLink, COMPONENT_TYPE_META, type EntityKind } from '../components/entities';
import { useEntityKinds } from '../components/entityIndex';
import { AutoLinkHtml } from '../components/autoLink';
import { ParameterEditor } from '../components/parametrics';
import ParametricsGuide from '../components/ParametricsGuide';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { useKeyboardShortcuts } from '../components/useKeyboardShortcuts';
import LoadingSplash from '../components/LoadingSplash';
import { LinkEditor } from '../components/LinkEditor';
import { HelpTip } from '../components/HelpTip';
import RichTextEditor from '../components/RichTextEditor';
import { HistoryPanel } from '../components/HistoryPanel';
import { CommentThread } from '../components/CommentThread';
import { useConfirm } from '../components/ConfirmDialog';
import { useToasts } from '../components/Toast';
import RenameDialog from '../components/RenameDialog';

/** Registry collection -> the entity kinds EntityLink knows how to render.
 *  Collections without a detail page of their own (decisions, analysis cases)
 *  fall back to a plain chip rather than linking somewhere that 404s. */
const BACKLINK_KINDS: Record<string, EntityKind> = {
  requirements: 'requirement',
  components: 'component',
  verification_cases: 'verification',
  specifications: 'specification',
  change_requests: 'change',
  risks: 'risk',
};

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

export default function ComponentDetailPage() {
  const { projectId, componentId } = useParams<{ projectId: string; componentId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canEdit());
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const entityKinds = useEntityKinds(projectId);
  const showConfirm = useConfirm();
  const { addToast } = useToasts();
  const descriptionId = useId();

  const [component, setComponent] = useState<Component | null>(null);
  const [allComponents, setAllComponents] = useState<Component[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<VerificationCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [projectBaselines, setProjectBaselines] = useState<string[]>([]);
  const [backlinks, setBacklinks] = useState<Backlinks | null>(null);

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
    api.getProject(projectId).then((p) => {
      setProjectBaselines(baselineNames(p.baselines));
    }).catch(() => {});
    api.getBacklinks(projectId, componentId)
      .then((b) => setBacklinks(b))
      .catch(() => setBacklinks(null));
  };

  useEffect(load, [projectId, componentId]);

  const save = async (data: Partial<Component>) => {
    if (!projectId || !componentId) return;
    setError('');
    try {
      // `component?.modified` is the version this form was populated from, so
      // the server can refuse a save that would overwrite someone else's edit
      // made since. Omitted when unknown, which behaves exactly as before.
      const updated = await api.updateComponent(projectId, componentId, data, component?.modified);
      setComponent(updated);
      addToast('success', `Component ${componentId} updated`);
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
    const ok = await showConfirm(warning, 'Delete Component', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    setError('');
    try {
      await api.deleteComponent(projectId, componentId);
      addToast('success', `Component ${componentId} deleted`);
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

  const [renaming, setRenaming] = useState(false);
  const [renamedTo, setRenamedTo] = useState<string | null>(null);

  const doRename = async (newId: string) => {
    if (!projectId || !componentId) throw new Error('No project/component');
    const res = await api.renameComponent(projectId, componentId, newId);
    bumpGraphVersion();
    // Navigating here would change `currentId` under the dialog, retriggering
    // its reset effect and wiping the result it is about to show. Follow the
    // record once the dialog closes instead.
    setRenamedTo(res.id);
    return res;
  };

  const closeRename = () => {
    setRenaming(false);
    if (renamedTo) {
      const target = renamedTo;
      setRenamedTo(null);
      navigate(`/project/${projectId}/components/${target}`, { replace: true });
    }
  };

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

  // A stored parent that names no component — a requirement id, or a component
  // since deleted. The select would otherwise render *blank*: assigning a value
  // no <option> carries sets selectedIndex to -1, which looks identical to an
  // unset field while the YAML holds something else entirely. Worse, the next
  // full-form save fails with "Parent component not found: <id>" against a box
  // that appears empty. Surfacing the value is what makes that reportable.
  const parentIsUnresolved = !!form.parent && !allComponents.some((c) => c.id === form.parent);

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
        <div className="mb-4 px-4 py-2 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
          <AlertTriangle size={14} /> {error}
          <button onClick={() => setError('')} className="ml-auto text-destructive/50 hover:text-destructive"><X size={14} /></button>
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
        {editable && (
          <button onClick={() => setRenaming(true)} className="btn-secondary text-xs p-2" title="Rename (change the id)">
            <Tag size={14} />
          </button>
        )}
        <button onClick={handleDelete} className="btn-danger" disabled={!editable} title="Delete">
          <Trash2 size={14} />
        </button>
      </div>

      <div className="grid grid-cols-1 @4xl:grid-cols-3 gap-6">
        {/* Main content area */}
        <div className="@4xl:col-span-2 space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
            <label className="label">Name
              <input
                className="input text-lg font-medium"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                onBlur={(e) => save({ name: e.target.value })}
                disabled={!editable}
              />
            </label>
            <label className="label mt-4" htmlFor={descriptionId}>Description</label>
            {editable ? (
              <RichTextEditor
                id={descriptionId}
                content={form.description || ''}
                onChange={(html) => setForm({ ...form, description: html })}
                // Saves on blur like every other field on this page (name,
                // quantity, part_number, supplier). Leaving this a no-op made
                // description the one field that needed "Save all changes".
                onBlur={(html) => save({ description: html })}
                placeholder="Write a component description…"
              />
            ) : (
              <div className="border rounded-lg p-3 min-h-[80px] opacity-90">
                {component.description ? <AutoLinkHtml html={component.description} kinds={entityKinds} /> : <span className="text-muted-foreground text-sm italic">No description</span>}
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
            id={componentId}
            references={[
              ...requirements.map((r) => ({ id: r.id, parameters: r.parameters || [] })),
              ...allComponents.map((c) => ({ id: c.id, parameters: c.parameters || [] })),
            ]}
          />
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.19 }} className="card p-5">
            <CommentThread entityKind="components" entityId={componentId!} />
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Change History</h2>
            <HistoryPanel itemId={componentId!} defaultOpen />
          </motion.div>
        </div>

        {/* Properties sidebar */}
        <div className="space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="card p-5">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Properties</h2>
            <div className="space-y-3">
              <div>
                <label className="label">Type
                  <select className="input" value={form.type} onChange={(e) => { setForm({ ...form, type: e.target.value }); save({ type: e.target.value }); }} disabled={!editable}>
                    {COMPONENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
              </div>
              <div>
                <label className="label">Parent component
                  <select
                    className={`input ${parentIsUnresolved ? 'border-destructive text-destructive' : ''}`}
                    value={form.parent}
                    onChange={(e) => { setForm({ ...form, parent: e.target.value }); save({ parent: e.target.value || null }); }}
                    disabled={!editable}
                  >
                    <option value="">(top level)</option>
                    {/* Shown only when the stored value resolves to nothing, so
                        the field states what it holds instead of going blank.
                        Disabled: it is not a choice, it is a report. */}
                    {parentIsUnresolved && (
                      <option value={form.parent} disabled>{form.parent} — not a component</option>
                    )}
                    {parentOptions.map((c) => (
                      // The type is part of the label because component names
                      // routinely match requirement group names — the seeded
                      // project has a component and a requirement both called
                      // "Wing Assembly" — and a bare name in this dropdown
                      // reads as a requirement group.
                      <option key={c.id} value={c.id}>{c.id} — {c.name} ({c.type})</option>
                    ))}
                  </select>
                </label>
                <HelpTip>A component's parent is always another component — this is design structure, not traceability. The link to requirements is “Satisfies requirements” above.</HelpTip>
                {parentIsUnresolved && (
                  <p className="text-xs text-destructive mt-1">
                    Stored parent <span className="font-mono">{form.parent}</span> is not a component. Pick a real parent, or (top level).
                  </p>
                )}
              </div>
              <div>
                <label className="label">Quantity
                  <input className="input" type="number" min={1} value={form.quantity}
                    onBlur={(e) => save({ quantity: Number(e.target.value) || 1 })}
                    onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) || 1 })}
                    disabled={!editable} />
                </label>
              </div>
              <div>
                <label className="label">Part number
                  <input className="input" value={form.part_number}
                    onChange={(e) => setForm({ ...form, part_number: e.target.value })}
                    onBlur={(e) => save({ part_number: e.target.value })}
                    disabled={!editable} />
                </label>
              </div>
              <div>
                <label className="label">Supplier
                  <input className="input" value={form.supplier}
                    onChange={(e) => setForm({ ...form, supplier: e.target.value })}
                    onBlur={(e) => save({ supplier: e.target.value })}
                    disabled={!editable} />
                </label>
              </div>
              <div>
                <span className="label">Baselines</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {projectBaselines.map((b) => {
                    const active = (component.baselines || []).includes(b);
                    return (
                      <button
                        key={b}
                        type="button"
                        onClick={() => {
                          const current = component.baselines || [];
                          const next = active ? current.filter(x => x !== b) : [...current, b];
                          save({ baselines: next });
                        }}
                        disabled={!editable}
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                          active
                            ? 'bg-primary/15 text-primary border-primary/30'
                            : 'bg-muted text-muted-foreground border-transparent hover:border-primary/20'
                        }`}
                      >
                        {b}
                      </button>
                    );
                  })}
                </div>
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
                    <EntityLink kind="component" id={c.id} name={c.name} subtype={c.type} className="hover:text-primary" />
                    <span className="text-muted-foreground">{c.type}{c.quantity > 1 ? ` ×${c.quantity}` : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>

          {/* Backlinks — everything that points at this component, computed
              server-side from the link registry. Read-only: each link is owned
              by the record holding it, so editing lives on that record's page. */}
          {backlinks && backlinks.total > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5">
              <h2 className="font-semibold text-sm text-card-foreground mb-1">Referenced By</h2>
              <p className="text-[11px] text-muted-foreground mb-3">
                {backlinks.total} record{backlinks.total === 1 ? '' : 's'} refer to this component.
                Deleting it will ask before breaking them.
              </p>
              <div className="space-y-2.5">
                {backlinks.groups.map((g) => (
                  <div key={g.collection}>
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                      {g.label}{g.items.length === 1 ? '' : 's'}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {g.items.map((it) => (
                        <span key={`${g.collection}-${it.id}`}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted text-xs"
                          title={it.label}>
                          {BACKLINK_KINDS[g.collection] ? (
                            <EntityLink kind={BACKLINK_KINDS[g.collection]} id={it.id}
                              name={it.name || undefined} className="hover:text-primary max-w-[180px]" />
                          ) : (
                            <span className="text-foreground truncate max-w-[180px]">
                              <span className="font-mono">{it.id}</span>{it.name ? ` — ${it.name}` : ''}
                            </span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

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

      <RenameDialog
        open={renaming}
        onClose={closeRename}
        currentId={componentId!}
        entityLabel="component"
        onRename={doRename}
      />
    </div>
  );
}
