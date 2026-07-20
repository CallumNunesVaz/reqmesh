import { useEffect, useState, useCallback, useRef } from 'react';
import {
  ShieldCheck, RefreshCw, Download, CheckCircle2, AlertTriangle, Loader,
  ArrowUpCircle, GitBranch, Server, ExternalLink, Terminal, X, Upload,
} from 'lucide-react';
import { api, type SystemInfo, type UpdateCheck, type UpdateStatus, type BuildInfo } from '../api/client';
import { useAuthStore } from '../store/auth';

/** States during which the update is actively running and we should poll. */
const ACTIVE = new Set(['preparing', 'requested', 'in_progress']);

export default function SystemPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const [build, setBuild] = useState<BuildInfo | null>(null);
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const runCheck = useCallback(async (force: boolean) => {
    setChecking(true);
    setError('');
    try {
      setCheck(await api.checkUpdate(force));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update check failed');
    } finally {
      setChecking(false);
    }
  }, []);

  // Initial load: build info, runtime info, cached check, current status.
  useEffect(() => {
    if (!isAdmin) return;
    (async () => {
      try {
        const [b, i, s] = await Promise.all([api.getVersion(), api.systemInfo(), api.updateStatus()]);
        setBuild(b); setInfo(i); setStatus(s);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load system info');
      }
      runCheck(false);
    })();
  }, [isAdmin, runCheck]);

  // Poll status while an update is in flight. During the container swap the API
  // briefly disappears; we treat fetch errors as "still restarting" and keep going.
  useEffect(() => {
    const active = status && ACTIVE.has(status.state);
    if (!active) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.updateStatus();
        setStatus(s);
        if (s.state === 'completed' || s.state === 'failed') {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
          if (s.state === 'completed') {
            api.getVersion().then(setBuild).catch(() => {});
            runCheck(true);
          }
        }
      } catch {
        // API unreachable mid-swap — keep the "restarting" state and retry.
        setStatus((prev) => prev ? { ...prev, message: 'Restarting the application…' } : prev);
      }
    }, 3000);
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [status, runCheck]);

  const startUpdate = async () => {
    setStarting(true);
    setError('');
    try {
      const res = await api.startUpdate(check?.latest ?? undefined);
      setConfirming(false);
      setStatus({
        state: 'requested', target_version: res.target_version,
        message: 'Update requested; backing up and handing off to the updater…',
        updated_at: new Date().toISOString(), backup: res.backup,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start update');
    } finally {
      setStarting(false);
    }
  };

  const uploadUpdate = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setError('');
    try {
      const m = uploadFile.name.match(/v?(\d+\.\d+\.\d+)/);
      const res = await api.uploadUpdate(uploadFile, m?.[1]);
      setUploadFile(null);
      setStatus({
        state: 'requested', target_version: res.target_version || (m?.[1] ?? null),
        message: 'Image uploaded; backing up and handing off to the updater…',
        updated_at: new Date().toISOString(), backup: res.backup,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const dismiss = async () => {
    try { await api.dismissUpdate(); } catch { /* best effort */ }
    setStatus({ state: 'idle', target_version: null, message: '', updated_at: new Date().toISOString() });
  };

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto p-8 text-center">
        <ShieldCheck className="mx-auto mb-3 text-muted-foreground" size={32} />
        <h1 className="text-lg font-semibold">Administrator access required</h1>
        <p className="text-muted-foreground text-sm mt-1">System settings and updates are available to administrators only.</p>
      </div>
    );
  }

  const updateAvailable = check?.update_available;
  const active = status && ACTIVE.has(status.state);
  const completed = status?.state === 'completed';
  const failed = status?.state === 'failed';
  const repoUrl = info ? `https://github.com/${info.github_repo}` : '';

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-center gap-2">
        <Server size={20} className="text-primary" />
        <h1 className="text-xl font-semibold">System</h1>
      </div>

      {error && (
        <div className="card p-3 border-destructive/40 bg-destructive/10 text-sm flex items-center gap-2">
          <AlertTriangle size={16} className="text-destructive shrink-0" /> {error}
        </div>
      )}

      {/* ── Version card ─────────────────────────────────────────── */}
      <section className="card p-5">
        <h2 className="font-medium mb-3 flex items-center gap-2"><GitBranch size={16} /> Version</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Running</dt>
          <dd className="font-mono">v{build?.version ?? '…'} <span className="text-muted-foreground text-xs">({build?.channel})</span></dd>
          {build?.git_sha && (<><dt className="text-muted-foreground">Commit</dt><dd className="font-mono text-xs">{build.git_sha.slice(0, 12)}</dd></>)}
          {build?.built_at && (<><dt className="text-muted-foreground">Built</dt><dd className="text-xs">{build.built_at}</dd></>)}
          <dt className="text-muted-foreground">Repository</dt>
          <dd>{repoUrl ? <a className="text-primary hover:underline inline-flex items-center gap-1" href={repoUrl} target="_blank" rel="noreferrer">{info?.github_repo} <ExternalLink size={12} /></a> : '…'}</dd>
        </dl>
      </section>

      {/* ── Updates card ─────────────────────────────────────────── */}
      <section className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium flex items-center gap-2"><ArrowUpCircle size={16} /> Updates</h2>
          <button className="btn-ghost text-xs" onClick={() => runCheck(true)} disabled={checking || !!active}>
            <RefreshCw size={14} className={checking ? 'animate-spin' : ''} /> Check now
          </button>
        </div>

        {/* Active update progress */}
        {active && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 p-4 mb-3">
            <div className="flex items-center gap-2 font-medium text-sm">
              <Loader size={16} className="animate-spin text-primary" />
              Updating to v{status?.target_version}…
            </div>
            <p className="text-sm text-muted-foreground mt-1">{status?.message}</p>
            {status?.backup?.tag && (
              <p className="text-xs text-muted-foreground mt-2">Data backed up as <span className="font-mono">{status.backup.tag}</span> ({status.backup.projects.length} project{status.backup.projects.length === 1 ? '' : 's'}).</p>
            )}
            <p className="text-xs text-muted-foreground mt-2">You can leave this page — the update continues in the background.</p>
          </div>
        )}

        {/* Completed / failed banners */}
        {completed && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 mb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm"><CheckCircle2 size={16} className="text-emerald-500" /> Updated to v{status?.current}.</div>
              <button className="btn-ghost text-xs" onClick={dismiss}><X size={14} /> Dismiss</button>
            </div>
            <button className="btn-secondary mt-3 text-xs" onClick={() => window.location.reload()}>Reload the app</button>
          </div>
        )}
        {failed && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 mb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm"><AlertTriangle size={16} className="text-destructive" /> Update failed</div>
              <button className="btn-ghost text-xs" onClick={dismiss}><X size={14} /> Dismiss</button>
            </div>
            <p className="text-sm text-muted-foreground mt-1">{status?.message} Your data backup is intact; retry or update manually.</p>
          </div>
        )}

        {/* Check result */}
        {!active && (
          <>
            {check?.offline && <p className="text-sm text-muted-foreground">Offline mode is on — update checks are disabled.</p>}
            {check?.error && <p className="text-sm text-amber-500 flex items-center gap-2"><AlertTriangle size={14} /> {check.error}</p>}
            {!check?.offline && !check?.error && !updateAvailable && (
              <p className="text-sm text-muted-foreground flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-500" /> You're on the latest version (v{check?.current}).</p>
            )}

            {updateAvailable && !completed && (
              <div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
                <div className="flex items-center gap-2 font-medium">
                  <ArrowUpCircle size={18} className="text-primary" />
                  Version {check?.latest} is available
                  <span className="text-xs text-muted-foreground font-normal">(you have {check?.current})</span>
                </div>
                {check?.html_url && (
                  <a className="text-xs text-primary hover:underline inline-flex items-center gap-1 mt-1" href={check.html_url} target="_blank" rel="noreferrer">Release notes <ExternalLink size={11} /></a>
                )}
                {check?.notes && (
                  <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap text-xs bg-muted/40 rounded p-3 border">{check.notes}</pre>
                )}

                {info?.self_update_supported ? (
                  <div className="mt-4">
                    <button className="btn-primary" onClick={() => setConfirming(true)}>
                      <Download size={15} /> Update to v{check?.latest}
                    </button>
                    <p className="text-xs text-muted-foreground mt-2">Backs up all project data, then recreates the app on the new version. Brief downtime during restart.</p>
                  </div>
                ) : (
                  <GuidedInstructions info={info} check={check} />
                )}
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Update from file (offline / air-gapped) ──────────────── */}
      {info?.file_update_supported && !active && !completed && (
        <section className="card p-5">
          <h2 className="font-medium mb-1 flex items-center gap-2"><Upload size={16} /> Update from a file</h2>
          <p className="text-sm text-muted-foreground mb-3">
            For air-gapped servers. Upload a reqmesh image archive
            (<span className="font-mono text-xs">reqmesh-v&lt;version&gt;-image.tar.gz</span> from a release);
            it's loaded and applied without contacting GitHub.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <label className="btn-secondary cursor-pointer">
              <Upload size={15} /> Choose file
              <input
                type="file"
                accept=".tar,.tar.gz,.tgz,application/gzip,application/x-tar"
                className="hidden"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {uploadFile && (
              <span className="text-sm text-muted-foreground truncate max-w-[16rem]">
                {uploadFile.name} <span className="text-xs">({(uploadFile.size / 1048576).toFixed(0)} MB)</span>
              </span>
            )}
            <button className="btn-primary" onClick={uploadUpdate} disabled={!uploadFile || uploading}>
              {uploading ? <Loader size={15} className="animate-spin" /> : <Upload size={15} />}
              {uploading ? 'Uploading…' : 'Upload & update'}
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">Project data is backed up first, exactly as with an online update.</p>
        </section>
      )}

      {/* ── Confirm dialog ───────────────────────────────────────── */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setConfirming(false)}>
          <div className="card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold flex items-center gap-2"><Download size={18} /> Update to v{check?.latest}?</h3>
            <ul className="text-sm text-muted-foreground mt-3 space-y-1.5 list-disc pl-5">
              <li>All project data is backed up (a git tag per project) first.</li>
              <li>The app is recreated on the new image — expect a short restart.</li>
              <li>Project data is preserved; data migrations run automatically.</li>
            </ul>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
              <button className="btn-primary" onClick={startUpdate} disabled={starting}>
                {starting ? <Loader size={15} className="animate-spin" /> : <Download size={15} />} Update now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Copy-paste steps for deployments where the app can't self-update. */
function GuidedInstructions({ info, check }: { info: SystemInfo | null; check: UpdateCheck | null }) {
  const docker = info?.docker;
  const cmd = docker
    ? `docker compose -f docker-compose.prod.yml pull\ndocker compose -f docker-compose.prod.yml up -d`
    : `# download the new release, then\ntar -xzf reqmesh-v${check?.latest}.tar.gz\ncd reqmesh-v${check?.latest} && ./install.sh`;
  return (
    <div className="mt-4">
      <p className="text-sm flex items-center gap-2 text-muted-foreground">
        <Terminal size={14} /> One-click update isn't available in this deployment. Update manually:
      </p>
      <pre className="mt-2 text-xs bg-muted/40 rounded p-3 border overflow-auto whitespace-pre">{cmd}</pre>
      <p className="text-xs text-muted-foreground mt-2">
        {docker
          ? 'To enable one-click updates, run with the self-update profile: docker compose --profile self-update up -d.'
          : 'For one-click updates, deploy with Docker Compose and the self-update profile.'}
      </p>
    </div>
  );
}
