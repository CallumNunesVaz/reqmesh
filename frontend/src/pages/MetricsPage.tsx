import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, CheckCircle2, AlertTriangle, Search, TrendingUp, Shield, GitBranch, FileWarning, Sparkles, Sigma } from 'lucide-react';
import { api, type MetricsData, type ImpactResult, type GapItem, type QualityItem, type EvaluationData } from '../api/client';
import { EntityLink } from '../components/entities';
import { VerdictBadge } from '../components/parametrics';
import { HelpTip } from '../components/HelpTip';

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

  useEffect(() => {
    if (!projectId) return;
    api.getEvaluation(projectId).then(setEvaluation).catch(() => {});
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

  if (!metrics) return <div className="flex items-center justify-center h-64"><div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" /></div>;

  const q = metrics.quality_pct;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-bold text-foreground mb-1">Metrics & Analysis</h1>
      <HelpTip>High-level project health dashboard. Summary cards show overall counts. Quality scores measure completeness (descriptions, rationales, sources). Traceability shows shallow vs deep coverage. Gap analysis flags requirements missing key fields. Parametric constraints show pass/fail from the evaluation engine.</HelpTip>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Total Reqs', value: metrics.total, icon: FileWarning, color: 'text-blue-400 bg-blue-400/10' },
          { label: 'Coverage', value: `${coverage.coverage_pct}%`, icon: Shield, color: 'text-emerald-400 bg-emerald-400/10' },
          { label: 'Conflicts', value: conflicts.count, icon: AlertTriangle, color: conflicts.count > 0 ? 'text-red-400 bg-red-400/10' : 'text-green-400 bg-green-400/10' },
          { label: 'Gaps', value: gaps.length, icon: Search, color: gaps.length > 0 ? 'text-amber-400 bg-amber-400/10' : 'text-green-400 bg-green-400/10' },
          { label: 'Unreviewed', value: unreviewedCount, icon: Shield, color: unreviewedCount > 0 ? 'text-amber-400 bg-amber-400/10' : 'text-emerald-400 bg-emerald-400/10' },
        ].map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div key={card.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="card p-4">
              <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${card.color} mb-3`}><Icon size={18} /></div>
              <div className="text-2xl font-bold text-card-foreground">{card.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{card.label}</div>
            </motion.div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2"><TrendingUp size={16} /> Quality Scores</h2>
          <div className="space-y-3">
            {Object.entries(q).map(([key, pct]) => (
              <div key={key}>
                <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span><span className="text-foreground font-medium">{pct}%</span></div>
                <div className="w-full bg-muted rounded-full h-2"><motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }} className={`h-full rounded-full ${pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'}`} /></div>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2"><GitBranch size={16} /> Traceability</h2>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground">{coverage.shallow_covered}</div>
              <div className="text-xs text-muted-foreground">Shallow Covered</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground">{coverage.deep_covered}</div>
              <div className="text-xs text-muted-foreground">Deep Covered</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground">{metrics.baselines}</div>
              <div className="text-xs text-muted-foreground">Baselines</div>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-card-foreground">{compliance.standards.length}</div>
              <div className="text-xs text-muted-foreground">Standards</div>
            </div>
          </div>
        </motion.div>
      </div>

      {evaluation && evaluation.requirements.length > 0 && (
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
          <div className="space-y-1.5">
            {evaluation.requirements
              .filter((r) => r.verdict !== 'none')
              .sort((a, b) => (a.verdict === 'fail' || a.verdict === 'error' ? -1 : 1) - (b.verdict === 'fail' || b.verdict === 'error' ? -1 : 1))
              .slice(0, 10)
              .map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent">
                  <EntityLink kind="requirement" id={r.id} name={r.name} className="flex-1 min-w-0 hover:text-primary" />
                  {r.measured_verdict && <VerdictBadge status={r.measured_verdict} prefix="measured" />}
                  <VerdictBadge status={r.verdict} />
                </div>
              ))}
          </div>
        </motion.div>
      )}

      {quality.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><Sparkles size={16} className="text-violet-400" /> Requirement Quality ({qualityAvg}/100)</h2>
          <div className="space-y-2">
            {quality.slice(0, 10).map((q) => (
              <div key={q.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-[11px] font-bold shrink-0 ${q.score >= 80 ? 'bg-emerald-500/10 text-emerald-400' : q.score >= 50 ? 'bg-amber-500/10 text-amber-400' : 'bg-red-500/10 text-red-400'}`}>{q.score}</div>
                <div className="flex-1 min-w-0">
                  <EntityLink kind="requirement" id={q.id} />
                  <div className="text-[10px] text-muted-foreground truncate">{q.name}</div>
                </div>
                <div className="flex gap-1 flex-wrap justify-end">
                  {q.findings.slice(0, 3).map((f, fi) => (
                    <span key={fi} className={`badge text-[9px] ${f.severity === 'error' ? 'bg-red-500/10 text-red-400' : f.severity === 'warning' ? 'bg-amber-500/10 text-amber-400' : 'bg-muted text-muted-foreground'}`} title={f.message}>{f.rule.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {gaps.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-amber-400" /> Gap Analysis ({gaps.length} issues)</h2>
          <div className="space-y-1.5">
            {gaps.slice(0, 10).map((g, i) => (
              <div key={i} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                <EntityLink kind="requirement" id={g.id} />
                <span className="text-foreground">{g.name || ''}</span>
                <div className="flex gap-1 ml-auto">{g.issues.map(iss => <span key={iss} className="badge bg-amber-500/10 text-amber-400 text-[10px]">{iss.replace(/_/g, ' ')}</span>)}</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {conflicts.count > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="card p-5 mt-6">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-red-400" /> Conflicts ({conflicts.count})</h2>
          <div className="space-y-1.5">
            {conflicts.conflicts.map((c, i) => (
              <div key={i} className="text-xs py-1 px-2 rounded bg-red-500/5 text-red-400">
                {c.type === 'duplicate_name' ? `Duplicate name "${c.name}": ${(c.ids || []).join(', ')}` : `Conflict: ${c.a} ↔ ${c.b}`}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
