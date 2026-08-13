import { useEffect, useState, useId } from 'react';
import { X, ArrowUp } from 'lucide-react';
import { api, type Requirement } from '../api/client';
import { useUndoStore } from '../store/undo';
import { useSelectedReq } from '../components/Layout';
import { REQUIREMENT_TYPES, REQUIREMENT_TYPE_META } from '../lib/requirementTypes';
import Modal from './Modal';

export type CreateIntent =
  | { mode: 'blank' }
  | { mode: 'child'; parent: string }
  | { mode: 'duplicate'; source: Requirement };

export default function CreateRequirementModal({
  open, onClose, projectId, requirements, onCreated, intent,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  requirements: Requirement[];
  onCreated: (created?: Requirement) => void;
  intent?: CreateIntent;
}) {
  const [form, setForm] = useState({ id: '', name: '', type: 'functional', priority: 'medium', parent: '', description: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { selectedReqId } = useSelectedReq();
  const parentId = useId();

  useEffect(() => {
    if (!open) return;
    setError('');

    // Build the whole form from the intent rather than spreading over whatever
    // was left behind. The form is only cleared after a *successful* create, so
    // spreading meant cancelling a duplicate and then opening a blank form left
    // the previous name and description sitting in the fields.
    const base = { id: '', name: '', type: 'functional', priority: 'medium', parent: '', description: '' };

    if (intent?.mode === 'duplicate') {
      const source = intent.source;
      const parent = source.parent || '';
      setForm({
        ...base,
        name: `${source.name} (copy)`,
        type: source.type,
        priority: source.priority,
        description: source.description || '',
        parent,
      });
      api.getNextUid(projectId, parent || undefined)
        .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
        .catch(() => {});
      return;
    }

    // An explicit child intent wins over the ambient selection.
    const parent = intent?.mode === 'child' ? intent.parent : (selectedReqId || '');
    setForm({ ...base, parent });
    api.getNextUid(projectId, parent || undefined)
      .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
      .catch(() => {});
  }, [open, projectId, selectedReqId, intent]);

  const jumpToParent = () => {
    if (!form.parent) return;
    const parentReq = requirements.find(r => r.id === form.parent);
    if (parentReq?.parent) {
      setForm((f) => ({ ...f, parent: parentReq.parent! }));
      api.getNextUid(projectId, parentReq.parent)
        .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
        .catch(() => {});
    } else {
      setForm((f) => ({ ...f, parent: '' }));
      api.getNextUid(projectId)
        .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
        .catch(() => {});
    }
  };

  const handleParentChange = (parentId: string) => {
    setForm((f) => ({ ...f, parent: parentId }));
    api.getNextUid(projectId, parentId || undefined)
      .then((uid) => setForm((f) => ({ ...f, id: uid.next_id })))
      .catch(() => {});
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.id.trim()) return;
    setBusy(true);
    setError('');
    try {
      const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      const createData = {
        ...form,
        description: form.description ? `<p>${esc(form.description)}</p>` : '',
        parent: form.parent || undefined,
      };
      const created = await api.createRequirement(projectId, createData);
      const createdId = created.id;
      useUndoStore.getState().push({
        description: `Create ${createdId}`,
        undo: async () => { await api.deleteRequirement(projectId, createdId); },
        redo: async () => { await api.createRequirement(projectId, createData); },
      });
      setForm({ id: '', name: '', type: 'functional', priority: 'medium', parent: '', description: '' });
      onClose();
      onCreated(created);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const parentOptions = [...requirements].sort((a, b) => a.id.localeCompare(b.id));

  const heading = intent?.mode === 'child' ? `New child of ${intent.parent}`
    : intent?.mode === 'duplicate' ? `Duplicate ${intent.source.id}`
    : 'New Requirement';

  return (
    <Modal open={open} onClose={onClose} align="top" topOffset="pt-[12vh]" panelClassName="w-full max-w-lg p-5">
      <form onSubmit={submit}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-foreground">{heading}</h2>
          <button type="button" onClick={onClose} className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent">
            <X size={15} />
          </button>
        </div>

            <div className="space-y-3">
              <div>
                <label className="label" htmlFor={parentId}>Parent</label>
                <div className="flex gap-1.5">
                  <select id={parentId} className="select flex-1" value={form.parent} onChange={(e) => handleParentChange(e.target.value)}>
                    <option value="">None (top level)</option>
                    {parentOptions.map((r) => (
                      <option key={r.id} value={r.id}>{r.id} — {r.name || 'Untitled'}</option>
                    ))}
                  </select>
                  <button type="button" onClick={jumpToParent}
                    className="p-2 rounded-md border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                    title="Jump to parent group"
                    disabled={!form.parent || !requirements.find(r => r.id === form.parent)}>
                    <ArrowUp size={14} />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-[8rem_1fr] gap-3">
                <div>
                  <label className="label">ID <input className="input font-mono" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} /></label>
                </div>
                <div>
                  {/* The name is the primary field of a create dialog the user just
                      opened — the id is auto-generated and the parent pre-selected,
                      so the name is what they type first. Modal otherwise lands focus
                      on the close button. */}
                  {/* oxlint-disable-next-line jsx-a11y/no-autofocus */}
                  <label className="label">Name <input className="input" placeholder="Requirement name" value={form.name} autoFocus
                    onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Type <select className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                    {REQUIREMENT_TYPES.map((k) => <option key={k} value={k}>{REQUIREMENT_TYPE_META[k].label}</option>)}
                  </select></label>
                </div>
                <div>
                  <label className="label">Priority <select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select></label>
                </div>
              </div>

              <div>
                <label className="label">Description <span className="normal-case font-normal">(optional)</span><textarea
                  className="input min-h-[72px] resize-y"
                  placeholder="Describe the requirement…"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                /></label>
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={busy || !form.id.trim()} className="btn-primary">
                {busy ? 'Creating…' : 'Create requirement'}
              </button>
            </div>
      </form>
    </Modal>
  );
}
