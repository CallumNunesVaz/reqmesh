import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Check, X } from 'lucide-react';
import { api, type Comment } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useToasts } from './Toast';
import { useConfirm } from './ConfirmDialog';

/** Read/write comment thread for any entity.
 *
 *  Replaces the inline comment rendering that lived inside
 *  RequirementDetailPage and was unavailable everywhere else.
 *  Mounts in the same places 032 mounted HistoryPanel.
 */
export function CommentThread({ entityKind, entityId }: {
  entityKind: string;
  entityId: string;
}): JSX.Element {
  const { projectId } = useParams<{ projectId: string }>();
  const [comments, setComments] = useState<Comment[]>([]);
  const [newText, setNewText] = useState('');
  const [busy, setBusy] = useState(false);
  const canEdit = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();
  const showConfirm = useConfirm();

  const load = () => {
    if (!projectId) return;
    api.listComments(projectId, entityKind, entityId)
      .then(setComments)
      .catch(() => {});
  };

  useEffect(load, [projectId, entityKind, entityId]);

  const submit = async () => {
    if (!projectId || !newText.trim()) return;
    setBusy(true);
    try {
      await api.createComment(projectId, {
        entity_kind: entityKind,
        entity_id: entityId,
        text: newText.trim(),
      });
      addToast('success', 'Comment added');
      setNewText('');
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to post comment');
    } finally {
      setBusy(false);
    }
  };

  const toggleResolved = async (c: Comment) => {
    if (!projectId) return;
    try {
      await api.updateComment(projectId, c.id, { resolved: !c.resolved });
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to update comment');
    }
  };

  const remove = async (c: Comment) => {
    if (!projectId) return;
    const ok = await showConfirm('Delete this comment?', 'Delete Comment', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    try {
      await api.deleteComment(projectId, c.id);
      addToast('success', 'Comment deleted');
      load();
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to delete comment');
    }
  };

  const sorted = [...comments].sort(
    (a, b) => new Date(a.created).getTime() - new Date(b.created).getTime(),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm text-card-foreground">
          Comments ({comments.length})
        </h2>
      </div>

      {canEdit && (
        <div className="flex gap-1.5">
          <input
            className="input text-xs flex-1"
            placeholder="Write a comment..."
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit();
              if (e.key === 'Escape') setNewText('');
            }}
          />
          <button
            onClick={submit}
            disabled={busy || !newText.trim()}
            className="btn-primary text-xs"
          >
            {busy ? '...' : 'Send'}
          </button>
        </div>
      )}

      {sorted.length === 0 && (
        <p className="text-xs text-muted-foreground">No comments yet.</p>
      )}

      {sorted.map((c) => {
        const relative = relativeTime(new Date(c.created));
        return (
          <div
            key={c.id}
            className={`flex items-start gap-3 p-2.5 rounded-lg text-xs ${
              c.resolved ? 'bg-muted/30 opacity-60' : 'bg-accent/30'
            }`}
          >
            <span
              className="w-1 self-stretch rounded-full shrink-0"
              style={{ background: 'hsl(var(--primary) / 0.4)' }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-medium text-foreground">{c.author}</span>
                <span className="text-muted-foreground" title={c.created}>
                  {relative}
                </span>
                {c.resolved && (
                  <span className="badge bg-cs-green/10 text-cs-green text-4xs">
                    Resolved
                  </span>
                )}
              </div>
              <p className="text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {c.text}
              </p>
            </div>
            {canEdit && (
              <div className="flex items-center gap-0.5 shrink-0">
                <button
                  onClick={() => toggleResolved(c)}
                  className={`p-1 rounded-md hover:bg-accent transition-colors ${
                    c.resolved
                      ? 'text-cs-green'
                      : 'text-muted-foreground hover:text-cs-green'
                  }`}
                  title={c.resolved ? 'Mark unresolved' : 'Mark resolved'}
                >
                  <Check size={12} />
                </button>
                <button
                  onClick={() => remove(c)}
                  className="p-1 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  title="Delete comment"
                >
                  <X size={12} />
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function relativeTime(date: Date): string {
  const now = Date.now();
  const diff = now - date.getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}
