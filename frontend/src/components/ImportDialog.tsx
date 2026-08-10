import { useCallback, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileUp, UploadCloud, Loader, CheckCircle2, AlertTriangle, Eye, Clipboard } from 'lucide-react';
import { api, type ImportSummary } from '../api/client';
import { useStore } from '../store';

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
}

const formats = [
  { id: 'auto', label: 'Auto-detect', desc: 'Guess ReqIF or SysML from the file' },
  { id: 'reqif', label: 'ReqIF 1.2', desc: 'DOORS / Polarion / Jama interchange XML' },
  { id: 'sysml', label: 'SysML v2', desc: 'SysML v2 textual notation (.sysml)' },
  { id: 'csv', label: 'CSV', desc: 'Comma-separated values spreadsheet' },
  { id: 'tsv', label: 'TSV', desc: 'Tab-separated values spreadsheet' },
  { id: 'xlsx', label: 'Excel (XLSX)', desc: 'Microsoft Excel worksheet' },
];

/** Only the table parsers can preview: parse_and_import has no dry-run path,
 *  and `auto` does not know its format until the content has been sniffed. */
const PREVIEWABLE = new Set(['csv', 'tsv', 'xlsx']);

/** Formats that the paste path accepts: xlsx is binary, ReqIF/SysML are out of scope. */
const PASTEABLE = new Set(['auto', 'csv', 'tsv']);

const ACCEPT = [
  '.xml', '.reqif', '.sysml', '.txt', '.csv', '.tsv', '.xlsx',
  'application/xml', 'text/xml', 'text/csv', 'text/tab-separated-values',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
].join(',');

export default function ImportDialog({ open, onClose, projectId }: ImportDialogProps) {
  const [format, setFormat] = useState('auto');
  const [mode, setMode] = useState<'merge' | 'replace'>('merge');
  const [file, setFile] = useState<File | null>(null);
  const [pasteText, setPasteText] = useState('');
  const [source, setSource] = useState<'file' | 'paste'>('file');
  const [dryRun, setDryRun] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ImportSummary | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);

  const canPreview = source === 'file'
    ? PREVIEWABLE.has(format)
    : PREVIEWABLE.has(format) && format !== 'xlsx';
  const previewing = dryRun && canPreview;

  const reset = () => {
    setFile(null); setPasteText(''); setError(''); setResult(null); setBusy(false);
  };

  const close = () => { reset(); onClose(); };

  // A preview describing a different file, format or mode is worse than none.
  const clearResult = () => { setError(''); setResult(null); };

  const chooseFormat = (id: string) => {
    setFormat(id);
    clearResult();
    if (!PREVIEWABLE.has(id)) setDryRun(false);
  };

  const chooseMode = (m: 'merge' | 'replace') => { setMode(m); clearResult(); };

  const chooseSource = (s: 'file' | 'paste') => {
    setSource(s);
    clearResult();
    if (s === 'paste' && !PASTEABLE.has(format)) {
      setFormat('auto');
      setDryRun(false);
    }
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setError(''); setResult(null); }
  }, []);

  const isEmpty = source === 'file' ? !file : !pasteText.trim();

  const runImport = async (preview: boolean) => {
    if (isEmpty) return;
    setBusy(true); setError(''); setResult(null);
    try {
      let summary: ImportSummary;
      if (source === 'file') {
        summary = await api.importProject(projectId, file!, format, mode, preview);
      } else {
        summary = await api.importPastedText(projectId, pasteText, format, mode, preview);
      }
      setResult(summary);
      if (!summary.dry_run) bumpGraphVersion();
    } catch (err: any) {
      setError(err.message || 'Import failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={close}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative bg-card border rounded-xl shadow-2xl w-full max-w-lg p-6 mx-4"
          >
            <button onClick={close} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors">
              <X size={18} />
            </button>

            <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2">
              <FileUp size={18} /> Import Requirements
            </h2>
            <p className="text-xs text-muted-foreground mb-5">Load a ReqIF, SysML v2 or spreadsheet into this project</p>

            <div className="space-y-5">
              <div>
                <label className="label">Source</label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <button
                    onClick={() => chooseSource('file')}
                    className={`p-2.5 rounded-lg border text-xs font-medium transition-all ${
                      source === 'file' ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <UploadCloud size={14} className="inline mr-1.5" /> File
                  </button>
                  <button
                    onClick={() => chooseSource('paste')}
                    className={`p-2.5 rounded-lg border text-xs font-medium transition-all ${
                      source === 'paste' ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <Clipboard size={14} className="inline mr-1.5" /> Paste data
                  </button>
                </div>
              </div>

              <div>
                <label className="label">Format</label>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {formats.map((f) => {
                    const active = format === f.id;
                    const disabled = source === 'paste' && !PASTEABLE.has(f.id);
                    return (
                      <button
                        key={f.id}
                        onClick={() => { if (!disabled) chooseFormat(f.id); }}
                        title={disabled ? 'Pasted text only supports csv and tsv' : f.desc}
                        disabled={disabled}
                        className={`p-2.5 rounded-lg border text-xs transition-all ${
                          disabled ? 'bg-muted/50 text-muted-foreground/40 cursor-not-allowed border-border/50' :
                          active ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                        }`}
                      >
                        <span className="font-medium">{f.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="label">Mode</label>
                <div className="grid grid-cols-2 gap-2 mt-1">
                  <button
                    onClick={() => chooseMode('merge')}
                    className={`p-2.5 rounded-lg border text-xs text-left transition-all ${
                      mode === 'merge' ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <span className="font-medium">Merge</span>
                    <span className="block opacity-70 text-[10px] mt-0.5">Create new, update matching IDs</span>
                  </button>
                  <button
                    onClick={() => chooseMode('replace')}
                    className={`p-2.5 rounded-lg border text-xs text-left transition-all ${
                      mode === 'replace' ? 'border-cs-red bg-cs-red/5 text-cs-red' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <span className="font-medium">Replace</span>
                    <span className="block opacity-70 text-[10px] mt-0.5">Wipe existing first, then import</span>
                  </button>
                </div>
              </div>

              {source === 'file' ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  onClick={() => inputRef.current?.click()}
                  className={`flex flex-col items-center justify-center gap-2 py-8 rounded-lg border-2 border-dashed cursor-pointer transition-colors ${
                    dragging ? 'border-primary bg-primary/5' : 'border-border hover:border-ring/40'
                  }`}
                >
                  <UploadCloud size={28} className="text-muted-foreground" />
                  {file ? (
                    <span className="text-sm text-foreground font-medium">{file.name}</span>
                  ) : (
                    <>
                      <span className="text-sm text-muted-foreground">Drop a file here, or click to browse</span>
                      <span className="text-[10px] text-muted-foreground">.xml (ReqIF) · .sysml (SysML v2) · .csv · .tsv · .xlsx</span>
                    </>
                  )}
                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPT}
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) { setFile(f); setError(''); setResult(null); }
                    }}
                  />
                </div>
              ) : (
                <textarea
                  placeholder='"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baselines"'
                  value={pasteText}
                  onChange={(e) => { setPasteText(e.target.value); setError(''); setResult(null); }}
                  rows={8}
                  className="w-full rounded-lg border bg-card p-3 text-xs text-foreground font-mono resize-y focus:outline-none focus:ring-1 focus:ring-primary"
                />
              )}

              <label
                className={`flex items-center gap-2 text-xs ${canPreview ? 'text-muted-foreground cursor-pointer' : 'text-muted-foreground/50 cursor-not-allowed'}`}
                title={canPreview ? undefined : 'Dry run is only available for CSV and TSV'}
              >
                <input
                  type="checkbox"
                  checked={previewing}
                  disabled={!canPreview}
                  onChange={(e) => { setDryRun(e.target.checked); clearResult(); }}
                  className="rounded border-border"
                />
                Dry run (preview only, no changes)
              </label>

              {error && (
                <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-lg p-3">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
                </div>
              )}

              {result?.dry_run && (
                <div className="text-xs bg-muted/50 border rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2 text-foreground">
                    <Eye size={14} className="shrink-0 mt-0.5" />
                    <span className="font-medium">Nothing has been changed yet.</span>
                  </div>
                  <div className="text-muted-foreground">
                    <b className="text-foreground">{result.would_create}</b> to create ·{' '}
                    <b className="text-foreground">{result.would_update}</b> to update
                    {result.skipped > 0 && <> · {result.skipped} skipped</>}
                    {' '}out of {result.rows} row{result.rows === 1 ? '' : 's'}.
                  </div>
                  {result.would_delete > 0 && (
                    <div className="flex items-start gap-2 text-destructive">
                      <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                      <span>
                        <b>{result.would_delete}</b> existing requirement{result.would_delete === 1 ? '' : 's'} will be deleted first.
                      </span>
                    </div>
                  )}
                  <button
                    onClick={() => runImport(false)}
                    disabled={busy}
                    className="btn-primary w-full justify-center disabled:opacity-50 mt-1"
                  >
                    <FileUp size={14} /> Import for real
                  </button>
                </div>
              )}

              {result && !result.dry_run && (
                <>
                  <div className="flex items-start gap-2 text-xs text-cs-green bg-cs-green/10 rounded-lg p-3">
                    <CheckCircle2 size={14} className="shrink-0 mt-0.5" />
                    <span>
                      Imported <b>{result.format}</b>: {result.created} created, {result.updated} updated,{' '}
                      {result.verification_cases} verification cases, {result.traces_added} traces
                      {result.skipped > 0 && <>, {result.skipped} skipped</>}.
                    </span>
                  </div>
                  {result.ignored.lines > 0 && (
                    <div className="flex items-start gap-2 text-xs text-cs-orange bg-cs-orange/10 rounded-lg p-3">
                      <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                      <span>
                        {result.ignored.lines} lines were not imported:{' '}
                        {Object.entries(result.ignored.constructs)
                          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
                          .slice(0, 5)
                          .map(([name, count]) => `${name} (${count})`)
                          .join(', ')}
                        {Object.keys(result.ignored.constructs).length > 5 && '\u2026'}
                      </span>
                    </div>
                  )}
                </>
              )}

              <div className="flex gap-2 pt-2 border-t">
                <button
                  onClick={() => runImport(previewing)}
                  disabled={isEmpty || busy}
                  className="btn-primary flex-1 justify-center disabled:opacity-50"
                >
                  {busy
                    ? (<><Loader size={14} className="animate-spin" /> {previewing ? 'Previewing...' : 'Importing...'}</>)
                    : previewing
                      ? (<><Eye size={14} /> Preview</>)
                      : (<><FileUp size={14} /> Import</>)}
                </button>
                <button onClick={close} className="btn-secondary justify-center">Close</button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
