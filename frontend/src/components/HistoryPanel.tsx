import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { api, type HistoryEntry } from '../api/client';
import { useConfirm } from './ConfirmDialog';
import { useAuthStore } from '../store/auth';

/** Read-only audit trail for any entity.
 *
 *  Collapsed by default and fetched only once opened. The list pages mount one
 *  of these per card, so eager loading meant a project with fifty risks issued
 *  fifty history requests just to render the page — none of which the reader
 *  had asked for. `defaultOpen` is for the detail pages, where there is exactly
 *  one item and the history is part of what you came to see.
 */
export function HistoryPanel({ itemId, defaultOpen = false, onRestored }: {
  itemId: string;
  defaultOpen?: boolean;
  onRestored?: () => void;
}): JSX.Element {
  const { projectId } = useParams<{ projectId: string }>();
  const [open, setOpen] = useState(defaultOpen);
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(0);
  const showConfirm = useConfirm();
  const editable = useAuthStore((s) => s.canEdit());

  // Fetch lazily on first open, and again only when `refreshing` advances.
  // The key is "which item, at which refresh": collapsing and reopening keeps
  // the key identical, so an already-fetched panel never refetches, while an
  // explicit refresh (after a restore) advances `refreshing` and does. Keying
  // the effect on `open` alone was the old bug — it refetched on every reopen.
  const lastFetch = useRef<string | null>(null);

  // Entries belong to one item. Clearing them when the item changes is what
  // keeps the panel from showing the *previous* entity's history — and its
  // count — for as long as the new fetch takes. Deliberately not keyed on
  // `open`: collapsing must not throw away what has already been fetched, or
  // reopening would show "Loading…" and hit the network again.
  useEffect(() => {
    setEntries(null);
    setError('');
  }, [projectId, itemId]);

  useEffect(() => {
    if (!projectId || !open) return;
    const key = `${projectId}/${itemId}#${refreshing}`;
    if (lastFetch.current === key) return;
    lastFetch.current = key;
    let alive = true;
    setError('');
    api.getItemHistory(projectId, itemId)
      .then((data) => { if (alive) setEntries(data); })
      .catch((err: any) => { if (alive) setError(err?.message || 'Failed to load history'); });
    return () => { alive = false; };
  }, [projectId, itemId, open, refreshing]);

  const handleRestore = useCallback(async (entry: HistoryEntry) => {
    if (!projectId) return;
    const fieldNames = Object.keys(entry.changes);
    const fieldList = fieldNames.join(' and ');
    const message = `Restore ${fieldList} to ${fieldNames.length === 1 ? 'its' : 'their'} previous ${fieldNames.length === 1 ? 'value' : 'values'}?`;
    const ok = await showConfirm(message, 'Undo this change, keeping later edits');
    if (!ok) return;
    try {
      await api.restoreRequirementVersion(projectId, itemId, entry.id);
      setRefreshing((n) => n + 1);
      onRestored?.();
    } catch (e: any) {
      setError(e?.message || 'Restore failed');
    }
  }, [projectId, itemId, showConfirm, onRestored]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
      >
        Show change history
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-expanded
          aria-label="Collapse change history"
          className="shrink-0 p-0.5 -m-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
        >
          <ChevronDown size={14} className="rotate-180" />
        </button>
        {entries !== null && (
          <span className="text-xs text-muted-foreground">
            {entries.length} change{entries.length === 1 ? '' : 's'}
          </span>
        )}
      </div>
      {error ? (
        <p className="text-xs text-muted-foreground">{error}</p>
      ) : !entries ? (
        // Loading and empty must not render the same string: while they did, a
        // panel that never fetched was indistinguishable from one with nothing
        // to show.
        <p className="text-xs text-muted-foreground">Loading history…</p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-muted-foreground">No recorded changes</p>
      ) : (
        entries.map((entry) => {
          const ts = new Date(entry.timestamp).toLocaleString();
          const fieldNames = Object.keys(entry.changes);
          return (
            <div key={entry.id} className="text-xs py-1 px-2 rounded bg-muted/30">
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="font-medium text-foreground capitalize">{entry.action}</span>
                <span>{ts}</span>
                {entry.user && <span>by {entry.user}</span>}
                {editable && entry.action === 'update' && (
                  <button
                    type="button"
                    className="ml-auto text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
                    title="Undo this change, keeping later edits"
                    onClick={() => handleRestore(entry)}
                  >
                    Restore
                  </button>
                )}
              </div>
              {fieldNames.length > 0 && (
                <div className="mt-0.5 ml-2 space-y-0">
                  {fieldNames.map((field) => {
                    const before = String(entry.changes[field].before ?? '');
                    const after = String(entry.changes[field].after ?? '');
                    return (
                      <div key={field} className="flex items-baseline gap-1 min-w-0">
                        <span className="font-mono text-muted-foreground shrink-0">{field}: </span>
                        <span className="line-through text-cs-red truncate min-w-0" title={before}>{before}</span>
                        <span className="text-muted-foreground shrink-0">→</span>
                        <span className="text-cs-green truncate min-w-0" title={after}>{after}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
