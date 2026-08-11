import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
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

  // The dependency array is the whole "fetch once per itemId" mechanism: React
  // re-runs this only when projectId or itemId actually change identity. A ref
  // guard comparing the previous itemId was tried and is subtly broken — it
  // initialises to the current id, so the first render already compares equal
  // and returns before fetching, and the panel renders empty forever.
  useEffect(() => {
    if (!projectId || !open) return;
    let alive = true;
    setEntries(null);
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

  if (error) {
    return <p className="text-xs text-muted-foreground">{error}</p>;
  }

  // Loading and empty must not render the same string: while they did, a panel
  // that never fetched was indistinguishable from one with nothing to show.
  if (!entries) {
    return <p className="text-xs text-muted-foreground">Loading history…</p>;
  }

  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">No recorded changes</p>;
  }

  return (
    <div className="space-y-2">
      {entries.map((entry, i) => {
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
                    <div key={field}>
                      <span className="font-mono text-muted-foreground">{field}: </span>
                      <span className="line-through text-red-400">{before}</span>
                      <span className="mx-1 text-muted-foreground">→</span>
                      <span className="text-emerald-400">{after}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
