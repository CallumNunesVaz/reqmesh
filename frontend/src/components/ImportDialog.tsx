import { useCallback, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileUp, UploadCloud, Loader, CheckCircle2, AlertTriangle } from 'lucide-react';
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
];

export default function ImportDialog({ open, onClose, projectId }: ImportDialogProps) {
  const [format, setFormat] = useState('auto');
  const [mode, setMode] = useState<'merge' | 'replace'>('merge');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ImportSummary | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);

  const reset = () => {
    setFile(null); setError(''); setResult(null); setBusy(false);
  };

  const close = () => { reset(); onClose(); };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setError(''); setResult(null); }
  }, []);

  const handleImport = async () => {
    if (!file) return;
    setBusy(true); setError(''); setResult(null);
    try {
      const summary = await api.importProject(projectId, file, format, mode);
      setResult(summary);
      bumpGraphVersion();
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
            <p className="text-xs text-muted-foreground mb-5">Load a ReqIF 1.2 or SysML v2 file into this project</p>

            <div className="space-y-5">
              <div>
                <label className="label">Format</label>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {formats.map((f) => {
                    const active = format === f.id;
                    return (
                      <button
                        key={f.id}
                        onClick={() => setFormat(f.id)}
                        title={f.desc}
                        className={`p-2.5 rounded-lg border text-xs transition-all ${
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
                    onClick={() => setMode('merge')}
                    className={`p-2.5 rounded-lg border text-xs text-left transition-all ${
                      mode === 'merge' ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <span className="font-medium">Merge</span>
                    <span className="block opacity-70 text-[10px] mt-0.5">Create new, update matching IDs</span>
                  </button>
                  <button
                    onClick={() => setMode('replace')}
                    className={`p-2.5 rounded-lg border text-xs text-left transition-all ${
                      mode === 'replace' ? 'border-cs-red bg-cs-red/5 text-cs-red' : 'border bg-card text-muted-foreground hover:border-ring/30'
                    }`}
                  >
                    <span className="font-medium">Replace</span>
                    <span className="block opacity-70 text-[10px] mt-0.5">Wipe existing first, then import</span>
                  </button>
                </div>
              </div>

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
                    <span className="text-[10px] text-muted-foreground">.xml (ReqIF) · .sysml (SysML v2)</span>
                  </>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept=".xml,.reqif,.sysml,.txt,application/xml,text/xml"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setFile(f); setError(''); setResult(null); }
                  }}
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-lg p-3">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
                </div>
              )}

              {result && (
                <div className="flex items-start gap-2 text-xs text-cs-green bg-cs-green/10 rounded-lg p-3">
                  <CheckCircle2 size={14} className="shrink-0 mt-0.5" />
                  <span>
                    Imported <b>{result.format}</b>: {result.created} created, {result.updated} updated,{' '}
                    {result.verification_cases} verification cases, {result.traces_added} traces
                    {result.skipped > 0 && <>, {result.skipped} skipped</>}.
                  </span>
                </div>
              )}

              <div className="flex gap-2 pt-2 border-t">
                <button
                  onClick={handleImport}
                  disabled={!file || busy}
                  className="btn-primary flex-1 justify-center disabled:opacity-50"
                >
                  {busy ? (<><Loader size={14} className="animate-spin" /> Importing...</>) : (<><FileUp size={14} /> Import</>)}
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
