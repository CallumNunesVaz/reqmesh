import { useEffect, useState, useCallback, useRef } from 'react';
import {
  ShieldCheck, RefreshCw, Download, CheckCircle2, AlertTriangle, Loader,
  ArrowUpCircle, GitBranch, Server, ExternalLink, Terminal, X, Upload,
  Monitor, Globe, Network, Clock, Power, FileText, Play, DownloadCloud, Copy,
} from 'lucide-react';
import { api, type SystemInfo, type UpdateCheck, type UpdateStatus, type BuildInfo } from '../api/client';
import { useAuthStore } from '../store/auth';
import BodyPortal from '../components/BodyPortal';

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
  const [restarting, setRestarting] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [deps, setDeps] = useState<Array<{ id: string; label: string; category: string; status: string; detail: string; has_e2e: boolean; install_guide: string }>>([]);
  const [testingDep, setTestingDep] = useState<string | null>(null);
  const [installDep, setInstallDep] = useState<{ id: string; label: string; guide: string } | null>(null);
  const [depError, setDepError] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const restartPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      api.listDependencies().then(setDeps).catch(() => {});
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

  const handleTestDep = async (depId: string) => {
    setTestingDep(depId);
    setDepError('');
    try {
      const result = await api.testDependency(depId);
      setDeps(prev => prev.map(d => d.id === depId
        ? { ...d, status: result.ok ? 'ok' : 'error', detail: result.detail || result.error || '' }
        : d));
    } catch (e) {
      setDepError(e instanceof Error ? e.message : 'Test failed');
    } finally {
      setTestingDep(null);
    }
  };

  // Docker deployments upload a Docker image archive (applied by the sidecar);
  // bare-metal installs upload a release bundle, staged for the next restart.
  const bundleMode = !!info?.bundle_update_supported && !info?.file_update_supported;

  const uploadUpdate = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setError('');
    try {
      if (bundleMode) {
        const res = await api.uploadBundle(uploadFile);
        setUploadFile(null);
        setStatus({
          state: 'staged', target_version: res.target_version,
          message: `v${res.target_version} is staged — restart to apply.`,
          updated_at: new Date().toISOString(), backup: res.backup,
        });
      } else {
        const m = uploadFile.name.match(/v?(\d+\.\d+\.\d+)/);
        const res = await api.uploadUpdate(uploadFile, m?.[1]);
        setUploadFile(null);
        setStatus({
          state: 'requested', target_version: res.target_version || (m?.[1] ?? null),
          message: 'Image uploaded; backing up and handing off to the updater…',
          updated_at: new Date().toISOString(), backup: res.backup,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  // Restart the app in place (re-exec). The connection drops briefly while the
  // process comes back — and, if a bundle is staged, applies on the way up — so
  // we poll /version until it answers again.
  const restart = async () => {
    setConfirmRestart(false);
    setRestarting(true);
    setError('');
    try {
      await api.restartApp();
    } catch {
      // The process may drop the request as it re-execs — that's expected.
    }
    const started = Date.now();
    if (restartPollRef.current) clearInterval(restartPollRef.current);
    restartPollRef.current = setInterval(async () => {
      try {
        const [b, s] = await Promise.all([api.getVersion(), api.updateStatus()]);
        if (restartPollRef.current) { clearInterval(restartPollRef.current); restartPollRef.current = null; }
        setBuild(b); setStatus(s); setRestarting(false);
        runCheck(true);
      } catch {
        if (Date.now() - started > 120000) {
          if (restartPollRef.current) { clearInterval(restartPollRef.current); restartPollRef.current = null; }
          setRestarting(false);
          setError('The app did not come back within two minutes — check the server logs.');
        }
      }
    }, 2000);
  };

  useEffect(() => () => { if (restartPollRef.current) clearInterval(restartPollRef.current); }, []);

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
  const staged = status?.state === 'staged';
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

      {/* ── System info card ─────────────────────────────────────── */}
      <section className="card p-5">
        <h2 className="font-medium mb-3 flex items-center gap-2"><Monitor size={16} /> Environment</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Globe size={13} className="inline mr-1" /> Hostname</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">{info?.fqdn ?? '…'}{info?.hostname !== info?.fqdn ? ` (${info?.hostname})` : ''}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Network size={13} className="inline mr-1" /> IP addresses</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">{(info?.internal_ips ?? []).join(', ') || '…'}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Monitor size={13} className="inline mr-1" /> OS</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">{info?.os ? `${info.os.system} ${info.os.release} (${info.os.machine})` : '…'}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Terminal size={13} className="inline mr-1" /> Python</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">{info?.os?.python ?? '…'}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Clock size={13} className="inline mr-1" /> App uptime</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">
            {info ? formatUptime(info.process_uptime_seconds) : '…'}
          </dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><Server size={13} className="inline mr-1" /> Working directory</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs truncate">{info?.working_directory ?? '…'}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><ShieldCheck size={13} className="inline mr-1" /> Running as</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">{info?.running_user ?? '…'}{info?.docker ? ' (Docker)' : ''}</dd>
          <dt className="text-muted-foreground col-span-2 @xl:col-span-1"><FileText size={13} className="inline mr-1" /> PDF reports</dt>
          <dd className="col-span-2 @xl:col-span-1 font-mono text-xs">
            {info == null ? '…' : info.latex_engine
              ? `LaTeX (${info.latex_engine})`
              : 'HTML fallback — no LaTeX engine'}
          </dd>
        </dl>
      </section>

      {/* ── System Dependencies ──────────────────────────────────── */}
      <section className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium flex items-center gap-2"><Server size={16} /> System Dependencies</h2>
          <button onClick={() => api.listDependencies().then(setDeps).catch(() => {})} className="btn-ghost p-1.5 rounded text-muted-foreground hover:text-foreground" title="Refresh">
            <RefreshCw size={14} />
          </button>
        </div>
        {depError && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">{depError}</div>
        )}
        <div className="space-y-2">
          {/* Group by category */}
          {(() => {
            const cats = [...new Set(deps.map(d => d.category))];
            return cats.map(cat => (
              <div key={cat}>
                <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-1">{cat}</h3>
                {deps.filter(d => d.category === cat).map(dep => (
                  <div key={dep.id} className="flex items-center gap-3 py-1.5 px-2 rounded text-sm hover:bg-accent/40 group">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      dep.status === 'ok' ? 'bg-cs-green' :
                      dep.status === 'missing' ? 'bg-cs-red' :
                      dep.status === 'error' ? 'bg-cs-red' :
                      'bg-cs-grey'
                    }`} />
                    <span className="flex-1 font-medium text-foreground text-xs">{dep.label}</span>
                    <span className={`text-[10px] truncate max-w-[180px] ${
                      dep.status === 'ok' ? 'text-muted-foreground' :
                      dep.status === 'missing' || dep.status === 'error' ? 'text-destructive' :
                      'text-muted-foreground'
                    }`}>
                      {dep.detail || 'not checked'}
                    </span>
                    {dep.has_e2e && (
                      <button
                        onClick={() => handleTestDep(dep.id)}
                        disabled={testingDep === dep.id}
                        className="shrink-0 btn-ghost p-1 rounded text-xs text-muted-foreground hover:text-foreground disabled:opacity-50 opacity-0 group-hover:opacity-100 transition-opacity"
                        title={`Run end-to-end test for ${dep.label}`}
                      >
                        {testingDep === dep.id ? (
                          <Loader size={12} className="animate-spin" />
                        ) : (
                          <Play size={12} />
                        )}
                      </button>
                    )}
                    {dep.install_guide && dep.status !== 'ok' && (
                      <button
                        onClick={() => setInstallDep({ id: dep.id, label: dep.label, guide: dep.install_guide })}
                        className="shrink-0 btn-ghost p-1 rounded text-xs text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity"
                        title={`Install instructions for ${dep.label}`}
                      >
                        <DownloadCloud size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ));
          })()}
          {deps.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">Loading dependencies…</p>
          )}
        </div>
      </section>

      {/* ── Updates card ─────────────────────────────────────────── */}
      <section className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium flex items-center gap-2"><ArrowUpCircle size={16} /> Updates</h2>
          <div className="flex items-center gap-1">
            {info?.can_restart && !staged && (
              <button className="btn-ghost text-xs" onClick={() => setConfirmRestart(true)} disabled={restarting || !!active} title="Restart the application">
                <Power size={14} className={restarting ? 'animate-pulse' : ''} /> {restarting ? 'Restarting…' : 'Restart'}
              </button>
            )}
            <button className="btn-ghost text-xs" onClick={() => runCheck(true)} disabled={checking || !!active}>
              <RefreshCw size={14} className={checking ? 'animate-spin' : ''} /> Check now
            </button>
          </div>
        </div>

        {/* Staged bundle update — awaiting a restart to apply (bare-metal). */}
        {staged && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 p-4 mb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm">
                <ArrowUpCircle size={16} className="text-primary" /> Version {status?.target_version} is staged
              </div>
              <button className="btn-ghost text-xs" onClick={dismiss} disabled={restarting}><X size={14} /> Discard</button>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              The new version is validated and ready. Restart to apply it — the app is briefly unavailable while it comes back up.
            </p>
            {status?.backup?.tag && (
              <p className="text-xs text-muted-foreground mt-2">Data backed up as <span className="font-mono">{status.backup.tag}</span>{typeof status.backup.projects?.length === 'number' ? ` (${status.backup.projects.length} project${status.backup.projects.length === 1 ? '' : 's'})` : ''}.</p>
            )}
            <button className="btn-primary mt-3" onClick={restart} disabled={restarting}>
              {restarting ? <Loader size={15} className="animate-spin" /> : <Power size={15} />}
              {restarting ? 'Restarting…' : 'Restart & apply'}
            </button>
          </div>
        )}

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
      {(info?.file_update_supported || info?.bundle_update_supported) && !active && !staged && !completed && (
        <section className="card p-5">
          <h2 className="font-medium mb-1 flex items-center gap-2"><Upload size={16} /> Update from a file</h2>
          <p className="text-sm text-muted-foreground mb-3">
            {bundleMode ? (
              <>For offline / air-gapped servers. Upload a reqmesh release bundle
              (<span className="font-mono text-xs">reqmesh-v&lt;version&gt;.tar.gz</span>); it's validated and
              staged, then applied on the next restart — no contact with GitHub.</>
            ) : (
              <>For air-gapped servers. Upload a reqmesh image archive
              (<span className="font-mono text-xs">reqmesh-v&lt;version&gt;-image.tar.gz</span> from a release);
              it's loaded and applied without contacting GitHub.</>
            )}
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
              {uploading ? (bundleMode ? 'Staging…' : 'Uploading…') : (bundleMode ? 'Upload & stage' : 'Upload & update')}
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {bundleMode
              ? "Project data is backed up before staging; nothing changes until you restart."
              : "Project data is backed up first, exactly as with an online update."}
          </p>
        </section>
      )}

      {/* ── Confirm dialog ───────────────────────────────────────── */}
      {confirming && (
        <BodyPortal>
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
        </BodyPortal>
      )}

      {/* ── Confirm restart ──────────────────────────────────────── */}
      {confirmRestart && (
        <BodyPortal>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setConfirmRestart(false)}>
          <div className="card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold flex items-center gap-2"><Power size={18} /> Restart the application?</h3>
            <p className="text-sm text-muted-foreground mt-3">
              The app will be unavailable for a few seconds while it restarts, disconnecting anyone currently using it.
              {staged ? ' The staged update will be applied on the way back up.' : ''}
            </p>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setConfirmRestart(false)}>Cancel</button>
              <button className="btn-primary" onClick={restart} disabled={restarting}>
                {restarting ? <Loader size={15} className="animate-spin" /> : <Power size={15} />} Restart now
              </button>
            </div>
          </div>
        </div>
        </BodyPortal>
      )}

      {/* ── Install dependency modal ──────────────────────────────── */}
      {installDep && (
        <BodyPortal>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-[2px] p-4" onClick={() => setInstallDep(null)}>
          <div className="card p-5 max-w-lg w-full shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <DownloadCloud size={16} className="text-primary" />
                  Install {installDep.label}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">Run these commands on the server to install this dependency.</p>
              </div>
              <button onClick={() => setInstallDep(null)} className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent">
                <X size={15} />
              </button>
            </div>
            <div className="bg-muted rounded-lg p-3 relative">
              <pre className="text-xs font-mono text-foreground whitespace-pre-wrap">{installDep.guide}</pre>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(installDep.guide).then(() => {
                    setCopiedId(installDep.id);
                    setTimeout(() => setCopiedId(null), 2000);
                  }).catch(() => {});
                }}
                className="absolute top-2 right-2 p-1.5 rounded bg-card border text-muted-foreground hover:text-foreground transition-colors"
                title="Copy to clipboard"
              >
                {copiedId === installDep.id ? <CheckCircle2 size={14} className="text-cs-green" /> : <Copy size={14} />}
              </button>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={() => setInstallDep(null)} className="btn-secondary text-xs">Close</button>
            </div>
          </div>
        </div>
        </BodyPortal>
      )}
    </div>
  );
}

function formatUptime(seconds: number): string {
  if (seconds <= 0) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  return parts.length > 0 ? parts.join(' ') : '< 1m';
}

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
