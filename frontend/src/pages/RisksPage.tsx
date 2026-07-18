import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, AlertTriangle } from 'lucide-react';
import { api, type Risk } from '../api/client';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';

const sevColors: Record<string, string> = {
  low: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400',
  medium: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  high: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  critical: 'border-red-500/30 bg-red-500/10 text-red-400',
};

export default function RisksPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ id: '', title: '', description: '', severity: 'medium', probability: 'medium' });
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const entityKinds = useEntityKinds(projectId);

  const load = () => { if (!projectId) return; api.listRisks(projectId).then(setRisks).catch(console.error); };
  useEffect(load, [projectId]);

  // Arriving from a link elsewhere (?focus=RSK-001).
  const focusId = useFocusedEntity(risks.length > 0);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !form.id.trim()) return;
    await api.createRisk(projectId, form);
    setShowCreate(false); setForm({ id: '', title: '', description: '', severity: 'medium', probability: 'medium' });
    load();
  };

  const handleDelete = async (id: string) => {
    if (!projectId || !confirm('Delete this risk?')) return;
    await api.deleteRisk(projectId, id);
    setRisks(risks.filter(r => r.id !== id));
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div><h1 className="text-2xl font-bold text-foreground">Risks</h1><p className="text-sm text-muted-foreground mt-1">{risks.length} risks</p></div>
        {editable && (
        <button onClick={() => setShowCreate(!showCreate)} className="btn-primary"><Plus size={16} /> New Risk</button>
        )}
      </div>
      <AnimatePresence>
        {showCreate && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate} className="card p-4 mb-4 overflow-hidden">
            <div className="flex items-end gap-3">
              <div className="w-32"><label className="label">ID</label><input className="input font-mono" placeholder="RSK-001" value={form.id} onChange={e => setForm({...form, id: e.target.value})} autoFocus /></div>
              <div className="flex-1"><label className="label">Title</label><input className="input" placeholder="Risk title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} /></div>
              <div><label className="label">Severity</label><select className="select" value={form.severity} onChange={e => setForm({...form, severity: e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></div>
              <div><label className="label">Prob.</label><select className="select" value={form.probability} onChange={e => setForm({...form, probability: e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
      <div className="space-y-3">
        {risks.map((r, i) => (
          <motion.div key={r.id} id={`entity-${r.id}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
            className={`card p-4 hover:shadow-md transition-shadow group ${focusId === r.id ? 'ring-2 ring-primary/50' : ''}`}>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-red-500/10 text-red-400 rounded-lg flex items-center justify-center"><AlertTriangle size={18} /></div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{r.id}</span><h3 className="font-medium text-card-foreground">{r.title}</h3><span className={`badge border ${sevColors[r.severity] || ''}`}>{r.severity}</span><span className="text-xs text-muted-foreground">prob: {r.probability}</span><CopyLinkButton kind="risk" id={r.id} className="opacity-0 group-hover:opacity-100" /></div>
                {r.description && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1"><AutoLinkText text={r.description} kinds={entityKinds} /></p>}
                {r.linked_requirements.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Threatens</span>
                    {r.linked_requirements.map((rid) => (
                      <span key={rid} className="inline-flex items-center px-1.5 py-0.5 rounded bg-muted text-xs">
                        <EntityLink kind="requirement" id={rid} className="hover:text-primary" />
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {editable && (
              <button onClick={() => handleDelete(r.id)} className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"><Trash2 size={14} /></button>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
