// Orthogonal edge router for the UML block diagram.
//
// The stock smoothstep edge draws every connection from the source's
// right-center to the target's left-center, so parallel edges stack on one
// another and long edges plough straight through intervening blocks. This
// router plans all edges of a diagram together against the laid-out blocks:
//
//  - ports fan out along a node face instead of sharing its center,
//  - vertical runs inside a channel (the gutter between two ranks) get
//    distinct lanes via greedy interval partitioning, so runs never overlap,
//  - edges that span several ranks or run backwards travel along a corridor —
//    a cross-axis gap that is free of blocks in every rank they cross.
//
// Everything is computed in "flow" coordinates (m = main/rank axis,
// c = cross axis) so one code path serves all four rank directions.

export interface NodeRect { id: string; x: number; y: number; w: number; h: number }
export interface EdgeRef { id: string; source: string; target: string }
export interface Pt { x: number; y: number }

export interface RouteOpts {
  rankdir: 'LR' | 'RL' | 'TB' | 'BT';
  /** Spacing between parallel vertical runs sharing a channel. */
  laneGap: number;
  /** Spacing between parallel corridor runs sharing a gap. */
  runGap: number;
  /** Port fan-out band on a node face, relative to the face start. */
  portBand: [number, number];
  /** Clearance kept between a run and any block it passes. */
  margin: number;
}

const DEFAULTS: Omit<RouteOpts, 'portBand'> = { rankdir: 'LR', laneGap: 9, runGap: 7, margin: 8 };

interface FRect { id: string; m0: number; m1: number; c0: number; c1: number }

function toFlow(r: NodeRect, dir: RouteOpts['rankdir']): FRect {
  switch (dir) {
    case 'LR': return { id: r.id, m0: r.x, m1: r.x + r.w, c0: r.y, c1: r.y + r.h };
    case 'RL': return { id: r.id, m0: -(r.x + r.w), m1: -r.x, c0: r.y, c1: r.y + r.h };
    case 'TB': return { id: r.id, m0: r.y, m1: r.y + r.h, c0: r.x, c1: r.x + r.w };
    case 'BT': return { id: r.id, m0: -(r.y + r.h), m1: -r.y, c0: r.x, c1: r.x + r.w };
  }
}

function fromFlow(m: number, c: number, dir: RouteOpts['rankdir']): Pt {
  switch (dir) {
    case 'LR': return { x: m, y: c };
    case 'RL': return { x: -m, y: c };
    case 'TB': return { x: c, y: m };
    case 'BT': return { x: c, y: -m };
  }
}

/** Group rects into ranks: clusters along the main axis. */
function buildRanks(rects: FRect[]): FRect[][] {
  const sorted = [...rects].sort((a, b) => a.m0 - b.m0);
  const ranks: FRect[][] = [];
  for (const r of sorted) {
    const cur = ranks[ranks.length - 1];
    // Same rank when the main-extent start is within a few px of the cluster.
    if (cur && Math.abs(r.m0 - cur[0].m0) < 10) cur.push(r);
    else ranks.push([r]);
  }
  return ranks;
}

/** Merged blocked intervals along the cross axis for a set of ranks. */
function blockedIntervals(ranks: FRect[][], from: number, to: number, margin: number): [number, number][] {
  const iv: [number, number][] = [];
  for (let i = from; i <= to; i++) {
    for (const r of ranks[i] ?? []) iv.push([r.c0 - margin, r.c1 + margin]);
  }
  iv.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [a, b] of iv) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else merged.push([a, b]);
  }
  return merged;
}

/**
 * Find a corridor: the free cross-axis interval nearest `pref` that is clear
 * of every block in ranks[from..to]. Always succeeds — the space above the
 * first block and below the last is open.
 */
export function findCorridor(
  ranks: FRect[][], from: number, to: number, pref: number, margin: number,
): [number, number] {
  const blocked = blockedIntervals(ranks, from, to, margin);
  if (blocked.length === 0) return [pref - 20, pref + 20];
  const gaps: [number, number][] = [];
  gaps.push([blocked[0][0] - 64, blocked[0][0]]);
  for (let i = 0; i + 1 < blocked.length; i++) {
    if (blocked[i + 1][0] - blocked[i][1] >= 14) gaps.push([blocked[i][1], blocked[i + 1][0]]);
  }
  gaps.push([blocked[blocked.length - 1][1], blocked[blocked.length - 1][1] + 64]);
  let best = gaps[0];
  let bestDist = Infinity;
  for (const g of gaps) {
    const nearest = Math.min(Math.max(pref, g[0]), g[1]);
    const d = Math.abs(nearest - pref);
    if (d < bestDist) { bestDist = d; best = g; }
  }
  return best;
}

/**
 * Greedy interval partitioning: segments whose extents overlap get distinct
 * lanes; disjoint segments may share one. Returns lane index per segment and
 * the number of lanes used.
 */
export function assignLanes(segments: { lo: number; hi: number }[]): { lanes: number[]; count: number } {
  const order = segments.map((_, i) => i).sort((a, b) => segments[a].lo - segments[b].lo);
  const laneEnds: number[] = [];
  const lanes = new Array(segments.length).fill(0);
  for (const i of order) {
    const s = segments[i];
    let lane = laneEnds.findIndex((end) => end <= s.lo);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(s.hi); }
    else laneEnds[lane] = s.hi;
    lanes[i] = lane;
  }
  return { lanes, count: laneEnds.length };
}

interface Channel { m0: number; m1: number }

interface PlannedEdge {
  id: string;
  sId: string;
  tId: string;
  kind: 'adjacent' | 'span' | 'loop';
  sPort: number;         // cross position of the source port
  tPort: number;         // cross position of the target port
  sFace: number;         // main position of the source face
  tFace: number;         // main position of the target face
  sChannel: number;      // channel index for the vertical run leaving the source
  tChannel: number;      // channel index for the vertical run entering the target
  corridor?: [number, number];  // free cross interval for the long run
  corridorKey?: string;
  laneM?: number;        // resolved: single-channel vertical position
  sLaneM?: number; tLaneM?: number; runC?: number;  // resolved: span/loop positions
}

/**
 * Route every edge orthogonally. Returns edge id → polyline in canvas
 * coordinates, ready for `roundedPath`.
 */
export function routeEdges(nodes: NodeRect[], edges: EdgeRef[], opts?: Partial<RouteOpts>): Map<string, Pt[]> {
  const out = new Map<string, Pt[]>();
  if (nodes.length === 0 || edges.length === 0) return out;
  const dir = opts?.rankdir ?? DEFAULTS.rankdir;
  const laneGap = opts?.laneGap ?? DEFAULTS.laneGap;
  const runGap = opts?.runGap ?? DEFAULTS.runGap;
  const margin = opts?.margin ?? DEFAULTS.margin;
  const flow = nodes.map((n) => toFlow(n, dir));
  const first = flow[0];
  const portBand = opts?.portBand ?? [12, Math.max(24, Math.min(44, first.c1 - first.c0 - 12))];

  const byId = new Map(flow.map((r) => [r.id, r]));
  const ranks = buildRanks(flow);
  const rankOf = new Map<string, number>();
  ranks.forEach((rank, i) => rank.forEach((r) => rankOf.set(r.id, i)));

  // Channels: gutters between consecutive ranks, plus virtual gutters before
  // the first rank and after the last for loop-backs off the diagram edge.
  const channels: Channel[] = [];
  const firstM = Math.min(...ranks[0].map((r) => r.m0));
  channels.push({ m0: firstM - 56, m1: firstM });          // index 0 = before rank 0
  for (let i = 0; i + 1 < ranks.length; i++) {
    channels.push({ m0: Math.max(...ranks[i].map((r) => r.m1)), m1: Math.min(...ranks[i + 1].map((r) => r.m0)) });
  }
  const lastM = Math.max(...ranks[ranks.length - 1].map((r) => r.m1));
  channels.push({ m0: lastM, m1: lastM + 56 });            // index ranks.length = after last
  // channel index convention: channel k sits before rank k (k in 0..ranks.length)
  const rightOf = (rank: number) => rank + 1;
  const leftOf = (rank: number) => rank;

  // ── Plan: ports and topology ─────────────────────────────────────────────
  const outPorts = new Map<string, PlannedEdge[]>();  // per source node
  const inPorts = new Map<string, PlannedEdge[]>();   // per target node
  const planned: PlannedEdge[] = [];

  for (const e of edges) {
    const s = byId.get(e.source);
    const t = byId.get(e.target);
    if (!s || !t || e.source === e.target) continue;
    const sr = rankOf.get(s.id)!;
    const tr = rankOf.get(t.id)!;
    const p: PlannedEdge = {
      id: e.id,
      sId: s.id,
      tId: t.id,
      kind: tr === sr + 1 ? 'adjacent' : tr > sr + 1 ? 'span' : 'loop',
      sPort: 0, tPort: 0, sFace: s.m1, tFace: t.m0,
      sChannel: rightOf(sr),
      tChannel: leftOf(tr),
    };
    if (p.kind === 'loop') {
      // Corridor must clear every rank from the target's up to the source's.
      const lo = Math.min(sr, tr);
      const hi = Math.max(sr, tr);
      const pref = (s.c0 + s.c1 + t.c0 + t.c1) / 4;
      p.corridor = findCorridor(ranks, lo, hi, pref, margin);
      p.corridorKey = `${lo}-${hi}:${Math.round(p.corridor[0])}`;
    } else if (p.kind === 'span') {
      const pref = ((s.c0 + s.c1) / 2 + (t.c0 + t.c1) / 2) / 2;
      p.corridor = findCorridor(ranks, sr + 1, tr - 1, pref, margin);
      p.corridorKey = `${sr + 1}-${tr - 1}:${Math.round(p.corridor[0])}`;
    }
    planned.push(p);
    if (!outPorts.has(s.id)) outPorts.set(s.id, []);
    outPorts.get(s.id)!.push(p);
    if (!inPorts.has(t.id)) inPorts.set(t.id, []);
    inPorts.get(t.id)!.push(p);
  }

  // ── Ports: fan out along the face, ordered by where the edge is headed ──
  const spread = (band: [number, number], base: number, n: number, i: number) => {
    const [b0, b1] = band;
    if (n === 1) return base + (b0 + b1) / 2;
    return base + b0 + ((b1 - b0) * i) / (n - 1);
  };
  for (const [nid, list] of outPorts) {
    const node = byId.get(nid)!;
    const sorted = [...list].sort((a, b) => {
      const ta = byId.get(a.tId)!;
      const tb = byId.get(b.tId)!;
      return (ta.c0 + ta.c1) - (tb.c0 + tb.c1) || a.id.localeCompare(b.id);
    });
    sorted.forEach((p, i) => { p.sPort = spread(portBand, node.c0, sorted.length, i); });
  }
  for (const [nid, list] of inPorts) {
    const node = byId.get(nid)!;
    const sorted = [...list].sort((a, b) => {
      const sa = byId.get(a.sId)!;
      const sb = byId.get(b.sId)!;
      return (sa.c0 + sa.c1) - (sb.c0 + sb.c1) || a.id.localeCompare(b.id);
    });
    sorted.forEach((p, i) => { p.tPort = spread(portBand, node.c0, sorted.length, i); });
  }

  // ── Corridors: separate parallel long runs sharing a gap ────────────────
  const corridorGroups = new Map<string, PlannedEdge[]>();
  for (const p of planned) {
    if (!p.corridorKey) continue;
    if (!corridorGroups.has(p.corridorKey)) corridorGroups.set(p.corridorKey, []);
    corridorGroups.get(p.corridorKey)!.push(p);
  }
  for (const group of corridorGroups.values()) {
    const segs = group.map((p) => {
      const lo = Math.min(p.sFace, p.tFace);
      const hi = Math.max(p.sFace, p.tFace);
      return { lo, hi };
    });
    const { lanes, count } = assignLanes(segs);
    group.forEach((p, i) => {
      const [g0, g1] = p.corridor!;
      const mid = (g0 + g1) / 2;
      const c = mid + (lanes[i] - (count - 1) / 2) * runGap;
      p.runC = Math.min(Math.max(c, g0 + 5), g1 - 5);
    });
  }

  // ── Channels: lane-assign every vertical run ────────────────────────────
  interface VSeg { p: PlannedEdge; which: 'single' | 's' | 't'; lo: number; hi: number }
  const channelSegs = new Map<number, VSeg[]>();
  const addSeg = (ch: number, seg: VSeg) => {
    if (!channelSegs.has(ch)) channelSegs.set(ch, []);
    channelSegs.get(ch)!.push(seg);
  };
  for (const p of planned) {
    if (p.kind === 'adjacent') {
      addSeg(p.sChannel, { p, which: 'single', lo: Math.min(p.sPort, p.tPort), hi: Math.max(p.sPort, p.tPort) });
    } else {
      addSeg(p.sChannel, { p, which: 's', lo: Math.min(p.sPort, p.runC!), hi: Math.max(p.sPort, p.runC!) });
      addSeg(p.tChannel, { p, which: 't', lo: Math.min(p.tPort, p.runC!), hi: Math.max(p.tPort, p.runC!) });
    }
  }
  for (const [ch, segs] of channelSegs) {
    const { lanes, count } = assignLanes(segs);
    const { m0, m1 } = channels[ch];
    const mid = (m0 + m1) / 2;
    segs.forEach((seg, i) => {
      const m = Math.min(Math.max(mid + (lanes[i] - (count - 1) / 2) * laneGap, m0 + 6), m1 - 6);
      if (seg.which === 'single') seg.p.laneM = m;
      else if (seg.which === 's') seg.p.sLaneM = m;
      else seg.p.tLaneM = m;
    });
  }

  // ── Emit polylines ──────────────────────────────────────────────────────
  const push = (pts: [number, number][], m: number, c: number) => {
    const last = pts[pts.length - 1];
    if (last && Math.abs(last[0] - m) < 0.5 && Math.abs(last[1] - c) < 0.5) return;
    pts.push([m, c]);
  };
  for (const p of planned) {
    const pts: [number, number][] = [];
    push(pts, p.sFace, p.sPort);
    if (p.kind === 'adjacent') {
      push(pts, p.laneM!, p.sPort);
      push(pts, p.laneM!, p.tPort);
    } else {
      push(pts, p.sLaneM!, p.sPort);
      push(pts, p.sLaneM!, p.runC!);
      push(pts, p.tLaneM!, p.runC!);
      push(pts, p.tLaneM!, p.tPort);
    }
    push(pts, p.tFace, p.tPort);
    // Drop collinear middles so corners round cleanly.
    const clean: [number, number][] = [];
    for (const pt of pts) {
      const a = clean[clean.length - 2];
      const b = clean[clean.length - 1];
      if (a && b && ((a[0] === b[0] && b[0] === pt[0]) || (a[1] === b[1] && b[1] === pt[1]))) clean.pop();
      clean.push(pt);
    }
    out.set(p.id, clean.map(([m, c]) => fromFlow(m, c, dir)));
  }
  return out;
}

/** Convert a polyline into an SVG path with rounded corners. */
export function roundedPath(pts: Pt[], radius = 10): string {
  if (pts.length === 0) return '';
  if (pts.length === 1) return `M ${pts[0].x},${pts[0].y}`;
  let d = `M ${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const prev = pts[i - 1];
    const cur = pts[i];
    const next = pts[i + 1];
    const inLen = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const outLen = Math.hypot(next.x - cur.x, next.y - cur.y);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    if (r < 0.5) { d += ` L ${cur.x},${cur.y}`; continue; }
    const inX = cur.x - ((cur.x - prev.x) / inLen) * r;
    const inY = cur.y - ((cur.y - prev.y) / inLen) * r;
    const outX = cur.x + ((next.x - cur.x) / outLen) * r;
    const outY = cur.y + ((next.y - cur.y) / outLen) * r;
    d += ` L ${inX},${inY} Q ${cur.x},${cur.y} ${outX},${outY}`;
  }
  const last = pts[pts.length - 1];
  d += ` L ${last.x},${last.y}`;
  return d;
}
