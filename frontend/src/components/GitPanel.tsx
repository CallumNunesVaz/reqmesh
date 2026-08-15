import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  GitBranch, Clock, User, RotateCw, AlertTriangle,
  CheckCircle, XCircle, Plug, Unplug, Trash2, Upload,
  PlusCircle, KeyRound, Copy,
} from 'lucide-react';
import { api, type GitStatus, type GitKeyInfo } from '../api/client';
import { useToasts } from './Toast';
import { useConfirm } from './ConfirmDialog';
import { copyText } from '../lib/clipboard';

interface Props {
  projectId: string;
  isAdmin: boolean;
  canEdit: boolean;
  /** The current remote URL as stored in project settings (un-redacted).
   *  Used by the Test Connection button. */
  remoteUrl: string;
  /** Called after any action that changes the remote URL so the parent
   *  can re-read project settings. */
  onRemoteChanged?: () => void;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

/** Extract a displayable host+path from a redacted remote URL.
 *  ``https://***@github.com/acme/repo.git`` → ``github.com/acme/repo`` */
function remoteHost(redacted: string): string {
  if (!redacted) return '';
  // Strip credentials
  let u = redacted.replace(/\/\/[^@]*@/, '//');
  // Strip scheme
  u = u.replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//, '');
  // Strip trailing .git
  u = u.replace(/\.git$/, '');
  return u;
}

export default function GitPanel({ projectId, isAdmin, canEdit, remoteUrl, onRemoteChanged }: Props) {
  const { addToast } = useToasts();
  const showConfirm = useConfirm();

  const [status, setStatus] = useState<GitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-action loading states
  const [initialising, setInitialising] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean; error?: string; branches?: string[]; branch_count?: number;
  } | null>(null);
  const [removing, setRemoving] = useState(false);
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);
  const [togglingHook, setTogglingHook] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  // Deploy key (admin-only)
  const [keyInfo, setKeyInfo] = useState<GitKeyInfo | null>(null);
  const [loadingKey, setLoadingKey] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle');

  // Git log
  const [commits, setCommits] = useState<Array<{
    hash: string; author: string; date: string; message: string;
  }>>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchStatus = useCallback(async () => {
    setError(null);
    try {
      const s = await api.gitStatus(projectId);
      setStatus(s);
    } catch (err: any) {
      setError(err.message || 'Failed to load git status');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const fetchHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await api.gitLog(projectId, 50);
      setCommits(res.commits || []);
    } catch {
      // Non-critical — status already tells us the repo state
    } finally {
      setLoadingHistory(false);
    }
  }, [projectId]);

  const fetchKey = useCallback(async () => {
    if (!isAdmin) { setLoadingKey(false); return; }
    setLoadingKey(true);
    try {
      setKeyInfo(await api.gitGetKey(projectId));
    } catch {
      // 404 is the expected "no key" state; any other error also renders empty.
      setKeyInfo(null);
    } finally {
      setLoadingKey(false);
    }
  }, [projectId, isAdmin]);

  useEffect(() => {
    fetchStatus();
    fetchHistory();
    fetchKey();
  }, [fetchStatus, fetchHistory, fetchKey]);

  const afterAction = async () => {
    await fetchStatus();
    await fetchHistory();
    onRemoteChanged?.();
  };

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleInit = async () => {
    setInitialising(true);
    try {
      await api.gitInit(projectId);
      addToast('success', 'Repository initialised');
      await afterAction();
    } catch (err: any) {
      addToast('error', err.message || 'Failed to initialise');
    } finally {
      setInitialising(false);
    }
  };

  const handlePush = async () => {
    setPushing(true);
    try {
      await api.gitPush(projectId);
      addToast('success', 'Push succeeded');
      await afterAction();
    } catch (err: any) {
      addToast('error', err.message || 'Push request failed');
    } finally {
      setPushing(false);
    }
  };

  const handleTestRemote = async () => {
    if (!remoteUrl.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.gitTestRemote(projectId, remoteUrl.trim());
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ ok: false, error: err.message || 'Request failed' });
    } finally {
      setTesting(false);
    }
  };

  const handleDeleteRemote = async () => {
    setRemoving(true);
    try {
      await api.gitDeleteRemote(projectId);
      addToast('success', 'Remote removed');
      setShowRemoveConfirm(false);
      await afterAction();
    } catch (err: any) {
      addToast('error', err.message || 'Failed to remove remote');
    } finally {
      setRemoving(false);
    }
  };

  const handleToggleHook = async () => {
    setTogglingHook(true);
    try {
      if (status?.hook_installed) {
        await api.gitUninstallHook(projectId);
        addToast('success', 'Pre-commit hook uninstalled');
      } else {
        await api.gitInstallHook(projectId);
        addToast('success', 'Pre-commit hook installed');
      }
      await afterAction();
    } catch (err: any) {
      addToast('error', err.message || 'Hook operation failed');
    } finally {
      setTogglingHook(false);
    }
  };

  const handleRestore = async (hash: string) => {
    if (!canEdit) return;
    const ok = await showConfirm(
      `Restore project to commit ${hash.slice(0, 8)}? ` +
      'This will restore all files to that state and create a new commit ' +
      'recording the restoration.',
      'Restore from History',
    );
    if (!ok) return;
    setRestoring(hash);
    try {
      await api.gitRestore(projectId, hash);
      await fetchHistory();
      await fetchStatus();
      addToast('success', `Restored to ${hash.slice(0, 8)}`);
    } catch (err: any) {
      addToast('error', err.message || 'Restore failed');
    } finally {
      setRestoring(null);
    }
  };

  const handleGenerateKey = async () => {
    setGenerating(true);
    try {
      setKeyInfo(await api.gitCreateKey(projectId));
      addToast('success', 'Deploy key generated');
    } catch (err: any) {
      addToast('error', err.message || 'Failed to generate key');
    } finally {
      setGenerating(false);
    }
  };

  const handleRotateKey = async () => {
    const ok = await showConfirm(
      'Rotating the deploy key discards the current private key. ' +
      'Pushes will fail until the new public key is registered at the remote host.',
      'Rotate Deploy Key',
    );
    if (!ok) return;
    setRotating(true);
    try {
      setKeyInfo(await api.gitRotateKey(projectId));
      addToast('success', 'Deploy key rotated');
    } catch (err: any) {
      addToast('error', err.message || 'Failed to rotate key');
    } finally {
      setRotating(false);
    }
  };

  const handleDeleteKey = async () => {
    const ok = await showConfirm(
      'Delete the deploy key? Pushes to SSH remotes will fail until a new key is generated and registered.',
      'Delete Deploy Key',
      { destructive: true },
    );
    if (!ok) return;
    setDeleting(true);
    try {
      await api.gitDeleteKey(projectId);
      setKeyInfo(null);
      addToast('success', 'Deploy key deleted');
    } catch (err: any) {
      addToast('error', err.message || 'Failed to delete key');
    } finally {
      setDeleting(false);
    }
  };

  const handleCopyKey = async () => {
    if (!keyInfo) return;
    const ok = await copyText(keyInfo.public_key);
    setCopied(ok ? 'ok' : 'fail');
    window.setTimeout(() => setCopied('idle'), 2000);
  };

  // ── Deploy key card (admin-only) ────────────────────────────────────────────

  const deployKeyCard = !isAdmin ? null : (
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="card p-5 mb-6"
    >
      <div className="flex items-center gap-2 mb-3">
        <KeyRound size={14} className="text-muted-foreground" />
        <h2 className="font-semibold text-sm text-card-foreground">SSH Deploy Key</h2>
      </div>

      {loadingKey ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <RotateCw size={14} className="animate-spin" />
          Loading deploy key…
        </div>
      ) : keyInfo ? (
        <div>
          <p className="text-xs text-muted-foreground mb-2">
            This project's deploy key. Paste the public key into your git host
            (GitHub / GitLab) as a deploy key with write access.
          </p>

          <div className="relative">
            <code className="block w-full text-[11px] font-mono bg-primary/5 border border-border/60 rounded p-2 pr-16 break-all">
              {keyInfo.public_key}
            </code>
            <button
              onClick={handleCopyKey}
              disabled={copied === 'ok'}
              className="btn-secondary text-[10px] absolute right-1 top-1"
              title="Copy public key"
            >
              {copied === 'ok' ? (
                <><CheckCircle size={11} className="mr-1" /> Copied</>
              ) : (
                <><Copy size={11} className="mr-1" /> Copy</>
              )}
            </button>
          </div>
          {copied === 'fail' && (
            <p className="text-[10px] text-amber-400 mt-1">
              Copy blocked — select the key above and copy manually.
            </p>
          )}

          <div className="flex flex-wrap gap-x-6 gap-y-1 mt-2 text-[11px] text-muted-foreground">
            <span>Fingerprint: <code className="font-mono text-card-foreground">{keyInfo.fingerprint}</code></span>
            <span>Created: {new Date(keyInfo.created).toLocaleString()}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 mt-3">
            <button
              onClick={handleRotateKey}
              disabled={rotating}
              className="btn-secondary text-[10px]"
            >
              {rotating ? (
                <><RotateCw size={11} className="animate-spin mr-1" /> Rotating…</>
              ) : (
                <><RotateCw size={11} className="mr-1" /> Rotate</>
              )}
            </button>
            <button
              onClick={handleDeleteKey}
              disabled={deleting}
              className="btn-secondary text-[10px] text-red-400 hover:text-red-300"
            >
              {deleting ? 'Deleting…' : <><Trash2 size={11} className="mr-1" /> Delete</>}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <p className="text-xs text-muted-foreground mb-3">
            No deploy key. Generate one to authenticate pushes to an SSH remote —
            the public half is shown here for pasting into GitHub or GitLab, and
            the private half never leaves the server.
          </p>
          <button
            onClick={handleGenerateKey}
            disabled={generating}
            className="btn-primary text-sm"
          >
            {generating ? (
              <><RotateCw size={14} className="animate-spin mr-1" /> Generating…</>
            ) : (
              <><PlusCircle size={14} className="mr-1" /> Generate Key</>
            )}
          </button>
        </div>
      )}
    </motion.div>
  );

  // ── Loading / error states ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="card p-5 mb-6">
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <RotateCw size={14} className="animate-spin" />
          Loading git status…
        </div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="card p-5 mb-6">
        <div className="flex items-center gap-2 text-red-400 text-sm">
          <AlertTriangle size={14} />
          {error}
        </div>
      </div>
    );
  }

  // ── Not a repository ───────────────────────────────────────────────────────

  if (!status?.is_repo) {
    return (
      <>
        <motion.div
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          className="card p-5 mb-6"
        >
          <div className="flex items-center gap-2 mb-3">
            <GitBranch size={14} className="text-muted-foreground" />
            <h2 className="font-semibold text-sm text-card-foreground">Version Control</h2>
          </div>

          <div className="text-center py-6">
            <GitBranch size={32} className="mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground mb-1">
              Not a git repository
            </p>
            <p className="text-xs text-muted-foreground/60 mb-4 max-w-md mx-auto">
              Initialise a git repository to version every change automatically.
              Every write to the project creates a commit, so you can always go
              back and see exactly who changed what and when.
            </p>
            {canEdit && (
              <button
                onClick={handleInit}
                disabled={initialising}
                className="btn-primary text-sm"
              >
                {initialising ? (
                  <><RotateCw size={14} className="animate-spin mr-1" /> Initialising…</>
                ) : (
                  <><PlusCircle size={14} className="mr-1" /> Initialise Repository</>
                )}
              </button>
            )}
          </div>
        </motion.div>
        {deployKeyCard}
      </>
    );
  }

  // ── Repository panel ───────────────────────────────────────────────────────

  const failedPush = status.last_push && !status.last_push.ok;
  const remoteDisplay = remoteHost(status.remote_url);

  // Build the status line
  const statusParts: string[] = [];
  if (remoteDisplay) {
    statusParts.push(`Connected to ${remoteDisplay}`);
  } else {
    statusParts.push('No remote configured');
  }
  if (status.ahead !== null && status.ahead > 0) {
    statusParts.push(`${status.ahead} commit${status.ahead !== 1 ? 's' : ''} to push`);
  }
  if (failedPush) {
    statusParts.push(`last push failed ${relativeTime(status.last_push!.at)}`);
  }

  return (
    <>
    <motion.div
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="card p-5 mb-6"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <GitBranch size={14} className="text-muted-foreground" />
        <h2 className="font-semibold text-sm text-card-foreground">Version Control</h2>
        <button
          onClick={() => { fetchStatus(); fetchHistory(); }}
          className="btn-secondary text-[10px] ml-auto"
          title="Refresh"
        >
          <RotateCw size={11} />
        </button>
      </div>

      {/* Status line */}
      <div className="flex items-center gap-2 mb-4 text-sm">
        {status.dirty && (
          <span className="flex items-center gap-1 text-amber-400 text-xs">
            <AlertTriangle size={12} />
            Uncommitted changes
          </span>
        )}
        {!status.dirty && (
          <span className="flex items-center gap-1 text-green-400/70 text-xs">
            <CheckCircle size={12} />
            Clean
          </span>
        )}
        <span className="text-muted-foreground text-xs">
          · {status.commit_count} commit{status.commit_count !== 1 ? 's' : ''}
          {status.branch ? ` on ${status.branch}` : ''}
        </span>
        {status.ahead !== null && status.ahead > 0 && (
          <span className="text-blue-400 text-xs">
            · {status.ahead} to push
          </span>
        )}
        {status.ahead === null && status.has_remote && (
          <span className="text-muted-foreground text-xs">
            · push state unknown
          </span>
        )}
      </div>

      {/* State sentence */}
      <p className="text-sm text-card-foreground mb-4">
        {statusParts.join(' · ')}
      </p>

      {/* Failed last push — the loudest thing on the panel */}
      {failedPush && (
        <div className="border border-red-500/30 bg-red-500/10 rounded-lg p-3 mb-4">
          <div className="flex items-start gap-2">
            <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-red-300 font-medium mb-1">
                Last push failed {relativeTime(status.last_push!.at)}
              </p>
              {status.last_push!.error && (
                <p className="text-xs text-red-400/80 break-all mb-2">
                  {status.last_push!.error}
                </p>
              )}
              {canEdit && (
                <button
                  onClick={handlePush}
                  disabled={pushing}
                  className="btn-primary text-xs"
                >
                  {pushing ? (
                    <><RotateCw size={12} className="animate-spin mr-1" /> Pushing…</>
                  ) : (
                    <><Upload size={12} className="mr-1" /> Push now</>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Push button (when no failure banner to show it).
          Gated on `has_remote`: with nothing configured there is nowhere to
          push, so the button could only ever report its own failure. A panel
          whose job is to make backup state legible should not offer an action
          that cannot succeed. */}
      {!failedPush && canEdit && status?.has_remote && (
        <div className="mb-4">
          <button
            onClick={handlePush}
            disabled={pushing}
            className="btn-secondary text-xs"
          >
            {pushing ? (
              <><RotateCw size={12} className="animate-spin mr-1" /> Pushing…</>
            ) : (
              <><Upload size={12} className="mr-1" /> Push now</>
            )}
          </button>
        </div>
      )}

      {/* Remote section */}
      <div className="border-t border-border/60 pt-4 mb-4">
        <h3 className="text-xs font-semibold text-card-foreground mb-2">Remote</h3>
        {status.has_remote ? (
          <div>
            <p className="text-xs text-muted-foreground font-mono mb-2 break-all">
              {status.remote_url}
            </p>

            {/* Admin controls */}
            {isAdmin && (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={handleTestRemote}
                  disabled={testing || !remoteUrl.trim()}
                  className="btn-secondary text-[10px]"
                >
                  {testing ? (
                    <><RotateCw size={11} className="animate-spin mr-1" /> Testing…</>
                  ) : (
                    'Test Connection'
                  )}
                </button>

                {!showRemoveConfirm ? (
                  <button
                    onClick={() => setShowRemoveConfirm(true)}
                    className="btn-secondary text-[10px] text-red-400 hover:text-red-300"
                    title={`Remove remote ${remoteDisplay}`}
                  >
                    <Trash2 size={11} className="mr-1" />
                    Remove Remote
                  </button>
                ) : (
                  <span className="flex items-center gap-2 text-xs">
                    <span className="text-red-400">
                      Remove {remoteDisplay}?
                    </span>
                    <button
                      onClick={handleDeleteRemote}
                      disabled={removing}
                      className="btn-primary text-[10px] px-2 py-0.5 bg-red-600 hover:bg-red-700"
                    >
                      {removing ? 'Removing…' : 'Yes, remove'}
                    </button>
                    <button
                      onClick={() => setShowRemoveConfirm(false)}
                      className="btn-secondary text-[10px] px-2 py-0.5"
                    >
                      Cancel
                    </button>
                  </span>
                )}
              </div>
            )}

            {/* Test result */}
            {testResult && (
              <div className={`mt-2 px-3 py-2 rounded text-xs ${
                testResult.ok
                  ? 'border border-green-500/20 bg-green-500/5 text-green-400'
                  : 'border border-red-500/20 bg-red-500/5 text-red-400'
              }`}>
                {testResult.ok ? (
                  <>
                    Remote is reachable.
                    {testResult.branch_count !== undefined && (
                      <> Found {testResult.branch_count} branch{testResult.branch_count !== 1 ? 'es' : ''}
                        {testResult.branches && testResult.branches.length > 0
                          ? `: ${testResult.branches.join(', ')}`
                          : '.'
                        }
                      </>
                    )}
                  </>
                ) : (
                  <>{testResult.error}</>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            No remote configured. Add a remote URL in the Git Integration section above.
          </p>
        )}
      </div>

      {/* Hook section */}
      <div className="border-t border-border/60 pt-4 mb-4">
        <h3 className="text-xs font-semibold text-card-foreground mb-2">Pre-commit Hook</h3>
        <p className="text-xs text-muted-foreground mb-2">
          {status.hook_installed
            ? 'The pre-commit hook validates requirement YAML files before every commit.'
            : 'No pre-commit hook installed. Install one to validate requirements before each commit.'}
        </p>
        {canEdit && (
          <button
            onClick={handleToggleHook}
            disabled={togglingHook}
            className="btn-secondary text-[10px]"
          >
            {togglingHook ? (
              <><RotateCw size={11} className="animate-spin mr-1" /> Working…</>
            ) : status.hook_installed ? (
              <><Unplug size={11} className="mr-1" /> Uninstall Hook</>
            ) : (
              <><Plug size={11} className="mr-1" /> Install Hook</>
            )}
          </button>
        )}
      </div>

      {/* Git History */}
      <div className="border-t border-border/60 pt-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-card-foreground">
            Git History
          </h3>
          <button
            onClick={fetchHistory}
            className="btn-secondary text-[10px]"
            disabled={loadingHistory}
          >
            <RotateCw size={11} className={loadingHistory ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {commits.length === 0 ? (
          <div className="text-center py-8">
            <Clock size={32} className="mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">No commits yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              Make changes to the project data — commits are created automatically.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border/60 max-h-[400px] overflow-y-auto">
            {commits.map((commit) => (
              <div
                key={commit.hash}
                className="flex items-start gap-3 py-2.5 px-2 rounded hover:bg-accent/40 group transition-colors"
              >
                <div className="shrink-0 mt-0.5">
                  <div className="w-2 h-2 rounded-full bg-primary/40" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <code className="text-[11px] font-mono text-primary bg-primary/5 px-1.5 py-0.5 rounded">
                      {commit.hash.slice(0, 8)}
                    </code>
                    <span className="text-[11px] text-muted-foreground">
                      {relativeTime(commit.date)}
                    </span>
                  </div>
                  <p className="text-xs text-foreground truncate">{commit.message}</p>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground/70">
                    <span className="flex items-center gap-1">
                      <User size={10} />
                      {commit.author}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock size={10} />
                      {new Date(commit.date).toLocaleString()}
                    </span>
                  </div>
                </div>
                {canEdit && (
                  <button
                    onClick={() => handleRestore(commit.hash)}
                    disabled={restoring === commit.hash}
                    className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity btn-secondary text-[10px] px-2 py-1 mt-0.5"
                    title="Restore project to this commit"
                  >
                    {restoring === commit.hash ? (
                      <RotateCw size={11} className="animate-spin" />
                    ) : (
                      <><RotateCw size={11} /> Restore</>
                    )}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
    {deployKeyCard}
    </>
  );
}
