import { useEffect, useState, useMemo } from 'react';
import { usePersistedState } from '../hooks/usePersistedState';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, CheckCircle2, X, Link as LinkIcon, Loader, Search, UploadCloud, Copy } from 'lucide-react';
import { api, type VerificationCase, type TestResultImportSummary } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { CopyLinkButton, SECTION_TITLES } from '../components/entities';
import { useFocusedEntity } from '../components/useFocusedEntity';
import { HelpTip } from '../components/HelpTip';
import { useToasts } from '../components/Toast';
import { useBulkActions } from '../hooks/useBulkActions';
import BulkActionBar from '../components/BulkActionBar';
import LoadingSplash from '../components/LoadingSplash';
import EmptyState from '../components/EmptyState';

const METHOD_OPTIONS = ['test', 'analysis', 'demonstration', 'inspection'] as const;
const STATUS_OPTIONS = ['pending', 'in_progress', 'passed', 'failed'] as const;

const statusBadges: Record<string, string> = {
  pending: 'border-cs-amber/30 bg-cs-amber/10 text-cs-amber',
  in_progress: 'border-cs-blue/30 bg-cs-blue/10 text-cs-blue',
  passed: 'border-cs-green/30 bg-cs-green/10 text-cs-green',
  failed: 'border-cs-red/30 bg-cs-red/10 text-cs-red',
};

export default function VerificationPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const dataVersion = useStore((s) => s.dataVersion);
  const [verificationCases, setVerificationCases] = useState<VerificationCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newVC, setNewVC] = useState({ id: '', name: '', description: '', method: 'test' });
  const [idExample, setIdExample] = useState('');
  // Persisted per project — see RequirementsPage/ComponentsPage for why.
  const pk = (field: string) => (projectId ? `rt-verification-${field}-${projectId}` : null);
  const [selectedVcs, setSelectedVcs] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState('passed');

  // CI test result import
  const [showImport, setShowImport] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importFormat, setImportFormat] = useState('auto');
  const [importDryRun, setImportDryRun] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<TestResultImportSummary | null>(null);
  const [importError, setImportError] = useState('');
  const [search, setSearch] = usePersistedState(pk('search'), '');
  const [filterStatus, setFilterStatus] = usePersistedState(pk('filter-status'), '');
  const [filterMethod, setFilterMethod] = usePersistedState(pk('filter-method'), '');

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    api.listVerificationCases(projectId)
      .then(setVerificationCases)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId, dataVersion]);

  const filteredVCs = useMemo(() => {
    if (!search && !filterStatus && !filterMethod) return verificationCases;
    const q = search.toLowerCase();
    return verificationCases.filter((vc) => {
      if (filterStatus && vc.status !== filterStatus) return false;
      if (filterMethod && vc.method !== filterMethod) return false;
      if (q) {
        const hay = `${vc.id} ${vc.name || ''} ${vc.description || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [verificationCases, search, filterStatus, filterMethod]);
  const filtering = !!(search || filterStatus || filterMethod);

  const openCreate = () => {
    setShowCreate(true);
    if (!projectId) return;
    // Prefill the id from the project's naming standard so the configured
    // scheme is followed rather than typed from memory. Only fills an empty id,
    // so a value already typed (or left over) is never clobbered.
    api.getNextId(projectId, 'verification')
      .then((r) => {
        setNewVC((v) => (v.id ? v : { ...v, id: r.next_id }));
        setIdExample(r.next_id);
      })
      .catch(() => {});
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !newVC.id.trim() || !editable) return;
    try {
      await api.createVerificationCase(projectId, newVC);
      addToast('success', `Verification case ${newVC.id.trim()} created`);
      setShowCreate(false);
      setNewVC({ id: '', name: '', description: '', method: 'test' });
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to create verification case');
    }
  };

  const handleDuplicate = async (vc: VerificationCase) => {
    if (!projectId) return;
    const existing = new Set(verificationCases.map((v) => v.id));
    // Numbered from 1, not bare `-copy`, because the project's naming
    // standard is enforced on create and a numeric-suffix scheme refuses an
    // id that does not end in a digit. `-copy` was silently rejected with a
    // 422 the moment enforcement went in, which broke Duplicate outright.
    let n = 1;
    let id = `${vc.id}-copy${n}`;
    while (existing.has(id)) { id = `${vc.id}-copy${++n}`; }
    try {
      await api.createVerificationCase(projectId, {
        id,
        name: `${vc.name} (copy)`,
        description: vc.description,
        method: vc.method,
      });
      addToast('success', `Verification case ${id} created`);
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to duplicate verification case');
    }
  };

  const handleImportTestResults = async () => {
    if (!projectId || !importFile) return;
    setImporting(true);
    setImportError('');
    setImportResult(null);
    try {
      const result = await api.importTestResults(projectId, importFile, importFormat, importDryRun);
      setImportResult(result);
      if (!importDryRun && result.updated > 0) {
        const updated = await api.listVerificationCases(projectId);
        setVerificationCases(updated);
      }
    } catch (err: any) {
      setImportError(err.message || 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  // Arriving from an older link (?focus=VC-001): ring and scroll to the row,
  // so the reference lands on the thing it pointed at even though the case
  // now lives on its own detail page.
  const focusId = useFocusedEntity(verificationCases.length > 0);

  const { runBulkUpdate } = useBulkActions({
    clearSelection: () => setSelectedVcs(new Set()),
    reload: load,
  });

  const handleBulkStatus = async (status: string) => {
    if (!projectId) return;
    const ids = [...selectedVcs];
    const before = Object.fromEntries(
      verificationCases.filter((vc) => selectedVcs.has(vc.id)).map((vc) => [vc.id, { status: vc.status }]),
    );
    await runBulkUpdate({
      label: `${status} on ${ids.length} verification cases`,
      noun: 'verification case',
      ids,
      before,
      updates: { status },
      apply: (updateIds, updatePayload) => api.bulkUpdateVerificationCases(projectId, updateIds, updatePayload),
      applyOne: (id, updatePayload) => api.updateVerificationCase(projectId, id, updatePayload),
    });
  };

  return (
    <div className="relative max-w-5xl mx-auto p-8">
      {loading && verificationCases.length === 0 && <LoadingSplash label="Loading verification cases…" />}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{SECTION_TITLES.verification}</h1>
          <HelpTip>Verification cases prove that requirements are met. Choose a method (test, analysis, demonstration, or inspection), link the requirements being verified, and optionally record measurements to feed the parametric evaluation engine.</HelpTip>
          <p className="text-sm text-muted-foreground mt-1">
            {filtering ? `${filteredVCs.length} of ${verificationCases.length} verification cases` : `${verificationCases.length} verification cases`}
          </p>
        </div>
        {editable && (
        <button onClick={openCreate} className="btn-primary whitespace-nowrap shrink-0 self-start">
          <Plus size={16} /> New Verification Case
        </button>
        )}
        {editable && (
        <button onClick={() => { setShowImport(!showImport); setImportResult(null); setImportError(''); }}
                className="btn-secondary whitespace-nowrap shrink-0 self-start">
          <UploadCloud size={16} /> Import CI Results
        </button>
        )}
      </div>

      <div className="sticky top-0 z-10 -mx-2 px-2 py-2 bg-background/95 backdrop-blur-sm mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="input pl-9 pr-14 h-9"
              placeholder="Search verification cases…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search ? (
              <button className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            ) : (
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded-md border bg-muted text-3xs font-mono text-muted-foreground pointer-events-none">/</kbd>
            )}
          </div>
          <select className="select w-32 h-9 text-xs" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
          <select className="select w-36 h-9 text-xs" value={filterMethod} onChange={(e) => setFilterMethod(e.target.value)}>
            <option value="">All methods</option>
            {METHOD_OPTIONS.map((m) => <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>)}
          </select>
        </div>
      </div>

      {selectedVcs.size > 0 && (
        <BulkActionBar
          count={selectedVcs.size}
          onSelectAll={() => setSelectedVcs(new Set(filteredVCs.map(v => v.id)))}
          onClear={() => setSelectedVcs(new Set())}
        >
          <select className="select text-xs py-1 w-28" value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)}>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
          <button
            onClick={() => handleBulkStatus(bulkStatus)}
            className="btn-primary text-xs"
          >
            Apply
          </button>
        </BulkActionBar>
      )}

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
                <label className="label">ID
                  <input className="input font-mono" placeholder="VC-001" value={newVC.id} onChange={(e) => setNewVC({ ...newVC, id: e.target.value })} />
                </label>
                {idExample && <span className="text-3xs text-muted-foreground">e.g. {idExample}</span>}
              </div>
              <div className="flex-1">
                <label className="label">Name
                  <input className="input" placeholder="Verification case name" value={newVC.name} onChange={(e) => setNewVC({ ...newVC, name: e.target.value })} />
                </label>
              </div>
              <div>
                <label className="label">Method
                  <select className="select" value={newVC.method} onChange={(e) => setNewVC({ ...newVC, method: e.target.value })}>
                    {METHOD_OPTIONS.map((m) => <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>)}
                  </select>
                </label>
              </div>
              <button type="submit" className="btn-primary">Create</button>
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {filteredVCs.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title={filtering ? 'No verification cases match your filters.' : 'No verification cases yet'}
          hint={filtering ? undefined : 'Create verification cases to track requirement testing.'}
          action={!filtering && editable ? { label: 'New Verification Case', onClick: openCreate } : undefined}
        >
          {filtering && (
            <button className="text-xs text-primary hover:underline mt-2" onClick={() => { setSearch(''); setFilterStatus(''); setFilterMethod(''); }}>Clear filters</button>
          )}
        </EmptyState>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-muted/30">
                {editable && <th className="px-3 py-2.5 w-0" aria-label="Select" />}
                <th className="px-4 py-2.5 w-28 text-3xs font-semibold uppercase tracking-wider text-muted-foreground">ID</th>
                <th className="px-4 py-2.5 min-w-[14rem] text-3xs font-semibold uppercase tracking-wider text-muted-foreground">Name</th>
                <th className="px-4 py-2.5 w-28 text-3xs font-semibold uppercase tracking-wider text-muted-foreground">Method</th>
                <th className="px-4 py-2.5 w-28 text-3xs font-semibold uppercase tracking-wider text-muted-foreground">Status</th>
                <th className="px-4 py-2.5 text-3xs font-semibold uppercase tracking-wider text-muted-foreground">Result</th>
                <th className="px-4 py-2.5 w-24 text-3xs font-semibold uppercase tracking-wider text-muted-foreground">Links</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredVCs.map((vc) => {
                const linkedCount = vc.verified_requirements.length;
                return (
                  <tr key={vc.id} id={`entity-${vc.id}`}
                    onClick={() => navigate(`/project/${projectId}/verification/${encodeURIComponent(vc.id)}`)}
                    className={`group rt-row hover:bg-accent/30 transition-colors cursor-pointer ${focusId === vc.id ? 'ring-2 ring-primary/50' : ''}`}>
                    {editable && (
                      <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedVcs.has(vc.id)}
                          onChange={(e) => {
                            setSelectedVcs(p => { const n = new Set(p); if (e.target.checked) n.add(vc.id); else n.delete(vc.id); return n; });
                          }}
                          aria-label={`Select ${vc.id}`}
                          className="w-4 h-4 rounded-md border-muted-foreground/30 shrink-0"
                        />
                      </td>
                    )}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs text-card-foreground">{vc.id}</span>
                        <CopyLinkButton kind="verification" id={vc.id} className="opacity-0 group-hover:opacity-100" />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); navigate(`/project/${projectId}/verification/${encodeURIComponent(vc.id)}`); }}
                        className="line-clamp-1 text-card-foreground hover:underline text-left"
                        title={vc.name || undefined}
                      >
                        {vc.name || <span className="text-muted-foreground/40 italic">—</span>}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-card-foreground">{vc.method || '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className={`badge border ${statusBadges[vc.status] || ''}`}>{vc.status}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">
                      <span className="line-clamp-1" title={vc.result || undefined}>{vc.result || '—'}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1 text-2xs tabular-nums text-muted-foreground" title={`${linkedCount} linked requirement(s)`}>
                        <LinkIcon size={12} /> {linkedCount > 0 ? linkedCount : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 w-0" onClick={(e) => e.stopPropagation()}>
                      {editable && (
                        <button
                          onClick={() => handleDuplicate(vc)}
                          className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                          title="Duplicate verification case"
                        >
                          <Copy size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* CI Test Result Import */}
      <AnimatePresence>
        {showImport && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden mb-4"
          >
            <div className="card p-5 border-2 border-primary/20">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                  <UploadCloud size={16} /> Import CI Test Results
                </h3>
                <button onClick={() => setShowImport(false)} className="text-muted-foreground hover:text-foreground">
                  <X size={16} />
                </button>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                JUnit XML, CTRF JSON, or TAP test output. Test names must match verification case IDs (e.g. VCAF0001).
                <a className="text-primary hover:underline ml-1" href={`/api/projects/${projectId}/test-results/sample`} target="_blank">View sample JUnit XML</a>
              </p>

              {!importResult ? (
                <div className="space-y-3">
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="label">File
                        <input type="file" accept=".xml,.json,.tap,.txt" className="input"
                          onChange={(e) => setImportFile(e.target.files?.[0] ?? null)} />
                      </label>
                    </div>
                    <div>
                      <label className="label">Format
                        <select className="select" value={importFormat}
                          onChange={(e) => setImportFormat(e.target.value)}>
                          <option value="auto">Auto-detect</option>
                          <option value="junit">JUnit XML</option>
                          <option value="ctrf">CTRF JSON</option>
                          <option value="tap">TAP</option>
                        </select>
                      </label>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={importDryRun}
                      onChange={(e) => setImportDryRun(e.target.checked)}
                      className="w-4 h-4 rounded-md" />
                    Dry run (preview only, no changes)
                  </label>
                  {importError && (
                    <div className="p-2 rounded-md bg-destructive/10 text-destructive text-xs border border-destructive/20">{importError}</div>
                  )}
                  <button onClick={handleImportTestResults}
                    disabled={!importFile || importing}
                    className="btn-primary gap-1.5">
                    {importing ? <Loader size={14} className="animate-spin" /> : <UploadCloud size={14} />}
                    {importing ? 'Importing…' : importDryRun ? 'Preview' : 'Import'}
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-4 text-sm">
                    <span className="font-mono"><span className="text-cs-blue">{importResult.parsed}</span> parsed</span>
                    <span className="font-mono"><span className="text-cs-green">{importResult.matched}</span> matched</span>
                    {!importDryRun && <span className="font-mono"><span className="text-cs-teal">{importResult.updated}</span> updated</span>}
                    <span className="font-mono"><span className="text-cs-orange">{importResult.unmatched}</span> unmatched</span>
                    {importResult.errors.length > 0 && (
                      <span className="font-mono"><span className="text-cs-red">{importResult.errors.length}</span> errors</span>
                    )}
                  </div>
                  {importResult.details.length > 0 && (
                    <div className="max-h-60 overflow-y-auto border rounded-lg">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-muted">
                          <tr className="text-muted-foreground">
                            <th className="text-left px-2 py-1">Test</th>
                            <th className="text-left px-2 py-1" title="Verification Case">VC</th>
                            <th className="text-left px-2 py-1">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {importResult.details.map((d, i) => (
                            <tr key={i} className="border-t">
                              <td className="px-2 py-1 font-mono truncate max-w-[200px]" title={d.test_name}>{d.test_name}</td>
                              <td className="px-2 py-1 font-mono">{d.vc_id || '—'}</td>
                              <td className="px-2 py-1">
                                <span className={`text-3xs font-medium ${d.status === 'imported' ? 'text-cs-green' : d.status === 'unmatched' ? 'text-cs-orange' : d.status === 'dry_run' ? 'text-cs-blue' : 'text-cs-red'}`}>{d.status}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div className="flex gap-2">
                    <button onClick={() => { setImportResult(null); setImportFile(null); }}
                      className="btn-secondary text-xs">Import another</button>
                    <button onClick={() => setShowImport(false)}
                      className="btn-secondary text-xs">Close</button>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
