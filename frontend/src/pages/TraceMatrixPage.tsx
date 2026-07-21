import { useEffect, useState, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { GitBranch, Plus, X, LayoutGrid, LayoutList } from 'lucide-react';
import { api } from '../api/client';
import type { TraceLink, Requirement, VerificationCase } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import AutocompleteInput from '../components/AutocompleteInput';
import { ENTITY_META, EntityLink, type EntityKind } from '../components/entities';

// Cell tint per link type. Falls back to a neutral chip for any type not
// listed here (importers emit types like `verifies`/`traces` too).
const LINK_TYPE_COLORS: Record<string, string> = {
  satisfies: 'bg-blue-500/20 text-blue-400',
  refines: 'bg-purple-500/20 text-purple-400',
  verified_by: 'bg-emerald-500/20 text-emerald-400',
  verifies: 'bg-emerald-500/20 text-emerald-400',
  derives: 'bg-orange-500/20 text-orange-400',
  conflicts: 'bg-red-500/20 text-red-400',
};

export default function TraceMatrixPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [verificationCases, setVerificationCases] = useState<VerificationCase[]>([]);
  const [newLink, setNewLink] = useState({ source: '', target: '', type: 'satisfies' });
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list');
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const dataVersion = useStore((s) => s.dataVersion);

  const entitySuggestions = useMemo(() => {
    const reqItems = requirements.map((r) => ({ id: r.id, label: r.name || r.id }));
    const vcItems = verificationCases.map((v) => ({ id: v.id, label: v.name || v.id }));
    return [...reqItems, ...vcItems].sort((a, b) => a.id.localeCompare(b.id));
  }, [requirements, verificationCases]);

  const load = () => {
    if (!projectId) return;
    Promise.all([
      api.getTraces(projectId),
      api.listRequirements(projectId),
      api.listVerificationCases(projectId),
    ]).then(([traces, reqs, vcs]) => {
      setLinks(traces.links || []);
      setRequirements(reqs);
      setVerificationCases(vcs);
    }).catch(console.error);
  };

  useEffect(load, [projectId, dataVersion]);

  const addLink = async () => {
    if (!projectId || !newLink.source || !newLink.target) return;
    try {
      const updated = [...links, { ...newLink }];
      await api.updateTraces(projectId, { links: updated });
      setLinks(updated);
      setNewLink({ source: '', target: '', type: 'satisfies' });
    } catch (err: any) { setError(err.message || 'Failed to add link'); }
  };

  const removeLink = async (index: number) => {
    if (!projectId) return;
    try {
      const updated = links.filter((_, i) => i !== index);
      await api.updateTraces(projectId, { links: updated });
      setLinks(updated);
    } catch (err: any) { setError(err.message || 'Failed to remove link'); }
  };

  // Either end of a trace can be a requirement or a verification case.
  const vcIds = useMemo(() => new Set(verificationCases.map((v) => v.id)), [verificationCases]);
  const kindOf = (id: string): EntityKind => (vcIds.has(id) ? 'verification' : 'requirement');
  const nameOf = (id: string) =>
    requirements.find((r) => r.id === id)?.name ?? verificationCases.find((v) => v.id === id)?.name;

  // A general trace matrix: rows are every distinct link source, columns every
  // distinct link target. Either end may be a requirement or a verification
  // case, so requirement→requirement links (refines/derives/…) render as cells
  // too — not just requirement→VC pairings.
  const matrixSources = useMemo(
    () => [...new Set(links.map((l) => l.source))].sort(),
    [links],
  );
  const matrixTargets = useMemo(
    () => [...new Set(links.map((l) => l.target))].sort(),
    [links],
  );

  return (
    <div className="max-w-5xl mx-auto p-8">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Traceability Matrix</h1>
        <p className="text-sm text-muted-foreground mt-1">{links.length} trace links</p>
        <div className="flex gap-1 mt-2">
          <button
            onClick={() => setViewMode('list')}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs transition-colors ${viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'}`}
          >
            <LayoutList size={13} /> List
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs transition-colors ${viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'}`}
          >
            <LayoutGrid size={13} /> Grid
          </button>
        </div>
      </motion.div>

      {editable && (
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-4 mt-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
          <GitBranch size={16} /> Add Trace Link
        </h2>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="label">Source</label>
            <AutocompleteInput
              className="select"
              placeholder="Select source..."
              value={newLink.source}
              onChange={(v) => setNewLink({ ...newLink, source: v })}
              suggestions={entitySuggestions}
            />
          </div>
          <div>
            <label className="label">Type</label>
            <select className="select w-32" value={newLink.type} onChange={(e) => setNewLink({ ...newLink, type: e.target.value })}>
              <option value="satisfies">Satisfies</option>
              <option value="refines">Refines</option>
              <option value="verified_by">Verified By</option>
              <option value="derives">Derives</option>
              <option value="conflicts">Conflicts</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="label">Target</label>
            <AutocompleteInput
              className="select"
              placeholder="Select target..."
              value={newLink.target}
              onChange={(v) => setNewLink({ ...newLink, target: v })}
              suggestions={entitySuggestions}
            />
          </div>
          <button onClick={addLink} className="btn-primary" disabled={!newLink.source || !newLink.target}>
            <Plus size={14} /> Add
          </button>
        </div>
      </motion.div>
      )}

      {links.length === 0 ? (
        <div className="card p-12 text-center mt-6">
          <GitBranch size={48} className="mx-auto text-muted-foreground/40 mb-4" />
          <p className="text-card-foreground font-medium">No trace links yet</p>
          <p className="text-sm text-muted-foreground mt-1">Add links to connect requirements and verification cases.</p>
        </div>
      ) : viewMode === 'list' ? (
        <div className="card mt-6 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-4 py-2.5 font-semibold text-xs text-muted-foreground uppercase tracking-wider">Source</th>
                <th className="text-left px-4 py-2.5 font-semibold text-xs text-muted-foreground uppercase tracking-wider">Type</th>
                <th className="text-left px-4 py-2.5 font-semibold text-xs text-muted-foreground uppercase tracking-wider">Target</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {links.map((link, i) => (
                <motion.tr
                  key={`${link.source}-${link.target}-${i}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  className="border-b hover:bg-muted/30 transition-colors group"
                >
                  <td className="px-4 py-2.5 text-xs text-foreground">
                    <EntityLink kind={kindOf(link.source)} id={link.source} name={nameOf(link.source)} className="hover:text-primary" />
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="badge bg-muted text-muted-foreground">{link.type}</span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-foreground">
                    <EntityLink kind={kindOf(link.target)} id={link.target} name={nameOf(link.target)} className="hover:text-primary" />
                  </td>
                  <td className="px-2 py-2.5">
                    {editable && (
                    <button
                      onClick={() => removeLink(i)}
                      className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <X size={12} />
                    </button>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card mt-6 overflow-auto max-h-[70vh]">
          <table className="text-sm border-separate border-spacing-0">
            <thead>
              <tr>
                <th className="sticky top-0 left-0 z-20 bg-card border-b border-r px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider text-left min-w-[100px]">
                  Source \ Target
                </th>
                {matrixTargets.map((tgt) => (
                  <th
                    key={tgt}
                    className="sticky top-0 z-10 bg-card border-b px-2 py-2 text-[9px] font-mono whitespace-nowrap"
                  >
                    <EntityLink kind={kindOf(tgt)} id={tgt} name={nameOf(tgt)} showIcon={false} className="text-muted-foreground hover:text-primary" />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrixSources.map((src) => {
                const srcLinks = links.filter((l) => l.source === src);
                return (
                  <tr key={src} className="group">
                    <td className="sticky left-0 z-10 bg-card border-r px-3 py-1.5 text-[10px] font-mono whitespace-nowrap group-hover:bg-accent/40">
                      <EntityLink kind={kindOf(src)} id={src} name={nameOf(src)} showIcon={false} className="text-foreground hover:text-primary" />
                    </td>
                    {matrixTargets.map((tgt) => {
                      const link = srcLinks.find((l) => l.target === tgt);
                      return (
                        <td key={tgt} className="border-b px-2 py-1.5 text-center">
                          {link ? (
                            // The headers already link both ends; the cell
                            // itself takes you to the target the pairing hits.
                            <Link
                              to={ENTITY_META[kindOf(tgt)].path(projectId!, tgt)}
                              title={`${src} ${link.type} ${tgt}`}
                              className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-medium hover:ring-1 hover:ring-primary/40 transition-shadow ${LINK_TYPE_COLORS[link.type] || 'bg-muted text-muted-foreground'}`}
                            >
                              {link.type}
                            </Link>
                          ) : (
                            <span className="text-[9px] text-muted-foreground/30">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {matrixSources.length === 0 && <p className="text-xs text-muted-foreground text-center py-8">No trace links to display.</p>}
        </div>
      )}
    </div>
  );
}
