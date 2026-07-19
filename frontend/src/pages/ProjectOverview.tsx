import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { BarChart3, ClipboardList, FileText, CheckCircle2, AlertTriangle, Zap, Gauge, Plug, PenTool, Lock, Boxes } from 'lucide-react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList } from 'recharts';
import { api, type Requirement, type VerificationCase } from '../api/client';

const statusColors: Record<string, string> = {
  proposed: 'border-blue-500/50 bg-blue-500/10 text-blue-400',
  approved: 'border-green-500/50 bg-green-500/10 text-green-400',
  implemented: 'border-purple-500/50 bg-purple-500/10 text-purple-400',
  verified: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400',
  rejected: 'border-red-500/50 bg-red-500/10 text-red-400',
  deprecated: 'border-zinc-500/50 bg-zinc-500/10 text-zinc-400',
};

const priorityColors: Record<string, string> = {
  low: '#95a5a6',
  medium: '#539fe6',
  high: '#f59e0b',
  critical: '#ef4444',
};

const typeColors: Record<string, string> = {
  functional: '#539fe6',
  non_functional: '#009d96',
  interface: '#b291ff',
  design: '#ec4899',
  constraint: '#f59e0b',
};

const typeIcons: Record<string, React.ComponentType<any>> = {
  functional: Zap,
  non_functional: Gauge,
  interface: Plug,
  design: PenTool,
  constraint: Lock,
};

const qualityColors: Record<string, string> = {
  description: '#539fe6',
  rationale: '#29ad55',
  source: '#f59e0b',
  allocation: '#b291ff',
  traceability: '#ec4899',
};

interface ProjectStats {
  totalRequirements: number;
  totalVerificationCases: number;
  totalSpecifications: number;
  totalComponents: number;
  statusCounts: Record<string, number>;
  verificationStatus: { pending: number; passed: number; failed: number };
  coverage: number;
  withRationale: number;
  withSource: number;
  withAllocation: number;
  withTraces: number;
  baselines: number;
  priorityCounts: Record<string, number>;
  typeCounts: Record<string, number>;
  methodCounts: Record<string, number>;
  qualityPct: { label: string; value: number; color: string }[];
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold capitalize mb-0.5">{payload[0].name || label}</p>
      <p>{payload[0].value} requirements</p>
    </div>
  );
};

export default function ProjectOverview() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<{ id: string; name: string; path: string } | null>(null);
  const [stats, setStats] = useState<ProjectStats | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([
      api.getProject(projectId),
      api.listRequirements(projectId) as Promise<Requirement[]>,
      api.listSpecifications(projectId) as Promise<{ id: string; name: string }[]>,
      api.listVerificationCases(projectId) as Promise<VerificationCase[]>,
      api.listComponents(projectId).catch(() => []),
    ]).then(([proj, reqs, specs, vcs, components]) => {
      setProject(proj);
      const statusCounts: Record<string, number> = {};
      const priorityCounts: Record<string, number> = {};
      const typeCounts: Record<string, number> = {};
      const methodCounts: Record<string, number> = {};
      let verifiedCount = 0;
      let withRationale = 0;
      let withSource = 0;
      let withAllocation = 0;
      let withDescription = 0;
      let withTraces = 0;
      const baselines = new Set<string>();
      for (const r of reqs) {
        statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
        priorityCounts[r.priority] = (priorityCounts[r.priority] || 0) + 1;
        typeCounts[r.type] = (typeCounts[r.type] || 0) + 1;
        methodCounts[r.verification_method] = (methodCounts[r.verification_method] || 0) + 1;
        if (r.status === 'verified') verifiedCount++;
        if (r.rationale) withRationale++;
        if (r.source) withSource++;
        if (r.allocated_to) withAllocation++;
        if (r.description) withDescription++;
        if ((r.relations?.length || 0) > 0) withTraces++;
        if (r.baseline) baselines.add(r.baseline);
      }
      const total = reqs.length;
      const vcsPassed = vcs.filter((v) => v.status === 'passed').length;
      const vcsFailed = vcs.filter((v) => v.status === 'failed').length;
      const vcsPending = vcs.filter((v) => v.status !== 'passed' && v.status !== 'failed').length;
      setStats({
        totalRequirements: total,
        totalVerificationCases: vcs.length,
        totalSpecifications: specs.length,
        totalComponents: components.length,
        statusCounts,
        priorityCounts,
        typeCounts,
        methodCounts,
        verificationStatus: { pending: vcsPending, passed: vcsPassed, failed: vcsFailed },
        coverage: total > 0 ? Math.round((verifiedCount / total) * 100) : 0,
        withRationale,
        withSource,
        withAllocation,
        withTraces,
        baselines: baselines.size,
        qualityPct: [
          { label: 'Description', value: total > 0 ? Math.round((withDescription / total) * 100) : 0, color: qualityColors.description },
          { label: 'Rationale', value: total > 0 ? Math.round((withRationale / total) * 100) : 0, color: qualityColors.rationale },
          { label: 'Source', value: total > 0 ? Math.round((withSource / total) * 100) : 0, color: qualityColors.source },
          { label: 'Allocation', value: total > 0 ? Math.round((withAllocation / total) * 100) : 0, color: qualityColors.allocation },
          { label: 'Traceability', value: total > 0 ? Math.round((withTraces / total) * 100) : 0, color: qualityColors.traceability },
        ],
      });
    }).catch(console.error);
  }, [projectId]);

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  const statCards = [
    { label: 'Requirements', value: stats.totalRequirements, icon: ClipboardList, color: 'text-blue-400 bg-blue-400/10', to: `/project/${projectId}/requirements` },
    { label: 'Specifications', value: stats.totalSpecifications, icon: FileText, color: 'text-amber-400 bg-amber-400/10', to: `/project/${projectId}/specifications` },
    { label: 'Components', value: stats.totalComponents, icon: Boxes, color: 'text-orange-400 bg-orange-400/10', to: `/project/${projectId}/components` },
    { label: 'Verification Cases', value: stats.totalVerificationCases, icon: CheckCircle2, color: 'text-green-400 bg-green-400/10', to: `/project/${projectId}/verification` },
    { label: 'Coverage', value: `${stats.coverage}%`, icon: BarChart3, color: 'text-purple-400 bg-purple-400/10', to: `/project/${projectId}/traces` },
  ];

  const priorityData = Object.entries(stats.priorityCounts)
    .sort(([a], [b]) => ['critical', 'high', 'medium', 'low'].indexOf(a) - ['critical', 'high', 'medium', 'low'].indexOf(b))
    .map(([k, v]) => ({ name: k, count: v, fill: priorityColors[k] || '#64748b' }));

  const typeData = Object.entries(stats.typeCounts)
    .map(([k, v]) => ({ name: k.replace('_', ' '), count: v, fill: typeColors[k] || '#64748b' }));

  const methodData = Object.entries(stats.methodCounts)
    .sort(([, a], [, b]) => b - a)
    .map(([k, v]) => ({ name: k, count: v, fill: priorityColors.medium }));

  return (
    <div className="max-w-6xl mx-auto p-8">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{project?.name || projectId}</h1>
        <p className="text-sm text-muted-foreground font-mono mt-1">{project?.path || ''}</p>
      </motion.div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mt-6">
        {statCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.05 }}
              className="card p-4 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate(card.to)}
            >
              <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${card.color} mb-3`}>
                <Icon size={18} />
              </div>
              <div className="text-2xl font-bold text-card-foreground">{card.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{card.label}</div>
            </motion.div>
          );
        })}
      </div>

      {/* Row 1: Status + Quality */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Requirement Status */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2">
            <ClipboardList size={16} />
            Requirement Status
          </h2>
          <div className="space-y-2">
            {Object.entries(stats.statusCounts).map(([status, count]) => {
              const pct = stats.totalRequirements > 0 ? (count / stats.totalRequirements) * 100 : 0;
              const barColor =
                status === 'verified' ? 'bg-emerald-500' :
                status === 'approved' ? 'bg-green-500' :
                status === 'proposed' ? 'bg-blue-500' :
                status === 'rejected' ? 'bg-destructive' :
                'bg-purple-500';
              return (
                <div key={status} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`badge ${statusColors[status] || 'border-zinc-500/50 bg-zinc-500/10 text-zinc-400'}`}>
                      {status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-muted-foreground">{count}</span>
                    <div className="w-24 bg-muted rounded-full h-1.5">
                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* Quality Completeness */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <BarChart3 size={16} />
            Quality Completeness
          </h2>
          <div className="space-y-2.5">
            {stats.qualityPct.map((q) => (
              <div key={q.label}>
                <div className="flex justify-between text-xs text-muted-foreground mb-1">
                  <span>{q.label}</span>
                  <span className="font-mono">{q.value}%</span>
                </div>
                <div className="w-full bg-muted rounded-full h-1.5">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${q.value}%` }}
                    transition={{ duration: 0.6, delay: 0.5 }}
                    className="h-full rounded-full"
                    style={{ backgroundColor: q.color }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-3 border-t text-[10px] text-muted-foreground">
            {stats.totalRequirements > 0
              ? `${stats.withTraces} of ${stats.totalRequirements} requirements have trace links`
              : 'No requirements yet'}
          </div>
        </motion.div>
      </div>

      {/* Row 2: Priority + Type (charts) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Priority Distribution */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <AlertTriangle size={16} />
            Priority Distribution
          </h2>
          {priorityData.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">No data</p>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={priorityData} layout="vertical" margin={{ left: 0, right: 24, top: 2, bottom: 2 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} width={55} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted) / 0.3)' }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18}>
                  <LabelList dataKey="count" position="right" style={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  {priorityData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* Type Distribution */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <Zap size={16} />
            Requirement Types
          </h2>
          {typeData.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">No data</p>
          ) : (
            <div className="flex items-center gap-4">
              <ResponsiveContainer width={160} height={160}>
                <PieChart>
                  <Pie
                    data={typeData}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={38}
                    outerRadius={70}
                    paddingAngle={3}
                    stroke="transparent"
                  >
                    {typeData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-1.5">
                {typeData.map((t) => {
                  const Icon = typeIcons[Object.keys(typeColors).find(k => k.replace('_', ' ') === t.name) || 'functional'] || Zap;
                  return (
                    <div key={t.name} className="flex items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: t.fill }} />
                        <span className="text-muted-foreground capitalize truncate">{t.name}</span>
                      </div>
                      <span className="font-mono tabular-nums text-muted-foreground shrink-0">{t.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </motion.div>
      </div>

      {/* Row 3: Verification Method + Verification Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Verification Method */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
            <CheckCircle2 size={16} />
            Verification Method
          </h2>
          {methodData.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">No data</p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={methodData} margin={{ left: 0, right: 0, top: 8, bottom: 2 }}>
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted) / 0.3)' }} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={64} fill="hsl(var(--primary))">
                  <LabelList dataKey="count" position="top" style={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        {/* Verification Progress */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.65 }} className="card p-5">
          <h2 className="font-semibold text-sm text-card-foreground mb-4 flex items-center gap-2">
            <BarChart3 size={16} />
            Verification Progress
          </h2>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>Verification Coverage</span>
                <span>{stats.coverage}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${stats.coverage}%` }}
                  transition={{ duration: 0.8, delay: 0.5 }}
                  className="h-full bg-primary rounded-full"
                />
              </div>
            </div>
            <div className="flex gap-4 pt-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-emerald-500" />
                <span className="text-xs text-muted-foreground">
                  Passed: <strong className="text-foreground">{stats.verificationStatus.passed}</strong>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-amber-500" />
                <span className="text-xs text-muted-foreground">
                  Pending: <strong className="text-foreground">{stats.verificationStatus.pending}</strong>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-destructive" />
                <span className="text-xs text-muted-foreground">
                  Failed: <strong className="text-foreground">{stats.verificationStatus.failed}</strong>
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
