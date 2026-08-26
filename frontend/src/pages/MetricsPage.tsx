import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import Reveal from '../components/Reveal';
import { AlertTriangle, Search, TrendingUp, Shield, GitBranch, FileWarning, Sparkles, Sigma, Flame, ShieldCheck, Table } from 'lucide-react';
import { api, type MetricsData, type GapItem, type QualityItem, type EvaluationData, type PughMatrix, type RiskBingo } from '../api/client';
import { EntityLink } from '../components/entities';
import { VerdictBadge } from '../components/parametrics';
import { DefinitionsManager, AnalysisCasesPanel } from '../components/DefinitionsPanel';
import { HelpTip } from '../components/HelpTip';
import LoadingSplash from '../components/LoadingSplash';
import ActivityChart from '../components/ActivityChart';
import { useAuthStore } from '../store/auth';

export default function MetricsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [conflicts, setConflicts] = useState<{ count: number; conflicts: any[] }>({ count: 0, conflicts: [] });
  const [compliance, setCompliance] = useState<{ standards: { name: string; count: number }[] }>({ standards: [] });
  const [coverage, setCoverage] = useState<{ coverage_pct: number; deep_pct: number; total: number; shallow_covered: number; deep_covered: number; items: any[] }>({ coverage_pct: 0, deep_pct: 0, total: 0, shallow_covered: 0, deep_covered: 0, items: [] });
  const [quality, setQuality] = useState<QualityItem[]>([]);
  const [qualityAvg, setQualityAvg] = useState(0);
  const [unreviewedCount, setUnreviewedCount] = useState(0);
  const [evaluation, setEvaluation] = useState<EvaluationData | null>(null);
  const [pugh, setPugh] = useState<PughMatrix | null>(null);
  const [bingo, setBingo] = useState<RiskBingo | null>(null);
  // Definitions and analysis cases are maintainer-tier (backend require_maintain).
  const editable = useAuthStore((s) => s.canEdit());

  useEffect(() => {
    if (!projectId) return;
    api.getEvaluation(projectId).then(setEvaluation).catch(() => {});
    api.getPugh(projectId).then(setPugh).catch(() => {});
    api.getRiskBingo(projectId).then(setBingo).catch(() => {});
    Promise.all([
      api.getMetrics(projectId),
      api.getGapAnalysis(projectId),
      api.getConflicts(projectId),
      api.getCompliance(projectId),
      api.getCoverageAnalysis(projectId),
      api.getQuality(projectId),
      api.getUnreviewed(projectId),
    ]).then(([m, g, c, comp, cov, qual, unrev]) => {
      setMetrics(m);
      setGaps(g.items);
      setConflicts(c);
      setCompliance(comp);
      setCoverage(cov);
      setQuality(qual.per_requirement);
      setQualityAvg(qual.average);
      setUnreviewedCount(unrev.items.length);
    }).catch(console.error);
  }, [projectId]);

  if (!metrics) return <div className="relative h-[70vh]"><LoadingSplash label="Analysing project…" /></div>;

  // A project with no requirements returns the short form of the payload, so
  // neither of these is guaranteed to be present.
  const q = metrics.quality_pct ?? {};
  const risks = metrics.risks;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-bold tracking-tight text-foreground mb-1">Metrics</h1>
      <HelpTip>High-level project health dashboard. Summary cards show overall counts. Quality scores measure completeness (descriptions, rationales, sources). Traceability shows shallow vs deep coverage. Gap analysis flags requirements missing key fields. Parametric constraints show pass/fail from the evaluation engine.</HelpTip>

      <div className="grid grid-cols-2 @3xl:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Total Requirements', value: metrics.total, icon: FileWarning, color: 'text-cs-blue bg-cs-blue/10' },
          { label: 'Coverage', value: `${coverage.coverage_pct}%`, icon: Shield, color: 'text-cs-green bg-cs-green/10' },
          { label: 'Conflicts', value: conflicts.count, icon: AlertTriangle, color: conflicts.count > 0 ? 'text-cs-red bg-cs-red/10' : 'text-cs-green bg-cs-green/10' },
          { label: 'Gaps', value: gaps.length, icon: Search, color: gaps.length > 0 ? 'text-cs-amber bg-cs-amber/10' : 'text-cs-green bg-cs-green/10' },
          { label: 'Unreviewed', value: unreviewedCount, icon: Shield, color: unreviewedCount > 0 ? 'text-cs-amber bg-cs-amber/10' : 'text-cs-green bg-cs-green/10' },
          // The headline risk number is the one that needs action: open risks
          // in the top two bands. Total risks would only grow, and a register
          // that is large but well-mitigated is a healthy one.
          { label: 'Severe Open Risks', value: risks?.severe_open ?? 0, icon: Flame, color: (risks?.severe_open ?? 0) > 0 ? 'text-cs-red bg-cs-red/10' : 'text-cs-green bg-cs-green/10' },
        ].map((card, i) => {
          const Icon = card.icon;
          return (
            <Reveal key={card.label} step={i} className="card p-4">
              <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${card.color} mb-3`}><Icon size={18} /></div>
              <div className="text-2xl font-bold text-card-foreground tabular-nums">{card.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{card.label}</div>
            </Reveal>
          );
        })}
      </div>

      <ActivityChart />

      <div className="grid grid-cols-1 @3xl:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2"><TrendingUp size={16} /> Quality Scores</h2>
          <div className="space-y-3">
            {Object.entries(q).map(([key, pct]) => (
              <div key={key}>
                <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span><span className="text-foreground font-medium tabular-nums">{pct}%</span></div>
                <div className="w-full bg-muted rounded-full h-2"><motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }} className={`h-full rounded-full ${pct >= 80 ? 'bg-cs-green' : pct >= 50 ? 'bg-cs-amber' : 'bg-cs-red'}`} /></div>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2"><GitBranch size={16} /> Traceability</h2>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground tabular-nums">{coverage.shallow_covered}</div>
              <div className="text-xs text-muted-foreground">Shallow Covered</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground tabular-nums">{coverage.deep_covered}</div>
              <div className="text-xs text-muted-foreground">Deep Covered</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground tabular-nums">{metrics.baselines}</div>
              <div className="text-xs text-muted-foreground">Baselines</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground tabular-nums">{compliance.standards.length}</div>
              <div className="text-xs text-muted-foreground">Standards</div>
            </div>
          </div>
        </motion.div>
      </div>

      {risks && risks.total > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.31 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-1 flex items-center gap-2">
            <Flame size={16} className="text-cs-red" /> Risk Profile
            <span className="text-xs font-normal text-muted-foreground">
              {risks.open} open of {risks.total}
            </span>
          </h2>
          <HelpTip>
            Bands come from this project's risk matrix (Settings → Risk Matrix), and are derived from each
            risk's severity and likelihood rather than stored — retune the matrix and these move with it.
            Only open, mitigating and monitoring risks count towards the profile; closed and accepted ones
            stay in the register as a record.
          </HelpTip>

          <div className="grid grid-cols-1 @3xl:grid-cols-2 gap-6 mt-4">
            <div>
              <div className="text-xs text-muted-foreground mb-2">Open risks by band</div>
              {risks.open > 0 ? (
                <>
                  <div className="flex w-full h-3 rounded-full overflow-hidden bg-muted">
                    {risks.bands.map((b) => {
                      const n = risks.open_by_band[b.key] ?? 0;
                      if (!n) return null;
                      return (
                        <motion.div
                          key={b.key}
                          initial={{ width: 0 }}
                          animate={{ width: `${(n / risks.open) * 100}%` }}
                          transition={{ duration: 0.5 }}
                          style={{ backgroundColor: b.color }}
                          title={`${b.label}: ${n}`}
                        />
                      );
                    })}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
                    {risks.bands.map((b) => (
                      <span key={b.key} className="inline-flex items-center gap-1.5 text-xs">
                        <span className="w-2.5 h-2.5 rounded-md shrink-0" style={{ backgroundColor: b.color }} />
                        <span className="text-muted-foreground">{b.label}</span>
                        <span className="text-foreground font-medium tabular-nums">{risks.open_by_band[b.key] ?? 0}</span>
                        {(risks.by_band[b.key] ?? 0) !== (risks.open_by_band[b.key] ?? 0) && (
                          <span className="text-muted-foreground text-3xs tabular-nums">
                            / {risks.by_band[b.key] ?? 0} total
                          </span>
                        )}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-xs text-muted-foreground py-2">
                  No open risks — every entry in the register is closed or accepted.
                </div>
              )}

              {risks.unrated > 0 && (
                <div className="mt-3 text-xs flex items-start gap-1.5 text-cs-amber">
                  <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                  <span>
                    {risks.unrated} {risks.unrated === 1 ? 'risk cannot be rated' : 'risks cannot be rated'} — severity or
                    likelihood is unset, or names a level this matrix does not define.
                  </span>
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">Register coverage</div>
              {[
                { label: 'With a mitigation', pct: risks.mitigation_pct, n: risks.with_mitigation },
                { label: 'Linked to requirements', pct: risks.linked_pct, n: risks.with_requirements },
              ].map((row) => (
                <div key={row.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">{row.label}</span>
                    <span className="text-foreground font-medium tabular-nums">{row.n} · {row.pct}%</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${row.pct}%` }}
                      transition={{ duration: 0.5 }}
                      className={`h-full rounded-full ${row.pct >= 80 ? 'bg-cs-green' : row.pct >= 50 ? 'bg-cs-amber' : 'bg-cs-red'}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {risks.top_open.length > 0 && (
            <div className="mt-5">
              <div className="text-xs text-muted-foreground mb-2">Most serious open risks</div>
              <div className="space-y-1.5">
                {risks.top_open.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-accent">
                    <span
                      className="badge text-3xs shrink-0"
                      style={{ backgroundColor: `${r.color}1a`, color: r.color }}
                    >
                      {r.label}
                    </span>
                    <EntityLink kind="risk" id={r.id} name={r.title} className="flex-1 min-w-0 hover:text-primary" />
                    <span className="text-muted-foreground text-3xs whitespace-nowrap">
                      {r.severity} · {r.likelihood.replace(/_/g, ' ')}
                    </span>
                    {r.mitigated ? (
                      <ShieldCheck size={13} className="text-cs-green shrink-0" aria-label="Has a mitigation" />
                    ) : (
                      <span className="badge bg-cs-amber/10 text-cs-amber text-4xs shrink-0">unmitigated</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {bingo && bingo.total > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.315 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <Table size={16} className="text-cs-teal" /> Risk Bingo
            <span className="text-xs font-normal text-muted-foreground">
              {bingo.total} risk{bingo.total !== 1 ? 's' : ''} mapped {bingo.severities.length}×{bingo.likelihoods.length}
            </span>
          </h2>
          <HelpTip>
            Every severity × likelihood cell counts the risks that land there.
            A zero cell reads "0", not blank — the shape of the empty space
            is the point of a bingo card. Each cell is tinted by its band colour.
          </HelpTip>
          <div className="flex gap-4 mt-3">
            <div className="overflow-x-auto max-w-full">
              <table className="text-xs border-collapse">
                <thead>
                  <tr>
                    <th className="p-1" aria-label="Severity"></th>
                    {bingo.likelihoods.map((l) => (
                      <th key={l} className="p-1.5 text-muted-foreground font-medium text-center whitespace-nowrap">
                        {l.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bingo.severities.map((sv, si) => (
                    <tr key={sv}>
                      <td className="p-1.5 text-muted-foreground font-medium text-right whitespace-nowrap">
                        {sv}
                      </td>
                      {bingo.likelihoods.map((_, li) => {
                        const count = bingo.counts[si][li];
                        const bandKey = bingo.bands[si][li];
                        const band = risks?.bands?.find((b) => b.key === bandKey);
                        return (
                          <td
                            key={li}
                            className="p-1.5 text-center tabular-nums border border-border/50 min-w-[3rem]"
                            style={band ? { backgroundColor: `${band.color}20`, borderColor: `${band.color}40` } : undefined}
                          >
                            {count}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {bingo.unrated > 0 && (
              <div className="shrink-0 flex flex-col items-center justify-center gap-0.5 text-xs text-cs-amber bg-cs-amber/5 rounded-lg px-3 py-2">
                <AlertTriangle size={14} />
                <span className="font-semibold">{bingo.unrated}</span>
                <span className="text-3xs text-muted-foreground">unrated</span>
              </div>
            )}
          </div>
        </motion.div>
      )}

      {evaluation && (evaluation.requirements.length > 0 || evaluation.data_issues.length > 0) && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.32 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <Sigma size={16} className="text-cs-teal" /> Parametric Constraints
            <span className="text-xs font-normal text-muted-foreground">
              {evaluation.parameter_count} parameters · {evaluation.measurement_count} measurements
            </span>
          </h2>
          <div className="flex gap-4 mb-3 text-xs">
            {(['pass', 'fail', 'unknown', 'error'] as const).map((k) =>
              evaluation.summary[k] ? (
                <span key={k} className="inline-flex items-center gap-1.5">
                  <VerdictBadge status={k} /> × {evaluation.summary[k]}
                </span>
              ) : null,
            )}
            {(evaluation.measured_summary.pass + evaluation.measured_summary.fail) > 0 && (
              <span className="text-muted-foreground">
                measured: {evaluation.measured_summary.pass} pass / {evaluation.measured_summary.fail} fail
              </span>
            )}
          </div>
          {evaluation.data_issues.length > 0 && (
            <div className="mb-3 rounded-lg border border-cs-amber/30 bg-cs-amber/10 p-2.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-cs-amber">
                <AlertTriangle size={13} />
                {evaluation.data_issues.length} value{evaluation.data_issues.length === 1 ? '' : 's'} ignored
              </div>
              <div className="mt-1.5 space-y-0.5">
                {evaluation.data_issues.slice(0, 5).map((issue, i) => (
                  <div key={i} className="text-2xs text-muted-foreground">
                    <span className="font-mono">{issue.ref}</span>
                    {issue.source && <span> (from {issue.source})</span>}
                    : <span className="font-mono">{issue.value}</span> is not a number
                  </div>
                ))}
                {evaluation.data_issues.length > 5 && (
                  <div className="text-2xs text-muted-foreground">
                    …and {evaluation.data_issues.length - 5} more
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            {evaluation.requirements
              .filter((r) => r.verdict !== 'none')
              .sort((a, b) => (a.verdict === 'fail' || a.verdict === 'error' ? -1 : 1) - (b.verdict === 'fail' || b.verdict === 'error' ? -1 : 1))
              .slice(0, 10)
              .map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-accent">
                  <EntityLink kind="requirement" id={r.id} name={r.name} className="flex-1 min-w-0 hover:text-primary" />
                  {r.measured_verdict && <VerdictBadge status={r.measured_verdict} prefix="measured" />}
                  <VerdictBadge status={r.verdict} />
                </div>
              ))}
          </div>
        </motion.div>
      )}

      {projectId && (
        <div className="mt-6 space-y-6">
          <DefinitionsManager projectId={projectId} editable={editable} />
          <AnalysisCasesPanel projectId={projectId} editable={editable} />
        </div>
      )}

      {pugh && pugh.columns.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.33 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-1 flex items-center gap-2">
            <Table size={16} className="text-cs-teal" /> Pugh Matrix
            <span className="text-xs font-normal text-muted-foreground">
              {pugh.columns.length} of {pugh.total_candidates} candidates
            </span>
          </h2>
          <HelpTip>
            A Pugh matrix compares the best-valued requirements (columns) against weighted stakeholders
            (rows), relative to a chosen datum. Each cell shows whether the requirement scores above
            (+), below (−), or equal to (0) the datum for that stakeholder. The datum's own column is
            all zero — that is what a datum means.
          </HelpTip>
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-1.5 px-2 text-muted-foreground font-medium w-32">Stakeholder</th>
                  {pugh.columns.map((col) => (
                    <th key={col.id} className={`py-1.5 px-2 text-center font-mono text-2xs ${col.id === pugh.datum ? 'text-primary' : 'text-foreground'}`}>
                      <div className="truncate max-w-[100px]" title={col.id}>{col.id}</div>
                      {col.id === pugh.datum && (
                        <span className="badge bg-primary/10 text-primary text-4xs">datum</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pugh.stakeholders.map((s) => (
                  <tr key={s.name} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="py-1.5 px-2 text-foreground">
                      <span className="font-medium">{s.name}</span>
                      <span className="text-muted-foreground ml-1">×{s.weight}</span>
                    </td>
                    {pugh.columns.map((col) => {
                      const cell = col.cells[s.name];
                      if (!cell) return <td key={col.id} className="py-1.5 px-2 text-center text-muted-foreground">–</td>;
                      const signChar = cell.sign === 1 ? '+' : cell.sign === -1 ? '−' : cell.sign === 0 ? '0' : '·';
                      const signColor = cell.sign === 1 ? 'text-cs-green' : cell.sign === -1 ? 'text-cs-red' : 'text-muted-foreground';
                      return (
                        <td key={col.id} className={`py-1.5 px-2 text-center tabular-nums ${signColor}`}>
                          <span className="font-semibold">{signChar}</span>
                          {cell.score != null && (
                            <span className="text-muted-foreground ml-0.5">{cell.score}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-border">
                  <td className="py-1.5 px-2 text-muted-foreground text-3xs uppercase tracking-wider">plus / minus</td>
                  {pugh.columns.map((col) => (
                    <td key={col.id} className="py-1.5 px-2 text-center tabular-nums text-3xs">
                      <span className="text-cs-green">{col.plus}</span>
                      <span className="text-muted-foreground"> / </span>
                      <span className="text-cs-red">{col.minus}</span>
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="py-1 px-2 text-muted-foreground text-3xs uppercase tracking-wider">weighted</td>
                  {pugh.columns.map((col) => (
                    <td key={col.id} className={`py-1 px-2 text-center tabular-nums text-2xs font-mono ${col.weighted > 0 ? 'text-cs-green' : col.weighted < 0 ? 'text-cs-red' : 'text-muted-foreground'}`}>
                      {col.weighted > 0 ? '+' : ''}{col.weighted.toFixed(2)}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        </motion.div>
      )}

      {quality.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><Sparkles size={16} className="text-cs-purple" /> Requirement Quality ({qualityAvg}/100)</h2>
          <div className="space-y-2">
            {quality.slice(0, 10).map((q) => (
              <div key={q.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-accent">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-2xs font-bold shrink-0 ${q.score >= 80 ? 'bg-cs-green/10 text-cs-green' : q.score >= 50 ? 'bg-cs-amber/10 text-cs-amber' : 'bg-cs-red/10 text-cs-red'}`}>{q.score}</div>
                <div className="flex-1 min-w-0">
                  <EntityLink kind="requirement" id={q.id} />
                  <div className="text-3xs text-muted-foreground truncate">{q.name}</div>
                </div>
                <div className="flex gap-1 flex-wrap justify-end">
                  {q.findings.slice(0, 3).map((f, fi) => (
                    <span key={fi} className={`badge text-4xs ${f.severity === 'error' ? 'bg-cs-red/10 text-cs-red' : f.severity === 'warning' ? 'bg-cs-amber/10 text-cs-amber' : 'bg-muted text-muted-foreground'}`} title={f.message}>{f.rule.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {gaps.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-cs-amber" /> Gap Analysis ({gaps.length} issues)</h2>
          <div className="space-y-1.5">
            {gaps.slice(0, 10).map((g, i) => (
              <div key={i} className="flex items-center gap-2 text-xs py-1 px-2 rounded-md hover:bg-accent">
                <EntityLink kind="requirement" id={g.id} />
                <span className="text-foreground">{g.name || ''}</span>
                <div className="flex gap-1 ml-auto">{g.issues.map(iss => <span key={iss} className="badge bg-cs-amber/10 text-cs-amber text-3xs">{iss.replace(/_/g, ' ')}</span>)}</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {conflicts.count > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-cs-red" /> Conflicts ({conflicts.count})</h2>
          <div className="space-y-1.5">
            {conflicts.conflicts.map((c, i) => (
              <div key={i} className="text-xs py-1 px-2 rounded-md bg-cs-red/5 text-cs-red">
                {c.type === 'duplicate_name' ? `Duplicate name "${c.name}": ${(c.ids || []).join(', ')}` : `Conflict: ${c.a} ↔ ${c.b}`}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
