import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Save, CheckCircle2, Settings, Trash2, Pencil, X, Check, Plus, RotateCw, GitBranch, Clock, User } from 'lucide-react';
import { api, type StakeholderDef, type RiskMatrix } from '../api/client';
import { useAuthStore } from '../store/auth';

interface NamingRule {
  prefix_length: number;
  prefix_type: 'alpha' | 'alphanumeric';
  prefix_hint: string;
  separator: string;
  suffix_length: number;
  suffix_type: 'numeric' | 'alphanumeric';
  example: string;
}

const DEFAULT_NAMING: Record<string, NamingRule> = {
  requirements: { prefix_length: 4, prefix_type: 'alpha', prefix_hint: 'REQ', separator: '', suffix_length: 4, suffix_type: 'numeric', example: 'REQ0001' },
  components:    { prefix_length: 4, prefix_type: 'alpha', prefix_hint: 'COMP', separator: '', suffix_length: 4, suffix_type: 'numeric', example: 'COMP0001' },
  verification:  { prefix_length: 2, prefix_type: 'alpha', prefix_hint: 'VC', separator: '', suffix_length: 4, suffix_type: 'numeric', example: 'VC0001' },
  risks:         { prefix_length: 3, prefix_type: 'alpha', prefix_hint: 'RSK', separator: '', suffix_length: 5, suffix_type: 'numeric', example: 'RSK00001' },
  change_requests: { prefix_length: 2, prefix_type: 'alpha', prefix_hint: 'CR', separator: '', suffix_length: 6, suffix_type: 'numeric', example: 'CR000001' },
  specifications: { prefix_length: 5, prefix_type: 'alpha', prefix_hint: 'SPEC', separator: '-', suffix_length: 4, suffix_type: 'alphanumeric', example: 'SPEC-SYS' },
};

const ENTITY_LABELS: Record<string, string> = {
  requirements: 'Requirements',
  components: 'Components',
  verification: 'Verification Cases',
  risks: 'Risks',
  change_requests: 'Change Requests',
  specifications: 'Specifications',
};

/** A baseline definition as stored in project meta. The Baselines page edits
 *  `symbol` and `description`; this page edits only the set of names, but must
 *  round-trip the other fields untouched. */
interface BaselineDef {
  name: string;
  symbol: string;
  description: string;
}

export default function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const editable = useAuthStore((s) => s.canEdit());

  const [projectName, setProjectName] = useState('');
  const [naming, setNaming] = useState<Record<string, NamingRule>>({});
  const [originalName, setOriginalName] = useState('');
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  // Git settings
  const [gitUserName, setGitUserName] = useState('');
  const [gitUserEmail, setGitUserEmail] = useState('');
  const [gitRemoteUrl, setGitRemoteUrl] = useState('');
  const [gitAutocommit, setGitAutocommit] = useState(true);
  const [gitPushOnCommit, setGitPushOnCommit] = useState(false);
  const [gitPushInterval, setGitPushInterval] = useState(0);
  const [gitCommitSchedule, setGitCommitSchedule] = useState('every_change');
  const [gitCommitIntervalHours, setGitCommitIntervalHours] = useState(0);
  const [gitCommitChangesThreshold, setGitCommitChangesThreshold] = useState(0);

  // Baselines
  const [baselines, setBaselines] = useState<{ name: string; count: number }[]>([]);
  // Full definition objects, not just names. This page only edits the name
  // list, but it saves the whole array back — so holding bare strings here
  // silently wiped the symbol and description that the Baselines page sets,
  // on every unrelated settings save.
  const [baselineDefs, setBaselineDefs] = useState<BaselineDef[]>([]);
  const [newBaselineDef, setNewBaselineDef] = useState('');
  const [editingBaseline, setEditingBaseline] = useState<string | null>(null);
  const [editBaselineName, setEditBaselineName] = useState('');

  const addBaselineDef = () => {
    const name = newBaselineDef.trim();
    setNewBaselineDef('');
    if (!name || baselineDefs.some((d) => d.name === name)) return;
    setBaselineDefs((prev) => [...prev, { name, symbol: '', description: '' }]);
  };

  // Stakeholders whose views a requirement is scored against. Defined per
  // project so the scores are comparable between requirements — they used to
  // be free text typed into each requirement, so "safety" and "Safety" were
  // different stakeholders and nothing could be ranked.
  const [stakeholders, setStakeholders] = useState<StakeholderDef[]>([]);

  // The risk matrix turns a risk's two inputs (severity, likelihood) into its
  // rating. Held here as the whole object because the axes and the cell grid
  // have to stay the same shape — renaming a level and re-banding a cell are
  // one edit as far as the server is concerned.
  const [riskMatrix, setRiskMatrix] = useState<RiskMatrix | null>(null);
  const setCell = (si: number, li: number, band: string) => setRiskMatrix((m) => {
    if (!m) return m;
    const cells = m.cells.map((row) => [...row]);
    cells[si][li] = band;
    return { ...m, cells };
  });
  // Renaming an axis level must move the cells with it, so the grid is rebuilt
  // from the current one rather than left indexed against the old names.
  const renameLevel = (axis: 'severities' | 'likelihoods', i: number, name: string) =>
    setRiskMatrix((m) => (m ? { ...m, [axis]: m[axis].map((x, j) => (j === i ? name : x)) } : m));
  const addLevel = (axis: 'severities' | 'likelihoods') => setRiskMatrix((m) => {
    if (!m) return m;
    const name = `level_${m[axis].length + 1}`;
    const fallback = m.bands[0].key;
    if (axis === 'severities') {
      return { ...m, severities: [...m.severities, name],
               cells: [...m.cells, m.likelihoods.map(() => fallback)] };
    }
    return { ...m, likelihoods: [...m.likelihoods, name],
             cells: m.cells.map((row) => [...row, fallback]) };
  });
  const removeLevel = (axis: 'severities' | 'likelihoods', i: number) => setRiskMatrix((m) => {
    if (!m || m[axis].length <= 1) return m;   // an axis with no levels rates nothing
    if (axis === 'severities') {
      return { ...m, severities: m.severities.filter((_, j) => j !== i),
               cells: m.cells.filter((_, j) => j !== i) };
    }
    return { ...m, likelihoods: m.likelihoods.filter((_, j) => j !== i),
             cells: m.cells.map((row) => row.filter((_, j) => j !== i)) };
  });
  const [newStakeholder, setNewStakeholder] = useState('');
  const addStakeholder = () => {
    const name = newStakeholder.trim();
    setNewStakeholder('');
    if (!name || stakeholders.some((s) => s.name === name)) return;
    setStakeholders((prev) => [...prev, { name, weight: 1 }]);
  };

  // Git history
  const [gitCommits, setGitCommits] = useState<Array<{ hash: string; author: string; date: string; message: string }>>([]);
  const [gitRepo, setGitRepo] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [testingRemote, setTestingRemote] = useState(false);
  const [remoteTestResult, setRemoteTestResult] = useState<{ ok: boolean; error?: string; branches?: string[]; branch_count?: number } | null>(null);

  const loadGitHistory = () => {
    if (!projectId) return;
    setLoadingHistory(true);
    api.gitLog(projectId, 50).then((res) => {
      setGitRepo(res.is_repo);
      setGitCommits(res.commits || []);
    }).catch(() => {}).finally(() => setLoadingHistory(false));
  };

  const handleRestore = async (hash: string) => {
    if (!projectId || !editable) return;
    if (!confirm(`Restore project to commit ${hash.slice(0, 8)}? This will restore all files to that state and create a new commit recording the restoration.`)) return;
    setRestoring(hash);
    try {
      await api.gitRestore(projectId, hash);
      loadGitHistory();
    } catch (err: any) {
      alert(err.message || 'Restore failed');
    } finally {
      setRestoring(null);
    }
  };

  const handleTestRemote = async () => {
    if (!projectId || !gitRemoteUrl.trim()) return;
    setTestingRemote(true);
    setRemoteTestResult(null);
    try {
      const res = await api.gitTestRemote(projectId, gitRemoteUrl.trim());
      setRemoteTestResult(res);
    } catch (err: any) {
      setRemoteTestResult({ ok: false, error: err.message || 'Request failed' });
    } finally {
      setTestingRemote(false);
    }
  };

  const relativeTime = (iso: string) => {
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
  };

  const loadBaselines = () => {
    if (!projectId) return;
    api.listBaselines(projectId).then((b: any[]) => setBaselines(b.map(x => ({ name: x.name, count: x.count })))).catch(() => {});
  };

  useEffect(() => {
    if (!projectId) return;
    api.getProject(projectId).then((p: any) => {
      setProjectName(p.name || '');
      setOriginalName(p.name || '');
      const incoming = p.naming || {};
      const merged: Record<string, NamingRule> = {};
      for (const [key, def] of Object.entries(DEFAULT_NAMING)) {
        merged[key] = { ...def, ...(incoming[key] || {}) };
      }
      setNaming(merged);
      const git = p.git || {};
      setGitUserName(git.user_name || '');
      setGitUserEmail(git.user_email || '');
      setGitRemoteUrl(git.remote_url || '');
      setGitAutocommit(git.auto_commit !== false);
      setGitPushOnCommit(git.push_on_commit || false);
      setGitPushInterval(git.push_interval_minutes || 0);
      setGitCommitSchedule(git.commit_schedule || 'every_change');
      setGitCommitIntervalHours(git.commit_interval_hours || 0);
      setGitCommitChangesThreshold(git.commit_changes_threshold || 0);
      setStakeholders(p.stakeholders || []);
      setRiskMatrix(p.risk_matrix || null);
      setBaselineDefs((p.baselines || []).map((b: any) => (
        typeof b === 'string'
          ? { name: b, symbol: '', description: '' }
          : { name: b.name, symbol: b.symbol || '', description: b.description || '' }
      )));
    }).catch((err: any) => setError(err.message));
    loadBaselines();
    loadGitHistory();
  }, [projectId]);

  const example = (rule: NamingRule) => {
    const pfx = rule.prefix_hint.padEnd(rule.prefix_length, 'X').slice(0, rule.prefix_length);
    const sfx = rule.suffix_type === 'numeric' ? '0'.repeat(rule.suffix_length) : 'a'.repeat(rule.suffix_length);
    return pfx + rule.separator + sfx;
  };

  const updateRule = (key: string, patch: Partial<NamingRule>) => {
    setNaming((prev) => {
      const rule = { ...prev[key], ...patch };
      return { ...prev, [key]: rule };
    });
  };

  const save = async () => {
    if (!projectId) return;
    setError('');
    setSaving(true);
    try {
      await api.updateProject(projectId, {
        name: projectName, naming,
        baselines: baselineDefs,
        stakeholders,
        ...(riskMatrix ? { risk_matrix: riskMatrix } : {}),
        git: {
          user_name: gitUserName, user_email: gitUserEmail,
          remote_url: gitRemoteUrl, auto_commit: gitAutocommit,
          push_on_commit: gitPushOnCommit, push_interval_minutes: gitPushInterval,
          commit_schedule: gitCommitSchedule,
          commit_interval_hours: Number(gitCommitIntervalHours) || 0,
          commit_changes_threshold: Number(gitCommitChangesThreshold) || 0,
        },
      });
      setOriginalName(projectName);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
    } catch (err: any) {
      setError(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const dirty = projectName !== originalName;

  return (
    <div className="max-w-3xl mx-auto p-8">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/project/${projectId}`)} className="btn-secondary p-2">
          <ArrowLeft size={16} />
        </button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Settings size={20} /> Project Settings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Configuration for {projectId}</p>
        </div>
      </div>

      {success && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm flex items-center gap-2">
          <CheckCircle2 size={14} /> Saved
        </div>
      )}
      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
      )}

      {/* Project name */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-3">Project Name</h2>
        <input
          className="input text-lg font-medium"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          disabled={!editable}
          placeholder="My Project"
        />
      </motion.div>

      {/* Naming standards */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Naming Standards</h2>
        <p className="text-xs text-muted-foreground mb-4">Define ID patterns for auto-generated entity IDs. Used by the "Next UID" feature and the create-requirement modal.</p>

        <div className="space-y-4">
          {Object.entries(naming).map(([key, rule]) => (
            <div key={key} className="border rounded-lg p-4">
              <h3 className="text-sm font-medium text-card-foreground mb-3">{ENTITY_LABELS[key] || key}</h3>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs text-muted-foreground">Format:</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded font-mono">{example(rule)}</code>
                <span className="text-[10px] text-muted-foreground/50">(preview)</span>
              </div>
              <div className="grid grid-cols-2 @xl:grid-cols-3 gap-2">
                <div>
                  <label className="label text-[10px]">Prefix hint</label>
                  <input className="input text-xs font-mono" value={rule.prefix_hint}
                    onChange={(e) => updateRule(key, { prefix_hint: e.target.value })}
                    disabled={!editable} />
                </div>
                <div>
                  <label className="label text-[10px]">Prefix length</label>
                  <input className="input text-xs" type="number" min={1} max={8} value={rule.prefix_length}
                    onChange={(e) => updateRule(key, { prefix_length: Number(e.target.value) || 1 })}
                    disabled={!editable} />
                </div>
                <div>
                  <label className="label text-[10px]">Separator</label>
                  <input className="input text-xs font-mono" maxLength={1} value={rule.separator}
                    onChange={(e) => updateRule(key, { separator: e.target.value.slice(0, 1) })}
                    disabled={!editable} />
                </div>
                <div>
                  <label className="label text-[10px]">Suffix length</label>
                  <input className="input text-xs" type="number" min={1} max={10} value={rule.suffix_length}
                    onChange={(e) => updateRule(key, { suffix_length: Number(e.target.value) || 1 })}
                    disabled={!editable} />
                </div>
                <div>
                  <label className="label text-[10px]">Suffix type</label>
                  <select className="input text-xs" value={rule.suffix_type}
                    onChange={(e) => updateRule(key, { suffix_type: e.target.value as any })}
                    disabled={!editable}>
                    <option value="numeric">Numeric (0-9)</option>
                    <option value="alphanumeric">Alphanumeric (a-z, 0-9)</option>
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Stakeholders */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Stakeholders</h2>
        <p className="text-xs text-muted-foreground mb-3">
          Whose views requirements are scored against, and how much each one counts.
          Weights are relative — a stakeholder on 2 counts twice as much as one on 1.
          Each requirement scores 0–10 per stakeholder; its value is the weighted mean of those scored.
        </p>
        <div className="space-y-1.5 mb-2">
          {stakeholders.map((sh) => (
            <div key={sh.name} className="flex items-center gap-2">
              <span className="text-sm text-foreground flex-1 min-w-0 truncate">{sh.name}</span>
              <label className="text-[10px] text-muted-foreground">weight</label>
              <input
                type="number" min={0} step={0.1}
                className="input w-20 h-8 text-xs"
                value={sh.weight}
                disabled={!editable}
                onChange={(e) => setStakeholders((prev) => prev.map((x) =>
                  x.name === sh.name ? { ...x, weight: Number(e.target.value) } : x))}
              />
              {editable && (
                <button
                  onClick={() => setStakeholders((prev) => prev.filter((x) => x.name !== sh.name))}
                  className="text-muted-foreground hover:text-destructive"
                  title="Remove — existing scores for this stakeholder are kept but stop counting"
                ><X size={13} /></button>
              )}
            </div>
          ))}
          {stakeholders.length === 0 && (
            <span className="text-xs text-muted-foreground italic">
              No stakeholders defined. Requirements cannot be scored until at least one exists.
            </span>
          )}
        </div>
        {editable && (
          <div className="flex gap-2">
            <input className="input text-sm flex-1" placeholder="Safety" value={newStakeholder}
              onChange={(e) => setNewStakeholder(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addStakeholder(); } }} />
            <button className="btn-secondary text-xs" onClick={addStakeholder}>
              <Plus size={14} /> Add
            </button>
          </div>
        )}
      </motion.div>

      {/* Risk matrix */}
      {riskMatrix && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5 mb-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-1">Risk Matrix</h2>
          <p className="text-xs text-muted-foreground mb-3">
            Every risk states a severity and a likelihood; this grid turns that pair into its rating.
            Ratings are derived on read, so re-banding a cell re-rates every existing risk at once.
            {editable && ' Click a cell to cycle its band.'}
          </p>

          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-1">
              <thead>
                <tr>
                  <th className="text-[10px] text-muted-foreground font-normal text-right pr-2 align-bottom">
                    severity &darr; / likelihood &rarr;
                  </th>
                  {riskMatrix.likelihoods.map((l, li) => (
                    <th key={li} className="align-bottom">
                      <div className="flex flex-col items-center gap-1">
                        {editable && riskMatrix.likelihoods.length > 1 && (
                          <button onClick={() => removeLevel('likelihoods', li)}
                            className="text-muted-foreground hover:text-destructive" title="Remove this likelihood">
                            <X size={10} />
                          </button>
                        )}
                        <input
                          className="input h-7 py-0 text-[10px] w-24 text-center"
                          value={l} disabled={!editable}
                          onChange={(e) => renameLevel('likelihoods', li, e.target.value)}
                        />
                      </div>
                    </th>
                  ))}
                  {editable && (
                    <th className="align-bottom">
                      <button onClick={() => addLevel('likelihoods')} className="btn-secondary text-[10px] px-1.5 py-1" title="Add a likelihood level">
                        <Plus size={11} />
                      </button>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {/* Rendered most-severe first so the grid reads like a
                    conventional matrix, while the stored order stays
                    least-severe first to match the server's indexing. */}
                {[...riskMatrix.severities].map((_, i) => riskMatrix.severities.length - 1 - i).map((si) => (
                  <tr key={si}>
                    <td className="whitespace-nowrap">
                      <div className="flex items-center gap-1 justify-end">
                        <input
                          className="input h-7 py-0 text-[10px] w-24 text-right"
                          value={riskMatrix.severities[si]} disabled={!editable}
                          onChange={(e) => renameLevel('severities', si, e.target.value)}
                        />
                        {editable && riskMatrix.severities.length > 1 && (
                          <button onClick={() => removeLevel('severities', si)}
                            className="text-muted-foreground hover:text-destructive" title="Remove this severity">
                            <X size={10} />
                          </button>
                        )}
                      </div>
                    </td>
                    {riskMatrix.likelihoods.map((_, li) => {
                      const key = riskMatrix.cells[si]?.[li] ?? riskMatrix.bands[0].key;
                      const band = riskMatrix.bands.find((b) => b.key === key) ?? riskMatrix.bands[0];
                      const next = riskMatrix.bands[
                        (riskMatrix.bands.findIndex((b) => b.key === key) + 1) % riskMatrix.bands.length
                      ];
                      return (
                        <td key={li}>
                          <button
                            disabled={!editable}
                            onClick={() => setCell(si, li, next.key)}
                            title={editable ? `${band.label} — click for ${next.label}` : band.label}
                            className="w-24 h-9 rounded text-[10px] font-medium text-black/80 disabled:cursor-default"
                            style={{ backgroundColor: band.color }}
                          >
                            {band.label}
                          </button>
                        </td>
                      );
                    })}
                    {editable && <td />}
                  </tr>
                ))}
                {editable && (
                  <tr>
                    <td className="text-right">
                      <button onClick={() => addLevel('severities')} className="btn-secondary text-[10px] px-1.5 py-1" title="Add a severity level">
                        <Plus size={11} />
                      </button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-3 pt-3 border-t">
            {riskMatrix.bands.map((b, bi) => (
              <div key={b.key} className="flex items-center gap-1.5">
                <input
                  type="color" value={b.color} disabled={!editable}
                  className="w-6 h-6 rounded border-0 bg-transparent p-0 cursor-pointer disabled:cursor-default"
                  onChange={(e) => setRiskMatrix((m) => (m ? {
                    ...m, bands: m.bands.map((x, j) => (j === bi ? { ...x, color: e.target.value } : x)),
                  } : m))}
                />
                <input
                  className="input h-7 py-0 text-[10px] w-24" value={b.label} disabled={!editable}
                  onChange={(e) => setRiskMatrix((m) => (m ? {
                    ...m, bands: m.bands.map((x, j) => (j === bi ? { ...x, label: e.target.value } : x)),
                  } : m))}
                />
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Baseline definitions */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Baseline Definitions</h2>
        <p className="text-xs text-muted-foreground mb-3">Define the available baseline names for this project (e.g. PDR, CDR, TRR). These appear as selectable options on requirement forms.</p>
        <div className="flex flex-wrap gap-1 mb-2">
          {baselineDefs.map((def) => (
            <span key={def.name} className="inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-0.5 text-xs">
              {def.symbol ? `${def.symbol} · ${def.name}` : def.name}
              {editable && (
                <button onClick={() => setBaselineDefs((prev) => prev.filter((d) => d.name !== def.name))} className="text-muted-foreground hover:text-destructive"><X size={11} /></button>
              )}
            </span>
          ))}
          {baselineDefs.length === 0 && (
            <span className="text-xs text-muted-foreground italic">No baselines defined. Add names like PDR, CDR below.</span>
          )}
        </div>
        {editable && (
          <div className="flex gap-2">
            <input className="input text-sm flex-1" placeholder="PDR" value={newBaselineDef}
              onChange={(e) => setNewBaselineDef(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addBaselineDef(); } }} />
            <button className="btn-secondary text-xs" onClick={addBaselineDef}>
              <Plus size={14} /> Add
            </button>
          </div>
        )}
      </motion.div>

      {/* Baselines */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Baselines</h2>
        <p className="text-xs text-muted-foreground mb-4">Manage configuration baselines. Renaming updates all linked requirements. Deleting clears the baseline from all requirements.</p>
        {baselines.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">No baselines defined. Freeze a baseline from the Baselines page or use <code className="bg-muted px-1 rounded">POST /api/projects/{'{id}'}/baselines/NAME/freeze</code>.</p>
        ) : (
          <div className="space-y-1">
            {baselines.map((b) => (
              <div key={b.name} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent">
                {editingBaseline === b.name ? (
                  <>
                    <input className="input text-xs flex-1 font-mono" value={editBaselineName} onChange={(e) => setEditBaselineName(e.target.value)} autoFocus
                      onKeyDown={async (e) => {
                        if (e.key === 'Enter') {
                          if (!editBaselineName.trim()) return;
                          await api.renameBaseline(projectId!, b.name, editBaselineName.trim());
                          setEditingBaseline(null);
                          loadBaselines();
                        }
                        if (e.key === 'Escape') setEditingBaseline(null);
                      }} />
                    <button onClick={async () => {
                      if (!editBaselineName.trim()) return;
                      await api.renameBaseline(projectId!, b.name, editBaselineName.trim());
                      setEditingBaseline(null);
                      loadBaselines();
                    }} className="p-1 rounded text-emerald-400 hover:bg-emerald-500/10" title="Save">
                      <Check size={12} />
                    </button>
                    <button onClick={() => setEditingBaseline(null)} className="p-1 rounded text-muted-foreground hover:text-foreground" title="Cancel">
                      <X size={12} />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="font-mono text-card-foreground flex-1">{b.name}</span>
                    <span className="text-muted-foreground">{b.count} req{b.count !== 1 ? 's' : ''}</span>
                    {editable && (
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 hover:opacity-100 transition-opacity">
                        <button onClick={() => { setEditingBaseline(b.name); setEditBaselineName(b.name); }} className="p-1 rounded text-muted-foreground hover:text-foreground" title="Rename">
                          <Pencil size={12} />
                        </button>
                        <button onClick={async () => {
                          if (!confirm(`Delete baseline "${b.name}"? This will clear it from ${b.count} requirement(s).`)) return;
                          await api.deleteBaseline(projectId!, b.name);
                          loadBaselines();
                        }} className="p-1 rounded text-muted-foreground hover:text-destructive" title="Delete">
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Git Integration */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Git Integration</h2>
        <p className="text-xs text-muted-foreground mb-4">Configure how this project syncs with a git remote. These settings are stored in <code className="bg-muted px-1 rounded">_meta.yaml</code> and apply to this project only.</p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Author Name</label>
              <input className="input text-sm font-mono" value={gitUserName}
                onChange={(e) => setGitUserName(e.target.value)} disabled={!editable}
                placeholder="Acme Systems Engineering" />
              <div className="text-[10px] text-muted-foreground mt-0.5">Git commit author name</div>
            </div>
            <div>
              <label className="label">Author Email</label>
              <input className="input text-sm font-mono" value={gitUserEmail}
                onChange={(e) => setGitUserEmail(e.target.value)} disabled={!editable}
                placeholder="systems@acme-aero.com" />
              <div className="text-[10px] text-muted-foreground mt-0.5">Git commit author email</div>
            </div>
          </div>

          <div>
            <label className="label">Remote URL</label>
            <input className="input text-sm font-mono" value={gitRemoteUrl}
              onChange={(e) => setGitRemoteUrl(e.target.value)} disabled={!editable}
              placeholder="git@github.com:org/project-data.git" />
            <div className="text-[10px] text-muted-foreground mt-0.5">Git remote to push commits to (SSH or HTTPS). Leave blank for no remote.</div>
          </div>

          {gitRemoteUrl.trim() && (
            <div>
              <button
                onClick={handleTestRemote}
                disabled={testingRemote || !editable}
                className="btn-secondary text-xs"
              >
                {testingRemote ? (
                  <><RotateCw size={12} className="animate-spin mr-1" /> Testing…</>
                ) : (
                  'Test Connection'
                )}
              </button>
              {remoteTestResult && (
                <div className={`mt-2 px-3 py-2 rounded text-xs ${remoteTestResult.ok ? 'border border-green-500/20 bg-green-500/5 text-green-400' : 'border border-red-500/20 bg-red-500/5 text-red-400'}`}>
                  {remoteTestResult.ok ? (
                    <>Remote is reachable. Found {remoteTestResult.branch_count ?? 0} branch{remoteTestResult.branch_count !== 1 ? 'es' : ''}{remoteTestResult.branches && remoteTestResult.branches.length > 0 ? `: ${remoteTestResult.branches!.join(', ')}` : '.'}</>
                  ) : (
                    <>{remoteTestResult.error}</>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Commit Schedule */}
          <div className="border-t border-border/60 pt-4 mt-4">
            <label className="label mb-2">Commit Schedule</label>
            <p className="text-[10px] text-muted-foreground mb-3">
              Choose when git commits are created. Auto-commit must be enabled above.
            </p>
            <select className="select mb-3" value={gitCommitSchedule}
              onChange={(e) => setGitCommitSchedule(e.target.value)} disabled={!editable || !gitAutocommit}>
              <option value="every_change">Every change (debounced)</option>
              <option value="interval">Time-based — every N hours</option>
              <option value="changes">Change-count — every N changes</option>
              <option value="both">Both time and change-count (whichever comes first)</option>
            </select>

            {(gitCommitSchedule === 'interval' || gitCommitSchedule === 'both') && (
              <div className="mb-3">
                <label className="label">Commit interval (hours)</label>
                <input className="input text-sm w-32" type="number" min={0.5} step={0.5} max={720}
                  value={gitCommitIntervalHours || ''}
                  onChange={(e) => setGitCommitIntervalHours(Number(e.target.value) || 0)}
                  disabled={!editable || !gitAutocommit}
                  placeholder="24" />
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {gitCommitIntervalHours >= 24
                    ? `≈ every ${(gitCommitIntervalHours / 24).toFixed(1)} days`
                    : gitCommitIntervalHours >= 1
                      ? `≈ every ${gitCommitIntervalHours} hour${gitCommitIntervalHours !== 1 ? 's' : ''}`
                      : gitCommitIntervalHours > 0
                        ? `≈ every ${Math.round(gitCommitIntervalHours * 60)} minutes`
                        : 'Enter a value to enable time-based commits'}
                </div>
              </div>
            )}

            {(gitCommitSchedule === 'changes' || gitCommitSchedule === 'both') && (
              <div className="mb-3">
                <label className="label">Commit after every N changes</label>
                <input className="input text-sm w-32" type="number" min={1} max={10000}
                  value={gitCommitChangesThreshold || ''}
                  onChange={(e) => setGitCommitChangesThreshold(Number(e.target.value) || 0)}
                  disabled={!editable || !gitAutocommit}
                  placeholder="50" />
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {gitCommitChangesThreshold > 0
                    ? `A commit will be created after ${gitCommitChangesThreshold} changes.`
                    : 'Enter a value to enable change-count commits'}
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={gitAutocommit} onChange={(e) => setGitAutocommit(e.target.checked)} disabled={!editable}
                className="w-4 h-4 rounded border-muted-foreground/30" />
              <span className="label">Enable auto-commit</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={gitPushOnCommit} onChange={(e) => setGitPushOnCommit(e.target.checked)} disabled={!editable}
                className="w-4 h-4 rounded border-muted-foreground/30" />
              <span className="label">Push on every commit</span>
            </label>
          </div>

          <div>
            <label className="label">Push Interval (minutes)</label>
            <input className="input text-sm w-32" type="number" min={0} max={1440} value={gitPushInterval}
              onChange={(e) => setGitPushInterval(Number(e.target.value) || 0)} disabled={!editable || gitPushOnCommit} />
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {gitPushOnCommit ? 'Push on commit is enabled — interval is ignored.' : gitPushInterval > 0 ? `Push every ${gitPushInterval} minutes. 0 = manual only.` : 'Pushes are manual only. Use the CLI `push_to_remote` or set an interval.'}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Git History */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="card p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-semibold text-sm text-card-foreground flex items-center gap-2">
              <GitBranch size={14} className="text-muted-foreground" />
              Git History
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">Recent commits for this project. Restore to any past state.</p>
          </div>
          <button onClick={loadGitHistory} className="btn-secondary text-xs" disabled={loadingHistory}>
            <RotateCw size={12} className={loadingHistory ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {!gitRepo ? (
          <div className="text-center py-8">
            <GitBranch size={32} className="mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">Not a git repository</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Initialize with <code className="bg-muted px-1 rounded">git init</code> in the project directory to enable version history.</p>
          </div>
        ) : gitCommits.length === 0 ? (
          <div className="text-center py-8">
            <Clock size={32} className="mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">No commits yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Make changes to the project data — commits are created automatically.</p>
          </div>
        ) : (
          <div className="divide-y divide-border/60 max-h-[600px] overflow-y-auto">
            {gitCommits.map((commit) => (
              <div key={commit.hash} className="flex items-start gap-3 py-2.5 px-2 rounded hover:bg-accent/40 group transition-colors">
                <div className="shrink-0 mt-0.5">
                  <div className="w-2 h-2 rounded-full bg-primary/40" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <code className="text-[11px] font-mono text-primary bg-primary/5 px-1.5 py-0.5 rounded">{commit.hash.slice(0, 8)}</code>
                    <span className="text-[11px] text-muted-foreground">{relativeTime(commit.date)}</span>
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
                {editable && (
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
      </motion.div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button onClick={save} className={`btn-primary ${dirty ? 'ring-2 ring-amber-500/50' : ''}`} disabled={!editable || saving}>
          <Save size={14} /> {saving ? 'Saving…' : dirty ? 'Save Changes *' : 'Save'}
        </button>
        {dirty && <span className="text-[10px] text-amber-400">Unsaved changes</span>}
      </div>
    </div>
  );
}
