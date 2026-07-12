import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, FileText, Trash2 } from 'lucide-react';
import { api, type Specification } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';

export default function SpecificationsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { specifications, setSpecifications } = useStore();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [showCreate, setShowCreate] = useState(false);
  const [newSpec, setNewSpec] = useState({ id: '', name: '', description: '' });

  const load = () => {
    if (!projectId) return;
    api.listSpecifications(projectId).then(setSpecifications).catch(console.error);
  };

  useEffect(load, [projectId]);

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
          {specifications.map((spec, i) => (
            <motion.div
              key={spec.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className="card p-4 hover:shadow-md transition-shadow group"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-amber-500/10 text-amber-400 rounded-lg flex items-center justify-center">
                  <FileText size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{spec.id}</span>
                    <h3 className="font-medium text-card-foreground">{spec.name || 'Untitled'}</h3>
                  </div>
                  {spec.description && (
                    <p className="text-sm text-muted-foreground mt-0.5 line-clamp-1">{spec.description}</p>
                  )}
                  <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                    <span>{spec.requirements.length} requirements</span>
                    <span>{spec.children.length} sub-specs</span>
                  </div>
                </div>
                {editable && (
                <button
                  onClick={() => handleDelete(spec.id)}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={14} />
                </button>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
