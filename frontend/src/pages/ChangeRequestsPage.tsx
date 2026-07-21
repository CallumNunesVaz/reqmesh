import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, GitPullRequest, Square, CheckSquare, X } from 'lucide-react';
import { api, type ChangeRequest } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { CopyLinkButton, EntityLink } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { AutoLinkText } from '../components/autoLink';
import { useEntityKinds } from '../components/entityIndex';

const statusBadges: Record<string, string> = {
  submitted: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  in_review: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  approved: 'border-green-500/30 bg-green-500/10 text-green-400',
  rejected: 'border-red-500/30 bg-red-500/10 text-red-400',
  implemented: 'border-purple-500/30 bg-purple-500/10 text-purple-400',
  closed: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400',
};

export default function ChangeRequestsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [crs, setCrs] = useState<ChangeRequest[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ id: '', title: '', description: '' });
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const dataVersion = useStore((s) => s.dataVersion);
  const entityKinds = useEntityKinds(projectId);

  const load = () => {
    if (!projectId) return;
    api.listChangeRequests(projectId).then(setCrs).catch(console.error);
  };
  useEffect(load, [projectId, dataVersion]);

  // Arriving from a link elsewhere (?focus=CR-001).
  const focusId = useFocusedEntity(crs.length > 0);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !form.id.trim()) return;
    try {
      await api.createChangeRequest(projectId, form);
      setShowCreate(false);
      setForm({ id: '', title: '', description: '' });
      load();
    } catch (err: any) { setError(err.message || 'Failed to create'); }
  };

  const handleStatus = async (crId: string, status: string) => {
    if (!projectId) return;
    try {
      await api.updateChangeRequest(projectId, crId, { status });
      load();
    } catch (err: any) { setError(err.message || 'Failed to update'); }
  };

  const handleDelete = async (crId: string) => {
    if (!projectId || !confirm('Delete this change request?')) return;
    try {
      await api.deleteChangeRequest(projectId, crId);
      setCrs(crs.filter((c) => c.id !== crId));
    } catch (err: any) { setError(err.message || 'Failed to delete'); }
  };

  const toggleCR = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearCRSelection = () => setSelectedIds(new Set());
  const selectAllCRs = () => setSelectedIds(new Set(crs.map(c => c.id)));

  const handleBulkCRStatus = async (status: string) => {
    if (!projectId) return;
    await api.bulkUpdateChangeRequests(projectId, [...selectedIds], { status });
    clearCRSelection();
    load();
  };

  const handleBulkCRDelete = async () => {
    if (!projectId) return;
    if (!confirm(`Delete ${selectedIds.size} change request(s)?`)) return;
    await api.bulkDeleteChangeRequests(projectId, [...selectedIds]);
    clearCRSelection();
    load();
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Change Requests</h1>
          <p className="text-sm text-muted-foreground mt-1">{crs.length} change requests</p>
        </div>
        {editable && (
        <button onClick={() => setShowCreate(!showCreate)} className="btn-primary">
          <Plus size={16} /> New Change Request
        </button>
        )}
      </div>

      <AnimatePresence>
        {showCreate && (
          <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            onSubmit={handleCreate} className="card p-4 mb-4 overflow-hidden">
            <div className="flex items-end gap-3">
              <div className="w-32"><label className="label">ID</label><input className="input font-mono" placeholder="CR-001" value={form.id} onChange={e => setForm({...form, id: e.target.value})} autoFocus /></div>
              <div className="flex-1"><label className="label">Title</label><input className="input" placeholder="Change request title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} /></div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      <div className="space-y-3">
        {crs.map((cr, i) => (
          <motion.div key={cr.id} id={`entity-${cr.id}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
            className={`card p-4 hover:shadow-md transition-shadow group ${focusId === cr.id ? 'ring-2 ring-primary/50' : ''}`}>
            <div className="flex items-center gap-3">
              {editable && (
                <span className="shrink-0">
                  {selectedIds.has(cr.id) ? (
                    <CheckSquare size={14} className="text-primary cursor-pointer" onClick={() => toggleCR(cr.id)} />
                  ) : (
                    <Square size={14} className="text-muted-foreground/40 cursor-pointer hover:text-muted-foreground" onClick={() => toggleCR(cr.id)} />
                  )}
                </span>
              )}
              <div className="w-9 h-9 bg-purple-500/10 text-purple-400 rounded-lg flex items-center justify-center"><GitPullRequest size={18} /></div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{cr.id}</span><h3 className="font-medium text-card-foreground">{cr.title || 'Untitled'}</h3><span className={`badge border ${statusBadges[cr.status] || ''}`}>{cr.status}</span><CopyLinkButton kind="change" id={cr.id} className="opacity-0 group-hover:opacity-100" /></div>
                {cr.description && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1"><AutoLinkText text={cr.description} kinds={entityKinds} /></p>}
                {cr.affected_requirements.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Affects</span>
                    {cr.affected_requirements.map((rid) => (
                      <span key={rid} className="inline-flex items-center px-1.5 py-0.5 rounded bg-muted text-xs">
                        <EntityLink kind="requirement" id={rid} className="hover:text-primary" />
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1">
                <select className="select text-xs py-1 w-28" value={cr.status} onChange={e => handleStatus(cr.id, e.target.value)} disabled={!editable}>
                  <option value="submitted">Submitted</option><option value="in_review">In Review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="implemented">Implemented</option><option value="closed">Closed</option>
                </select>
                {editable && (
                <button onClick={() => handleDelete(cr.id)} className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"><Trash2 size={14} /></button>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
      {selectedIds.size > 0 && editable && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-card border rounded-xl shadow-2xl px-4 py-3">
          <span className="text-xs font-medium text-foreground">{selectedIds.size} selected</span>
          <select
            className="select text-xs py-1 w-32"
            onChange={(e) => { if (e.target.value) { handleBulkCRStatus(e.target.value); e.target.value = ''; } }}
            value=""
          >
            <option value="">Set status...</option>
            <option value="open">Open</option>
            <option value="in_review">In Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <button onClick={handleBulkCRDelete} className="btn-danger text-xs"><Trash2 size={13} /> Delete</button>
          <button onClick={selectAllCRs} className="text-[10px] text-muted-foreground hover:text-foreground">Select all</button>
          <button onClick={clearCRSelection} className="text-[10px] text-muted-foreground hover:text-foreground"><X size={13} /></button>
        </div>
      )}
    </div>
  );
}
