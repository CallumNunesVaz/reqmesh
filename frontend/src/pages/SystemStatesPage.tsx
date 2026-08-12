import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, Edit3, Check, X, Layers, Loader, AlertTriangle } from 'lucide-react';
import { api, type SystemStateDef } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useConfirm } from '../components/ConfirmDialog';

export default function SystemStatesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [states, setStates] = useState<SystemStateDef[]>([]);
  const [orphans, setOrphans] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const editable = useAuthStore((s) => s.canEdit());
  const showConfirm = useConfirm();

  // Create / edit form state
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [editingName, setEditingName] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await api.listSystemStates(projectId);
      setStates(data.states);
      setOrphans(data.orphans);
    } catch (err: any) {
      setError(err.message || 'Failed to load system states');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const openCreate = (prefillName?: string) => {
    setFormName(prefillName || '');
    setFormDesc('');
    setEditingName(null);
    setShowForm(true);
  };

  const openEdit = (s: SystemStateDef) => {
    setFormName(s.name);
    setFormDesc(s.description);
    setEditingName(s.name);
    setShowForm(true);
  };

  const save = async () => {
    if (!projectId || !formName.trim()) return;
    setFormSaving(true);
    setError('');
    try {
      if (editingName) {
        await api.updateSystemState(projectId, editingName, {
          name: formName.trim() !== editingName ? formName.trim() : undefined,
          description: formDesc,
        });
      } else {
        await api.createSystemState(projectId, {
          name: formName.trim(),
          description: formDesc,
        });
      }
      setShowForm(false);
      await load();
    } catch (err: any) {
      setError(err.message || 'Save failed');
    } finally {
      setFormSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!projectId) return;
    const ok = await showConfirm(
      `Delete system state "${name}"? This does not remove it from requirements — those will become undefined.`,
      'Delete System State',
      { resultLabel: 'Delete', destructive: true },
    );
    if (!ok) return;
    try {
      const res = await api.deleteSystemState(projectId, name);
      if (res.requirements_affected > 0) {
        setError(`Deleted "${name}" — ${res.requirements_affected} requirement${res.requirements_affected !== 1 ? 's' : ''} now reference an undefined state.`);
      }
      await load();
    } catch (err: any) {
      setError(err.message || 'Delete failed');
    }
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
            <h1 className="text-2xl font-bold text-card-foreground">System States</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              System states represent operational modes or phases a requirement applies to.
              Define them here so the requirement editor can offer a picker rather than a
              free-text box where a typo silently creates a state nobody can find again.
            </p>
          </div>
          {editable && (
            <button onClick={() => openCreate()} className="btn-primary gap-1.5">
              <Plus size={16} /> New State
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
                  {editingName ? `Edit "${editingName}"` : 'New System State'}
                </h3>
                <div>
                  <label className="label">Name *</label>
                  <input
                    className="input"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. takeoff, cruise, landing"
                    disabled={formSaving}
                    onKeyDown={(e) => { if (e.key === 'Enter') save(); }}
                  />
                </div>
                <div>
                  <label className="label">Description</label>
                  <textarea
                    className="input min-h-[80px] resize-y"
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    placeholder="Describe this operational mode or system phase"
                    disabled={formSaving}
                  />
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
                    onClick={save}
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

        {/* Orphans section */}
        {orphans.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-4 border-l-2 border-l-cs-orange"
          >
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={16} className="text-cs-orange" />
              <h3 className="font-semibold text-sm">Undefined States</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-3">
              These names are used by one or more requirements but are not defined here.
              A typo in a free-text field creates a state nobody can find again — define it
              to make it visible in the picker.
            </p>
            <div className="flex flex-wrap gap-2">
              {orphans.map((name) => (
                <div key={name} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-cs-orange/10 border border-cs-orange/20 text-sm">
                  <span className="font-mono text-cs-orange">{name}</span>
                  {editable && (
                    <button
                      onClick={() => openCreate(name)}
                      className="p-0.5 rounded hover:bg-cs-orange/20 transition-colors text-cs-orange"
                      title={`Define "${name}"`}
                    >
                      <Plus size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* State list */}
        {states.length === 0 && orphans.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Layers size={32} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">No system states defined yet.</p>
            {editable && (
              <p className="text-xs mt-1">
                Define system states so the requirement editor can offer a picker.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {states.map((s) => (
              <motion.div
                key={s.name}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="card p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-muted text-muted-foreground text-[10px] font-mono">
                        {s.order}
                      </span>
                      <h3 className="font-semibold text-card-foreground font-mono">{s.name}</h3>
                    </div>
                    {s.description && (
                      <p className="text-sm text-muted-foreground mt-1 opacity-80">
                        {s.description}
                      </p>
                    )}
                  </div>

                  {editable && (
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => openEdit(s)}
                        className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="Edit state"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(s.name)}
                        className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        title="Delete state"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
