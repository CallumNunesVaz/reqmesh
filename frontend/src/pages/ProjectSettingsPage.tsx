import { useEffect, useId, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Settings, X, Plus } from 'lucide-react';
import { api, type StakeholderDef, type RiskMatrix } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useToasts } from '../components/Toast';
import GitPanel from '../components/GitPanel';
import Reveal from '../components/Reveal';

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

export default function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const editable = useAuthStore((s) => s.canEdit());
  const { addToast } = useToasts();

  const [projectName, setProjectName] = useState('');
  const [naming, setNaming] = useState<Record<string, NamingRule>>({});
  const [enforceNaming, setEnforceNaming] = useState(true);
  const [originalName, setOriginalName] = useState('');
  const [saving, setSaving] = useState(false);

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
  const commitScheduleId = useId();

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

  useEffect(() => {
    if (!projectId) return;
    api.getProject(projectId).then((p: any) => {
      setProjectName(p.name || '');
      setOriginalName(p.name || '');
      const incoming = p.naming || {};
      const merged: Record<string, NamingRule> = {};
      for (const [key, def] of Object.entries(DEFAULT_NAMING)) {
        merged[key] = { ...def, ...incoming[key] };
      }
      setNaming(merged);
      setEnforceNaming((incoming as any).enforce !== false);
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
    }).catch((err: any) => addToast('error', `Could not load project settings: ${err.message}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    setSaving(true);
    try {
      await api.updateProject(projectId, {
        name: projectName, naming: { ...naming, enforce: enforceNaming },
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
      addToast('success', 'Settings saved');
    } catch (err: any) {
      addToast('error', err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const dirty = projectName !== originalName;

  return (
    <div className="max-w-6xl mx-auto p-8">
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

      {/* Project name */}
      <Reveal className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-3">Project Name</h2>
        <input
          className="input text-lg font-medium"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          disabled={!editable}
          placeholder="My Project"
        />
      </Reveal>

      {/* Naming standards */}
      <Reveal step={1} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Naming Standards</h2>
        <p className="text-xs text-muted-foreground mb-4">Define ID patterns for auto-generated entity IDs. Used by the "Next UID" feature and the create-requirement modal.</p>

        <label className="flex items-start gap-2 mb-1">
          <input
            type="checkbox"
            className="mt-0.5 w-4 h-4 rounded-md border-muted-foreground/30"
            checked={enforceNaming}
            onChange={(e) => setEnforceNaming(e.target.checked)}
            disabled={!editable}
          />
          <span className="text-sm font-medium text-card-foreground">Reject ids that do not fit these patterns</span>
        </label>
        <p className="text-xs text-muted-foreground mb-4 pl-6">
          New entities must match their kind's pattern. Turn this off for a project migrated from another tool, whose existing ids predate these standards — only creation is affected, existing records keep loading and saving.
        </p>

        <div className="space-y-4">
          {Object.entries(naming).map(([key, rule]) => (
            <div key={key} className="border rounded-lg p-4">
              <h3 className="text-sm font-medium text-card-foreground mb-3">{ENTITY_LABELS[key] || key}</h3>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs text-muted-foreground">Format:</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded-md font-mono">{example(rule)}</code>
                <span className="text-3xs text-muted-foreground/50">(preview)</span>
              </div>
              <div className="grid grid-cols-2 @xl:grid-cols-3 gap-2">
                <div>
                  <label className="label text-3xs">Prefix hint<input className="input text-xs font-mono" value={rule.prefix_hint}
                    onChange={(e) => updateRule(key, { prefix_hint: e.target.value })}
                    disabled={!editable} /></label>
                </div>
                <div>
                  <label className="label text-3xs">Prefix length<input className="input text-xs" type="number" min={1} max={8} value={rule.prefix_length}
                    onChange={(e) => updateRule(key, { prefix_length: Number(e.target.value) || 1 })}
                    disabled={!editable} /></label>
                </div>
                <div>
                  <label className="label text-3xs">Separator<input className="input text-xs font-mono" maxLength={1} value={rule.separator}
                    onChange={(e) => updateRule(key, { separator: e.target.value.slice(0, 1) })}
                    disabled={!editable} /></label>
                </div>
                <div>
                  <label className="label text-3xs">Suffix length<input className="input text-xs" type="number" min={1} max={10} value={rule.suffix_length}
                    onChange={(e) => updateRule(key, { suffix_length: Number(e.target.value) || 1 })}
                    disabled={!editable} /></label>
                </div>
                <div>
                  <label className="label text-3xs">Suffix type<select className="select text-xs" value={rule.suffix_type}
                    onChange={(e) => updateRule(key, { suffix_type: e.target.value as any })}
                    disabled={!editable}>
                    <option value="numeric">Numeric (0-9)</option>
                    <option value="alphanumeric">Alphanumeric (a-z, 0-9)</option>
                  </select></label>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Reveal>

      {/* Stakeholders */}
      <Reveal step={2} className="card p-5 mb-6">
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
              <label className="text-3xs text-muted-foreground">weight<input
                type="number" min={0} step={0.1}
                className="input w-20 h-8 text-xs"
                value={sh.weight}
                disabled={!editable}
                onChange={(e) => setStakeholders((prev) => prev.map((x) =>
                  x.name === sh.name ? { ...x, weight: Number(e.target.value) } : x))}
              /></label>
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
      </Reveal>

      {/* Risk matrix */}
      {riskMatrix && (
        <Reveal step={2} className="card p-5 mb-6">
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
                  <th className="text-3xs text-muted-foreground font-normal text-right pr-2 align-bottom">
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
                          className="input h-7 py-0 text-3xs w-24 text-center"
                          value={l} disabled={!editable}
                          onChange={(e) => renameLevel('likelihoods', li, e.target.value)}
                        />
                      </div>
                    </th>
                  ))}
                  {editable && (
                    <th className="align-bottom">
                      <button onClick={() => addLevel('likelihoods')} className="btn-secondary text-3xs px-1.5 py-1" title="Add a likelihood level">
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
                          className="input h-7 py-0 text-3xs w-24 text-right"
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
                            className="w-24 h-9 rounded-md text-3xs font-medium text-black/80 disabled:cursor-default"
                            style={{ backgroundColor: band.color }}
                          >
                            {band.label}
                          </button>
                        </td>
                      );
                    })}
                    {editable && <td aria-hidden="true" />}
                  </tr>
                ))}
                {editable && (
                  <tr>
                    <td className="text-right">
                      <button onClick={() => addLevel('severities')} className="btn-secondary text-3xs px-1.5 py-1" title="Add a severity level">
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
                  className="w-6 h-6 rounded-md border-0 bg-transparent p-0 cursor-pointer disabled:cursor-default"
                  onChange={(e) => setRiskMatrix((m) => (m ? {
                    ...m, bands: m.bands.map((x, j) => (j === bi ? { ...x, color: e.target.value } : x)),
                  } : m))}
                />
                <input
                  className="input h-7 py-0 text-3xs w-24" value={b.label} disabled={!editable}
                  onChange={(e) => setRiskMatrix((m) => (m ? {
                    ...m, bands: m.bands.map((x, j) => (j === bi ? { ...x, label: e.target.value } : x)),
                  } : m))}
                />
              </div>
            ))}
          </div>
        </Reveal>
      )}

      {/* Git Integration */}
      <Reveal step={3} className="card p-5 mb-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-1">Git Integration</h2>
        <p className="text-xs text-muted-foreground mb-4">Configure how this project syncs with a git remote. These settings are stored in <code className="bg-muted px-1 rounded-md">_meta.yaml</code> and apply to this project only.</p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Author Name<input className="input text-sm font-mono" value={gitUserName}
                onChange={(e) => setGitUserName(e.target.value)} disabled={!editable}
                placeholder="Acme Systems Engineering" /></label>
              <div className="text-3xs text-muted-foreground mt-0.5">Git commit author name</div>
            </div>
            <div>
              <label className="label">Author Email<input className="input text-sm font-mono" value={gitUserEmail}
                onChange={(e) => setGitUserEmail(e.target.value)} disabled={!editable}
                placeholder="systems@acme-aero.com" /></label>
              <div className="text-3xs text-muted-foreground mt-0.5">Git commit author email</div>
            </div>
          </div>

          <div>
            <label className="label">Remote URL<input className="input text-sm font-mono" value={gitRemoteUrl}
              onChange={(e) => setGitRemoteUrl(e.target.value)} disabled={!editable}
              placeholder="git@github.com:org/project-data.git" /></label>
            <div className="text-3xs text-muted-foreground mt-0.5">Git remote to push commits to (SSH or HTTPS). Leave blank for no remote.</div>
          </div>

          {/* Commit Schedule */}
          <div className="border-t border-border/60 pt-4 mt-4">
            <label className="label mb-2" htmlFor={commitScheduleId}>Commit Schedule</label>
            <p className="text-3xs text-muted-foreground mb-3">
              Choose when git commits are created. Auto-commit must be enabled above.
            </p>
            <select id={commitScheduleId} className="select mb-3" value={gitCommitSchedule}
              onChange={(e) => setGitCommitSchedule(e.target.value)} disabled={!editable || !gitAutocommit}>
              <option value="every_change">Every change (debounced)</option>
              <option value="interval">Time-based — every N hours</option>
              <option value="changes">Change-count — every N changes</option>
              <option value="both">Both time and change-count (whichever comes first)</option>
            </select>

            {(gitCommitSchedule === 'interval' || gitCommitSchedule === 'both') && (
              <div className="mb-3">
                <label className="label">Commit interval (hours)<input className="input text-sm w-32" type="number" min={0.5} step={0.5} max={720}
                  value={gitCommitIntervalHours || ''}
                  onChange={(e) => setGitCommitIntervalHours(Number(e.target.value) || 0)}
                  disabled={!editable || !gitAutocommit}
                  placeholder="24" /></label>
                <div className="text-3xs text-muted-foreground mt-0.5">
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
                <label className="label">Commit after every N changes<input className="input text-sm w-32" type="number" min={1} max={10000}
                  value={gitCommitChangesThreshold || ''}
                  onChange={(e) => setGitCommitChangesThreshold(Number(e.target.value) || 0)}
                  disabled={!editable || !gitAutocommit}
                  placeholder="50" /></label>
                <div className="text-3xs text-muted-foreground mt-0.5">
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
                className="w-4 h-4 rounded-md border-muted-foreground/30" />
              <span className="label">Enable auto-commit</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={gitPushOnCommit} onChange={(e) => setGitPushOnCommit(e.target.checked)} disabled={!editable}
                className="w-4 h-4 rounded-md border-muted-foreground/30" />
              <span className="label">Push on every commit</span>
            </label>
          </div>

          <div>
            <label className="label">Push Interval (minutes)<input className="input text-sm w-32" type="number" min={0} max={1440} value={gitPushInterval}
              onChange={(e) => setGitPushInterval(Number(e.target.value) || 0)} disabled={!editable || gitPushOnCommit} /></label>
            <div className="text-3xs text-muted-foreground mt-0.5">
              {gitPushOnCommit ? 'Push on commit is enabled — interval is ignored.' : gitPushInterval > 0 ? `Push every ${gitPushInterval} minutes. 0 = manual only.` : 'Pushes are manual only. Use the CLI `push_to_remote` or set an interval.'}
            </div>
          </div>
        </div>
      </Reveal>

      {/* Git Panel — status, push, remote, hooks, history */}
      <GitPanel
        projectId={projectId!}
        isAdmin={user?.role === 'admin'}
        canEdit={editable}
        remoteUrl={gitRemoteUrl}
        onRemoteChanged={() => {
          // Re-load project settings so the parent picks up any
          // remote_url change made by GitPanel (e.g. delete remote).
          if (!projectId) return;
          api.getProject(projectId).then((p: any) => {
            const git = p.git || {};
            setGitRemoteUrl(git.remote_url || '');
          }).catch(() => {});
        }}
      />

      {/* Save */}
      <div className="flex items-center gap-3">
        <button onClick={save} className={`btn-primary ${dirty ? 'ring-2 ring-cs-amber/50' : ''}`} disabled={!editable || saving}>
          <Save size={14} /> {saving ? 'Saving…' : dirty ? 'Save Changes *' : 'Save'}
        </button>
        {dirty && <span className="text-3xs text-cs-amber">Unsaved changes</span>}
      </div>
    </div>
  );
}
