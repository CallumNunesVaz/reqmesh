import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, AlertTriangle, Square, CheckSquare, X } from 'lucide-react';
import { api, type Risk } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
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
  const [error, setError] = useState('');
  const [form, setForm] = useState({ id: '', title: '', description: '', severity: 'medium', probability: 'medium' });
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const dataVersion = useStore((s) => s.dataVersion);
  const entityKinds = useEntityKinds(projectId);

  const load = () => { if (!projectId) return; api.listRisks(projectId).then(setRisks).catch(console.error); };
  useEffect(load, [projectId, dataVersion]);

  // Arriving from a link elsewhere (?focus=RSK-001).
  const focusId = useFocusedEntity(risks.length > 0);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !form.id.trim()) return;
    try {
      await api.createRisk(projectId, form);
      setShowCreate(false); setForm({ id: '', title: '', description: '', severity: 'medium', probability: 'medium' });
      load();
    } catch (err: any) { setError(err.message || 'Failed to create'); }
  };

  const handleDelete = async (id: string) => {
    if (!projectId || !confirm('Delete this risk?')) return;
    try {
      await api.deleteRisk(projectId, id);
      setRisks(risks.filter(r => r.id !== id));
    } catch (err: any) { setError(err.message || 'Failed to delete'); }
  };

  const toggleRisk = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearRiskSelection = () => setSelectedIds(new Set());
  const selectAllRisks = () => setSelectedIds(new Set(risks.map(r => r.id)));

  const handleBulkRiskStatus = async (status: string) => {
    if (!projectId) return;
    await api.bulkUpdateRisks(projectId, [...selectedIds], { status });
    clearRiskSelection();
    load();
  };

  const handleBulkRiskDelete = async () => {
    if (!projectId) return;
    if (!confirm(`Delete ${selectedIds.size} risk(s)?`)) return;
    await api.bulkDeleteRisks(projectId, [...selectedIds]);
    clearRiskSelection();
    load();
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}
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
              {editable && (
                <span className="shrink-0">
                  {selectedIds.has(r.id) ? (
                    <CheckSquare size={14} className="text-primary cursor-pointer" onClick={() => toggleRisk(r.id)} />
                  ) : (
                    <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={() => toggleRisk(r.id)} />
                  )}
                </span>
              )}
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
      {selectedIds.size > 0 && editable && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkRiskStatus(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set status...</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="mitigated">Mitigated</option>
          </select>
          <button onClick={handleBulkRiskDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
          <button onClick={selectAllRisks} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearRiskSelection} className="text-[10px] text-muted-foreground hover:text-foreground"><X size={13} /></button>
        </div>
      )}
    </div>
  );
}
