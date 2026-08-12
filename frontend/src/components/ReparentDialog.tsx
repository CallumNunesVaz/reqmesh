import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, CornerUpLeft, Loader, Search, X } from 'lucide-react';
import { validParents, type Node } from '../lib/hierarchy';
import Modal from './Modal';

export interface ReparentTarget extends Node {
  name?: string;
}

export interface RenamePreview {
  from: string;
  to: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Every candidate in the tree; the moving rows' own branches are filtered out. */
  items: ReparentTarget[];
  movingIds: string[];
  /** Destination chosen already — a drop names its target, so the dialog
   *  opens on the confirm step instead of asking again. `undefined` means
   *  nothing was chosen; `null` means top level. */
  initialParent?: string | null;
  /** Whether this tree renames ids when the destination prefix differs.
   *  Components never do — only requirements. */
  supportsRePrefix?: boolean;
  /** Ask the server what the move would rename, without performing it. */
  preview?: (parent: string | null, rePrefix: boolean) => Promise<RenamePreview[]>;
  onConfirm: (parent: string | null, rePrefix: boolean) => Promise<void>;
}

/**
 * Choose a new parent, then confirm — with the id renames spelled out first.
 *
 * This replaces a free-text "Parent ID" box. That box was three problems at
 * once: a typo silently created an orphan, nothing stopped you naming a
 * descendant (a cycle), and the client always sent re_prefix=true, so an
 * ordinary move could rewrite a whole subtree's ids across the project with no
 * warning and no way back — there is no rename endpoint to undo it with.
 *
 * So re-prefixing is opt-in here, and ticking it shows exactly which ids
 * change before anything is written.
 */
export default function ReparentDialog({
  open, onClose, items, movingIds, initialParent, supportsRePrefix = false, preview, onConfirm,
}: Props) {
  const [query, setQuery] = useState('');
  const [parent, setParent] = useState<string | null>(null);
  const [chosen, setChosen] = useState(false);
  const [rePrefix, setRePrefix] = useState(false);
  const [renames, setRenames] = useState<RenamePreview[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  const candidates = useMemo(
    () => validParents(items, movingIds),
    [items, movingIds],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return candidates.slice(0, 200);
    return candidates
      .filter((c) => c.id.toLowerCase().includes(q) || (c.name ?? '').toLowerCase().includes(q))
      .slice(0, 200);
  }, [candidates, query]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setParent(initialParent === undefined ? null : initialParent);
    setChosen(initialParent !== undefined);
    setRePrefix(false); setRenames([]); setError(''); setBusy(false);
    if (initialParent !== undefined) return;
    const t = setTimeout(() => searchRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open, initialParent]);

  // Re-run the preview whenever the destination or the re-prefix choice
  // changes: a stale rename table describing a different move is worse than
  // none, because it is what the user is deciding on.
  useEffect(() => {
    if (!open || !chosen || !preview) return;
    let cancelled = false;
    setBusy(true); setError('');
    preview(parent, rePrefix)
      .then((r) => { if (!cancelled) setRenames(r); })
      .catch((e: any) => { if (!cancelled) setError(e?.message || 'Could not preview the move'); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [open, chosen, parent, rePrefix, preview]);

  const confirm = async () => {
    setBusy(true); setError('');
    try {
      await onConfirm(parent, rePrefix);
      onClose();
    } catch (e: any) {
      setError(e?.message || 'Move failed');
      setBusy(false);
    }
  };

  const destinationLabel = parent === null
    ? 'the top level'
    : `${parent}${items.find((i) => i.id === parent)?.name ? ` — ${items.find((i) => i.id === parent)!.name}` : ''}`;

  return (
    <Modal open={open} onClose={onClose} panelClassName="w-full max-w-lg p-6">
      <button
        onClick={onClose}
        title="Close"
        className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors"
      >
        <X size={18} />
      </button>

      <h2 className="text-lg font-bold text-foreground mb-1">
        Move {movingIds.length} {movingIds.length === 1 ? 'item' : 'items'}
      </h2>

            {!chosen ? (
              <>
                <p className="text-xs text-muted-foreground mb-4">
                  Choose a new parent. The items being moved, and everything beneath them,
                  are not offered — that would create a cycle.
                </p>
                <div className="relative mb-2">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    ref={searchRef}
                    className="input text-sm w-full pl-9"
                    placeholder="Search by id or name..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <div className="max-h-72 overflow-y-auto border rounded-lg divide-y divide-border/60">
                  <button
                    onClick={() => { setParent(null); setChosen(true); }}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-muted/50 flex items-center gap-2"
                  >
                    <CornerUpLeft size={13} className="text-muted-foreground" />
                    <span className="font-medium text-foreground">Top level</span>
                    <span className="text-muted-foreground">(no parent)</span>
                  </button>
                  {filtered.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => { setParent(c.id); setChosen(true); }}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-muted/50"
                    >
                      <span className="font-mono text-foreground">{c.id}</span>
                      {c.name && <span className="text-muted-foreground ml-2">{c.name}</span>}
                    </button>
                  ))}
                  {filtered.length === 0 && (
                    <div className="px-3 py-6 text-xs text-muted-foreground text-center">
                      No eligible parent matches that search.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-4 flex items-center gap-2 flex-wrap">
                  Moving to <ArrowRight size={12} />
                  <span className="font-mono text-foreground">{destinationLabel}</span>
                  <button
                    onClick={() => { setChosen(false); setRenames([]); }}
                    className="text-primary hover:underline"
                  >
                    change
                  </button>
                </p>

                {supportsRePrefix && (
                  <label className="flex items-start gap-2 text-xs text-muted-foreground mb-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rePrefix}
                      onChange={(e) => setRePrefix(e.target.checked)}
                      className="rounded border-border mt-0.5"
                    />
                    <span>
                      Renumber ids to match the destination prefix
                      <span className="block text-[10px] opacity-80">
                        Off by default: renaming rewrites relation targets across the whole
                        project and cannot be undone.
                      </span>
                    </span>
                  </label>
                )}

                {busy && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                    <Loader size={13} className="animate-spin" /> Working out what would change...
                  </div>
                )}

                {!busy && renames.length > 0 && (
                  <div className="text-xs bg-destructive/5 border border-destructive/30 rounded-lg p-3 mb-3">
                    <div className="flex items-center gap-2 text-destructive font-medium mb-2">
                      <AlertTriangle size={13} />
                      {renames.length} id{renames.length === 1 ? '' : 's'} will be renamed — this cannot be undone
                    </div>
                    <div className="max-h-40 overflow-y-auto font-mono space-y-0.5">
                      {renames.map((r) => (
                        <div key={r.from} className="text-muted-foreground">
                          {r.from} <span className="text-foreground">→ {r.to}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!busy && chosen && renames.length === 0 && !error && (
                  <p className="text-xs text-muted-foreground mb-3">
                    No ids change. Only the parent is updated.
                  </p>
                )}

                {error && (
                  <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-lg p-3 mb-3">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
                  </div>
                )}

                <div className="flex gap-2 pt-2 border-t">
                  <button
                    onClick={confirm}
                    disabled={busy}
                    className="btn-primary flex-1 justify-center disabled:opacity-50"
                  >
                    Move
                  </button>
                  <button onClick={onClose} className="btn-secondary justify-center">Cancel</button>
                </div>
              </>
            )}
    </Modal>
  );
}
