import { useEffect, useState } from 'react';
import { X, AlertTriangle } from 'lucide-react';
import { api, type Requirement } from '../api/client';
import type { RequirementCreate } from '../api/generated/writeModels';
import { useUndoStore } from '../store/undo';
import { splitDescription } from '../lib/splitText';
import type { SplitCandidate } from '../lib/splitText';
import Modal from './Modal';

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: string;
  source: Requirement;
  onSplit: (createdIds: string[]) => void;
}

interface Row {
  id: number;
  candidate: SplitCandidate;
  selected: boolean;
  name: string;
}

export default function SplitRequirementDialog({ open, onClose, projectId, source, onSplit }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    const candidates = splitDescription(source.description);
    setRows(candidates.map((c, i) => ({ id: i, candidate: c, selected: true, name: c.name })));
    setError('');
  }, [open, source.description]);

  const selectedCount = rows.filter((r) => r.selected).length;

  /** 1-based position among the *selected* rows — the order they will be
   *  created in — or 0 for a row that is not being created. */
  const ordinalOf = (id: number) => {
    let n = 0;
    for (const r of rows) {
      if (!r.selected) continue;
      n += 1;
      if (r.id === id) return n;
    }
    return 0;
  };

  const toggleRow = (id: number) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, selected: !r.selected } : r)));
  };

  const setName = (id: number, name: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, name } : r)));
  };

  const handleSplit = async () => {
    const selected = rows.filter((r) => r.selected);
    if (selected.length === 0) return;

    setBusy(true);
    setError('');

    const createdIds: string[] = [];
    const createdData: { id: string; data: RequirementCreate }[] = [];

    for (const row of selected) {
      try {
        const uid = await api.getNextUid(projectId, source.id);
        const data: RequirementCreate = {
          id: uid.next_id,
          name: row.name,
          description: `<p>${row.candidate.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')}</p>`,
          type: source.type,
          priority: source.priority,
          parent: source.id,
        };
        await api.createRequirement(projectId, data);
        createdIds.push(uid.next_id);
        createdData.push({ id: uid.next_id, data });
      } catch (err: any) {
        const landed = createdIds.length;
        setError(
          landed > 0
            ? `${landed} child${landed === 1 ? '' : 'ren'} created before the error: ${err?.message || 'Creation failed'}`
            : err?.message || 'Creation failed',
        );
        setBusy(false);
        return;
      }
    }

    if (createdIds.length > 0) {
      useUndoStore.getState().push({
        description: `Split ${source.id} into ${createdIds.length} children`,
        undo: async () => {
          for (const id of createdIds) {
            await api.deleteRequirement(projectId, id, true);
          }
        },
        redo: async () => {
          for (const { data } of createdData) {
            await api.createRequirement(projectId, data);
          }
        },
      });
    }

    setBusy(false);
    onClose();
    onSplit(createdIds);
  };

  const onDialogClose = () => {
    if (!busy) onClose();
  };

  return (
    <Modal open={open} onClose={onDialogClose} panelClassName="w-full max-w-2xl max-h-[85vh] flex flex-col">
      <div className="flex items-center justify-between p-4 border-b shrink-0">
        <h2 className="font-semibold text-sm text-card-foreground">
          Split {source.id} into child requirements
        </h2>
        <button onClick={onDialogClose} className="p-1 text-muted-foreground hover:text-foreground" disabled={busy}>
          <X size={16} />
        </button>
      </div>

            <div className="p-4 text-xs text-muted-foreground shrink-0">
              {source.id} keeps its current description. Nothing is removed from it.
            </div>

            {error && (
              <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-cs-red/10 border border-cs-red/20 text-cs-red text-sm flex items-start gap-2 shrink-0">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="overflow-y-auto p-4 space-y-4 flex-1">
              {rows.map((row) => (
                <div key={row.id} className="border rounded-lg p-3">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={row.selected}
                      onChange={() => toggleRow(row.id)}
                      disabled={busy}
                      className="mt-1.5"
                    />
                    <div className="flex-1 min-w-0">
                      {/* The ordinal lives here, not in the name. It is a live
                          count of what is ticked, so it can't go stale the way
                          a "1 of 3" written into the data would once a child is
                          deleted or the parent is split again. */}
                      <span className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                        {ordinalOf(row.id) ? `Child ${ordinalOf(row.id)} of ${selectedCount}` : 'Not included'}
                      </span>
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) => setName(row.id, e.target.value)}
                        disabled={busy || !row.selected}
                        className="input text-sm font-medium w-full"
                      />
                      <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">
                        {row.candidate.text}
                      </p>
                    </div>
                  </label>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between p-4 border-t shrink-0">
              <span className="text-xs text-muted-foreground">
                {selectedCount} of {rows.length} selected
              </span>
              <div className="flex gap-2">
                <button onClick={onDialogClose} className="btn-secondary text-xs" disabled={busy}>
                  Cancel
                </button>
                <button
                  onClick={handleSplit}
                  className="btn-primary text-xs"
                  disabled={busy || selectedCount === 0}
                >
                  {busy ? 'Creating…' : `Create ${selectedCount} child${selectedCount === 1 ? '' : 'ren'}`}
                </button>
              </div>
            </div>
    </Modal>
  );
}
