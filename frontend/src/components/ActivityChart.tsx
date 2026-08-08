import { useEffect, useState, useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { useParams } from 'react-router-dom';
import { api, type ActivityData, type ActivityBucket, ACTIVITY_KIND_ORDER } from '../api/client';

const KIND_LABELS: Record<string, string> = {
  verification: 'Verification',
  change: 'Change',
  specification: 'Specification',
  requirement: 'Requirement',
  component: 'Component',
  decision: 'Decision',
  risk: 'Risk',
};

/** Days between two date strings to decide the default bucket granularity. */
function daysBetween(a: string, b: string): number {
  return (new Date(b).getTime() - new Date(a).getTime()) / 86400000;
}

/** Read a --chart-* CSS variable from the document root at call time so we
 *  always pick up the active theme. */
function chartColor(kind: string): string {
  if (typeof document === 'undefined') return '#888';
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--chart-${kind}`)
    .trim() || '#888';
}

/** The topmost non-zero segment in a bar gets a 4 px rounded top; all other
 *  segments get a 2 px gap against their neighbours by drawing a surface-colour
 *  stroke.  Recharts renders bars in stack order from bottom to top, so the
 *  "topmost" is the last kind in the stacking order that has a positive count. */
function topmostKind(entry: ActivityBucket, kinds: readonly string[]): string | null {
  for (let i = kinds.length - 1; i >= 0; i--) {
    const k = kinds[i];
    if ((entry as unknown as Record<string, number>)[k] > 0) return k;
  }
  return null;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 text-xs shadow-lg max-w-[220px]">
      <p className="font-semibold mb-1">{label}</p>
      {payload
        .filter((p: any) => p.value > 0)
        .map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-4">
            <span className="text-muted-foreground">
              {KIND_LABELS[p.dataKey] ?? p.dataKey}
            </span>
            <span className="font-mono tabular-nums text-foreground">{p.value}</span>
          </div>
        ))}
    </div>
  );
};

export default function ActivityChart() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<ActivityData | null>(null);
  const [bucket, setBucket] = useState<'day' | 'week' | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.getActivity(projectId, { bucket: bucket ?? undefined }).then((d) => {
      setData(d);
      // Auto-select bucket based on window size if the user hasn't picked one.
      if (bucket === null) {
        setBucket(daysBetween(d.since, d.until) >= 60 ? 'week' : 'day');
      }
    }).catch(() => {});
  }, [projectId, bucket]);

  const kindColors = useMemo(() => {
    const map: Record<string, string> = {};
    for (const k of ACTIVITY_KIND_ORDER) {
      map[k] = chartColor(k);
    }
    return map;
  }, []);

  // Build the list of actually visible kinds sorted by the fixed order.
  const visibleKinds = useMemo(() => {
    if (!data) return [] as readonly string[];
    const kinds = new Set(data.kinds ?? []);
    return ACTIVITY_KIND_ORDER.filter((k) => kinds.has(k));
  }, [data]);

  // Surface colour for the gap stroke between stacked segments.
  const surfaceColor = 'hsl(var(--card))';

  if (!data) {
    return (
      <div className="card p-5 mt-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
          Activity
        </h2>
        <div className="h-48 flex items-center justify-center text-xs text-muted-foreground">
          Loading…
        </div>
      </div>
    );
  }

  if (data.total === 0) {
    return (
      <div className="card p-5 mt-6">
        <h2 className="font-semibold text-sm text-card-foreground mb-3 flex items-center gap-2">
          Activity
        </h2>
        <div className="h-32 flex items-center justify-center text-sm text-muted-foreground">
          No activity in the selected window — try a wider range.
        </div>
      </div>
    );
  }

  return (
    <div className="card p-5 mt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-sm text-card-foreground flex items-center gap-2">
          Activity
          <span className="text-xs font-normal text-muted-foreground">
            {data.total} change{data.total !== 1 ? 's' : ''} ·{' '}
            {data.since} → {data.until}
          </span>
        </h2>
        <div className="flex items-center gap-1 text-xs">
          <button
            className={`px-2 py-1 rounded ${bucket === 'day' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setBucket('day')}
          >
            Day
          </button>
          <button
            className={`px-2 py-1 rounded ${bucket === 'week' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setBucket('week')}
          >
            Week
          </button>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={data.buckets}
          margin={{ top: 4, right: 4, left: -12, bottom: 2 }}
        >
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            axisLine={{ stroke: 'hsl(var(--border))' }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted) / 0.3)' }} />
          <Legend
            wrapperStyle={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}
            formatter={(value: string) => (
              <span className="text-muted-foreground">{KIND_LABELS[value] ?? value}</span>
            )}
          />
          {visibleKinds.map((kind) => (
            <Bar
              key={kind}
              dataKey={kind}
              stackId="a"
              fill={kindColors[kind]}
              stroke={surfaceColor}
              strokeWidth={2}
              isAnimationActive={true}
              animationDuration={400}
              shape={(props: any) => {
                // Determine whether *this* segment's bar is the topmost
                // non-zero one in its stack, based on the stacking order.
                const entry = props.payload as ActivityBucket | undefined;
                const top = entry ? topmostKind(entry, visibleKinds) : null;
                const rx = top === kind ? 4 : 0;
                const r = Math.min(rx, props.height);
                return (
                  <rect
                    x={props.x}
                    y={props.y}
                    width={props.width}
                    height={props.height}
                    fill={props.fill}
                    stroke={props.stroke}
                    strokeWidth={props.strokeWidth}
                    rx={r}
                    ry={r}
                  />
                );
              }}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
