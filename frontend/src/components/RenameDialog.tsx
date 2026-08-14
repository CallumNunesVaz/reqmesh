import { useEffect, useRef, useState, useId } from 'react';
import { AlertTriangle, Loader, Tag, X } from 'lucide-react';
import Modal from './Modal';

interface Props {
  open: boolean;
  onClose: () => void;
  currentId: string;
  /** Singular noun for the entity being renamed, e.g. "requirement". */
  entityLabel?: string;
  /** The default: the parent's prefix plus the next free slot. Fetched lazily
   *  so the scheme lives in one place — the server. When absent (an entity
   *  with no naming scheme), the field starts from the current id. */
  suggest?: () => Promise<string>;
  onRename: (newId: string) => Promise<{ children: string[]; relinked: string[] }>;
}

/**
 * Rename an entity (a requirement, a component).
 *
 * An id is the YAML filename, every child's parent pointer, and every relation
 * target in the project, so this is a bigger action than it looks. The dialog
 * says what else will move before it happens, and reports what actually did.
 */
export default function RenameDialog({ open, onClose, currentId, entityLabel = 'requirement', suggest, onRename }: Props) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState<{ children: string[]; relinked: string[] } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const newId = useId();

  useEffect(() => {
    if (!open) return;
    setValue(''); setError(''); setDone(null); setBusy(true);
    const next = suggest
      ? suggest()
      : Promise.resolve(currentId);
    next
      .then((s) => setValue(s))
      // A failed suggestion must not block a manual rename — the field just
      // starts from the current id instead.
      .catch(() => setValue(currentId))
      .finally(() => {
        setBusy(false);
        setTimeout(() => inputRef.current?.select(), 50);
      });
  }, [open, currentId, suggest]);

  const submit = async () => {
    const next = value.trim();
    if (!next || next === currentId) { onClose(); return; }
    setBusy(true); setError('');
    try {
      setDone(await onRename(next));
    } catch (e: any) {
      setError(e?.message || 'Rename failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} panelClassName="w-full max-w-md p-6">
      <button
        onClick={onClose}
        title="Close"
        className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors"
      >
        <X size={18} />
      </button>

      <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2">
        <Tag size={17} /> Rename {entityLabel}
      </h2>

            {done ? (
              <>
                <p className="text-xs text-muted-foreground mb-4">
                  <span className="font-mono text-foreground">{currentId}</span> is now{' '}
                  <span className="font-mono text-foreground">{value}</span>.
                </p>
                <div className="text-xs bg-muted/50 border rounded-lg p-3 space-y-1 mb-4">
                  <div>{done.children.length} child {entityLabel}{done.children.length === 1 ? '' : 's'} repointed</div>
                  <div>{done.relinked.length} reference{done.relinked.length === 1 ? '' : 's'} rewritten</div>
                </div>
                <button onClick={onClose} className="btn-primary w-full justify-center">Done</button>
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-4">
                  Renaming moves the record and repoints every child and relation that
                  referred to it. The suggested id follows this project's naming scheme;
                  any id that fits the scheme is accepted.
                </p>

                <label className="label" htmlFor={newId}>New id</label>
                <input
                  ref={inputRef}
                  id={newId}
                  aria-label="New id"
                  className="input font-mono w-full mt-1"
                  value={value}
                  disabled={busy}
                  onChange={(e) => { setValue(e.target.value); setError(''); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose(); }}
                />
                <p className="text-[10px] text-muted-foreground mt-1">
                  Currently <span className="font-mono">{currentId}</span>
                </p>

                {error && (
                  <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-lg p-3 mt-3">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
                  </div>
                )}

                <div className="flex gap-2 pt-4 mt-4 border-t">
                  <button
                    onClick={submit}
                    disabled={busy || !value.trim() || value.trim() === currentId}
                    className="btn-primary flex-1 justify-center disabled:opacity-50"
                  >
                    {busy ? (<><Loader size={14} className="animate-spin" /> Working...</>) : 'Rename'}
                  </button>
                  <button onClick={onClose} className="btn-secondary justify-center">Cancel</button>
                </div>
              </>
            )}
    </Modal>
  );
}
