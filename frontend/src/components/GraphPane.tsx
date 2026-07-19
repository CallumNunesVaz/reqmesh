import { useCallback, useEffect, useMemo, useState, useRef, createContext, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type EdgeProps,
  type ReactFlowInstance,
  Panel,
  MarkerType,
  BackgroundVariant,
  EdgeLabelRenderer,
  BaseEdge,
  useInternalNode,
  useStore as useFlowStore,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from 'd3-force';
import { Search, RotateCw, ListTree, Orbit, Boxes, SlidersHorizontal } from 'lucide-react';
import { api, type Requirement, type TraceLink, type EvaluatedRequirement, type EvaluatedParameter, type Component } from '../api/client';
import CircularNode from './CircularNode';
import BlockNode, { BLOCK_W, type BlockParam, type BlockConstraint } from './BlockNode';
import OrthoEdge from './OrthoEdge';
import { routeEdges, type NodeRect } from './orthoRoute';
import LoadingSplash from './LoadingSplash';
import { zoomLevel, LEVEL_LABELS } from './semanticZoom';
import { useTheme } from './ThemeProvider';
import { useSelectedReq } from './Layout';
import { useStore } from '../store';

const edgeColors: Record<string, string> = {
  refines: 'hsl(207,90%,64%)',
  satisfies: 'hsl(145,55%,42%)',
  verified_by: 'hsl(260,100%,78%)',
  derives: 'hsl(28,100%,53%)',
  conflicts: 'hsl(0,84%,68%)',
  duplicates: 'hsl(195,6%,62%)',
  cascades: 'hsl(300,60%,64%)',
};

const componentColors: Record<string, string> = {
  system:    'hsl(207,70%,58%)',
  subsystem: 'hsl(260,55%,62%)',
  assembly:  'hsl(28,65%,58%)',
  part:      'hsl(145,40%,50%)',
  software:  'hsl(180,50%,48%)',
  interface: 'hsl(330,50%,58%)',
};

const statusMinimapColors: Record<string, string> = {
  proposed: '#539fe6',
  approved: '#29ad55',
  implemented: '#b291ff',
  verified: '#009d96',
  rejected: '#ff5d64',
  deprecated: '#95a5a6',
};

// Reserved footprint per block for the layered layout. Height covers the
// tallest semantic-zoom state so compartments never overlap the row below.
const NODE_W = BLOCK_W;
const NODE_H = 118;

const edgeMarkers: Record<string, { markerEnd: MarkerType; strokeDasharray: string; strokeWidth: number }> = {
  refines: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: 'none', strokeWidth: 1.4 },
  satisfies: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: '6,3', strokeWidth: 1.2 },
  verified_by: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: '4,3', strokeWidth: 1.1 },
  derives: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: '6,3', strokeWidth: 1.1 },
  conflicts: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: '2,3', strokeWidth: 1 },
  duplicates: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: 'none', strokeWidth: 0.9 },
  cascades: { markerEnd: MarkerType.ArrowClosed, strokeDasharray: '1,4', strokeWidth: 0.9 },
};

function nodeRadius(childCount: number): number {
  if (childCount <= 1) return 16;
  return Math.min(26, 16 + childCount * 1.5);
}

function computeDepth(nodes: Node[]): Map<string, number> {
  const childrenByParent = new Map<string | null, Node[]>();
  for (const node of nodes) {
    const pid = ((node.data as any).parent as string) || null;
    if (!childrenByParent.has(pid)) childrenByParent.set(pid, []);
    childrenByParent.get(pid)!.push(node);
  }
  const depth = new Map<string, number>();
  function assignDepth(pid: string | null, d: number) {
    for (const child of childrenByParent.get(pid) || []) {
      depth.set(child.id, d);
      assignDepth(child.id, d + 1);
    }
  }
  assignDepth(null, 0);
  return depth;
}

// Deterministic pseudo-random from a string, so layouts are stable per project.
function hashUnit(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 10000) / 10000;
}

// Force-directed layout: hierarchy links pull related nodes together, charge
// pushes unrelated ones apart, and a collision radius (sized for the node
// plus its text label) guarantees nodes never overlap.
function forceLayout(nodes: Node[], edges: Edge[]) {
  if (nodes.length === 0) return nodes;
  const depth = computeDepth(nodes);

  const simNodes = nodes.map((n) => {
    const d = depth.get(n.id) ?? 0;
    const angle = hashUnit(n.id) * Math.PI * 2;
    const ring = 120 + d * 180;
    return {
      id: n.id,
      r: nodeRadius((n.data as any).childCount || 0),
      x: Math.cos(angle) * ring,
      y: Math.sin(angle) * ring,
    };
  });
  const ids = new Set(simNodes.map((n) => n.id));

  // Deduplicate links per node pair; hierarchy links are stronger and shorter
  // than cross-cutting relations so the tree shape dominates.
  const seen = new Set<string>();
  const simLinks: { source: string; target: string; hierarchy: boolean }[] = [];
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    const k = e.source < e.target ? `${e.source}|${e.target}` : `${e.target}|${e.source}`;
    const hierarchy = e.id.endsWith('-parent');
    if (seen.has(k)) continue;
    seen.add(k);
    simLinks.push({ source: e.source, target: e.target, hierarchy });
  }

  const sim = forceSimulation(simNodes as any)
    .force('link', forceLink(simLinks as any)
      .id((d: any) => d.id)
      .distance((l: any) => (l.hierarchy ? 130 : 220))
      .strength((l: any) => (l.hierarchy ? 0.9 : 0.08)))
    .force('charge', forceManyBody().strength(-460))
    .force('collide', forceCollide().radius((d: any) => d.r + 58).strength(1).iterations(3))
    .force('x', forceX(0).strength(0.045))
    .force('y', forceY(0).strength(0.045))
    .stop();

  sim.tick(320);

  const posById = new Map(simNodes.map((n: any) => [n.id, n]));
  return nodes.map((n) => {
    const p: any = posById.get(n.id);
    if (!p) return n;
    const r = nodeRadius((n.data as any).childCount || 0);
    return { ...n, position: { x: p.x - r, y: p.y - r } };
  });
}

// Left-to-right layered layout along the parent hierarchy — much easier to
// read for requirement breakdowns than the radial view.
function hierarchyLayout(nodes: Node[], edges: Edge[], gs: { nodesep: number; ranksep: number; rankdir: string; margin: number }) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: gs.rankdir || 'LR', nodesep: gs.nodesep, ranksep: gs.ranksep, marginx: gs.margin, marginy: gs.margin });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_W + 20, height: NODE_H + 16 });
  }
  for (const e of edges) {
    if (e.id.endsWith('-parent') && g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    if (!pos) return n;
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });
}

// Floating edge: connects the two node circles along the straight line
// between their centers, so arrows enter from the direction of the other
// node instead of a fixed top/bottom handle. Flat single-color stroke.
function FloatingEdge({ id, source, target, data, style, markerEnd }: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  if (!sourceNode || !targetNode) return null;

  const sw = sourceNode.measured?.width ?? 32;
  const tw = targetNode.measured?.width ?? 32;
  const scx = sourceNode.internals.positionAbsolute.x + sw / 2;
  const scy = sourceNode.internals.positionAbsolute.y + (sourceNode.measured?.height ?? 32) / 2;
  const tcx = targetNode.internals.positionAbsolute.x + tw / 2;
  const tcy = targetNode.internals.positionAbsolute.y + (targetNode.measured?.height ?? 32) / 2;

  const dx = tcx - scx;
  const dy = tcy - scy;
  const dist = Math.hypot(dx, dy) || 1;
  const ux = dx / dist;
  const uy = dy / dist;

  // Start/end on the node perimeters (small gap for the arrowhead)
  const sx = scx + ux * (sw / 2 + 1);
  const sy = scy + uy * (sw / 2 + 1);
  const tx = tcx - ux * (tw / 2 + 5);
  const ty = tcy - uy * (tw / 2 + 5);

  // Gentle constant-direction curve so parallel edges don't stack
  const bend = Math.min(dist * 0.12, 40);
  const mx = (sx + tx) / 2 - uy * bend;
  const my = (sy + ty) / 2 + ux * bend;
  const edgePath = `M ${sx},${sy} Q ${mx},${my} ${tx},${ty}`;
  const labelX = 0.25 * sx + 0.5 * mx + 0.25 * tx;
  const labelY = 0.25 * sy + 0.5 * my + 0.25 * ty;

  const edgeColor = (data?.color as string) || (style as any)?.stroke || 'hsl(207,90%,64%)';
  const edgeLabel = (data?.label as string) || '';
  const showLabel = !!(data?.showLabel && edgeLabel);

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{ ...style, stroke: edgeColor, fill: 'none', strokeLinecap: 'round' }}
        markerEnd={markerEnd}
      />
      {showLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <span
              className="text-[9px] font-semibold px-1.5 py-px rounded bg-card border shadow-sm"
              style={{ color: edgeColor, whiteSpace: 'nowrap' }}>
              {edgeLabel}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const edgeTypes = { floating: FloatingEdge, ortho: OrthoEdge };

const blockNodeTypes = { requirementNode: BlockNode };
const circleNodeTypes = { requirementNode: CircularNode };

// Small readout of the current semantic-zoom altitude, so the level jumps
// (structure → blocks → … → full detail) feel intentional rather than glitchy.
function ZoomLevelChip() {
  const level = useFlowStore((s) => zoomLevel(s.transform[2]));
  return (
    <span className="font-mono">
      L{level} &middot; {LEVEL_LABELS[level]}
    </span>
  );
}

interface GraphSelectionCtxValue {
  connectedIds: Set<string>;
  selectedReqId: string | null;
  hasSelection: boolean;
}
export const GraphSelectionCtx = createContext<GraphSelectionCtxValue>({
  connectedIds: new Set(),
  selectedReqId: null,
  hasSelection: false,
});
export function useGraphSelection() { return useContext(GraphSelectionCtx); }

interface GraphPaneProps { projectId: string; compact?: boolean; }

export default function GraphPane({ projectId, compact }: GraphPaneProps) {
  const navigate = useNavigate();
  // ReactFlow defaults to colorMode="light", which stamps a `.light` class on
  // its container and re-scopes our theme CSS variables inside the graph.
  const { theme } = useTheme();
  const [reqs, setReqs] = useState<Requirement[]>([]);
  const [traces, setTraces] = useState<TraceLink[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
  const [showComponents, setShowComponents] = useState(false);
  const [evaluated, setEvaluated] = useState<Map<string, EvaluatedRequirement>>(new Map());

  // Reload choreography: a data reload or layout switch hard-remounts the
  // canvas (new key), which used to flash blank, replay the entrance stagger
  // and jump the camera in full view. Instead the splash blurs the *previous*
  // graph, stays up while the new one mounts, lays out and fits (the settle
  // window), then fades away over the finished diagram.
  const [splash, setSplash] = useState<'on' | 'leaving' | null>('on');
  const splashTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const holdSplash = useCallback(() => {
    splashTimers.current.forEach(clearTimeout);
    splashTimers.current = [];
    setSplash('on');
  }, []);
  const releaseSplash = useCallback((settleMs = 650) => {
    splashTimers.current.forEach(clearTimeout);
    splashTimers.current = [
      setTimeout(() => setSplash('leaving'), settleMs),
      setTimeout(() => setSplash(null), settleMs + 380),
    ];
  }, []);
  useEffect(() => () => splashTimers.current.forEach(clearTimeout), []);
  const [search, setSearch] = useState('');
  const [key, setKey] = useState(0);
  const { selectedReqId, selectReq } = useSelectedReq();
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [entranceDone, setEntranceDone] = useState(false);
  // Fresh storage key: the UML block diagram is the default view for
  // everyone — older sessions' saved 'force'/'tree' preference doesn't carry.
  const [layoutMode, setLayoutMode] = useState<'uml' | 'force'>(() => {
    return localStorage.getItem('rt-graph-layout2') === 'force' ? 'force' : 'uml';
  });

  // Graph layout settings — persisted per project
  const [graphSettings, setGraphSettings] = useState(() => {
    try { return JSON.parse(localStorage.getItem(`rt-graph-settings-${projectId}`) || '{}'); }
    catch { return {}; }
  });
  const gs = { nodesep: 28, ranksep: 150, rankdir: 'LR', maxZoom: 1.1, margin: 50, ...graphSettings };
  const [showSettings, setShowSettings] = useState(false);

  const updateGraphSetting = (key: string, value: any) => {
    setGraphSettings((prev: Record<string, any>) => {
      const next = { ...prev, [key]: value };
      try { localStorage.setItem(`rt-graph-settings-${projectId}`, JSON.stringify(next)); } catch {}
      return next;
    });
  };

  const resetGraphSettings = () => {
    setGraphSettings({});
    try { localStorage.removeItem(`rt-graph-settings-${projectId}`); } catch {}
  };

  const switchLayout = (mode: 'uml' | 'force') => {
    if (mode === layoutMode) return;
    // Same choreography as a reload: blur the old diagram, swap underneath,
    // reveal the re-laid-out one.
    holdSplash();
    localStorage.setItem('rt-graph-layout2', mode);
    setLayoutMode(mode);
    releaseSplash();
  };

  const loadData = useCallback(() => {
    holdSplash();
    Promise.all([
      api.listRequirements(projectId),
      api.getTraces(projectId),
      api.getEvaluation(projectId).catch(() => null),
      api.listComponents(projectId).catch(() => ({ items: [], total: 0 })),
    ]).then(([requirements, traceData, evaluation, compData]) => {
      setReqs(requirements); setTraces(traceData.links || []);
      setComponents((compData as any).items || []);
      setEvaluated(new Map((evaluation?.requirements ?? []).map((er) => [er.id, er])));
      setKey(k => k + 1); setEntranceDone(false);
      releaseSplash();
    }).catch((err) => {
      console.error(err);
      releaseSplash(150);
    });
  }, [projectId, holdSplash, releaseSplash]);

  useEffect(() => { loadData(); }, [loadData]);

  // Reactively reload graph when requirements are mutated elsewhere.
  const graphVersion = useStore((s) => s.graphVersion);
  const prevGraphVersion = useRef(graphVersion);
  useEffect(() => {
    if (graphVersion !== prevGraphVersion.current) {
      prevGraphVersion.current = graphVersion;
      loadData();
    }
  }, [graphVersion, loadData]);

  const filteredReqs = useMemo(() => {
    if (!search) return reqs;
    const q = search.toLowerCase();
    return reqs.filter(r => r.id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
  }, [reqs, search]);

  const childCounts = useMemo(() => {
    const counts = new Map<string, number>();
    function count(id: string): number {
      let total = 0;
      for (const r of reqs) {
        if (r.parent === id) { total += 1 + count(r.id); }
      }
      counts.set(id, total);
      return total;
    }
    for (const r of reqs) { if (!r.parent) count(r.id); }
    return counts;
  }, [reqs]);

  const visibleNodeIds = useMemo(() => {
    const visible = new Set<string>();
    function collect(id: string) {
      if (collapsed.has(id)) return;
      visible.add(id);
      for (const r of reqs) { if (r.parent === id) collect(r.id); }
    }
    for (const r of reqs) { if (!r.parent) collect(r.id); }
    if (visible.size === 0) reqs.forEach(r => visible.add(r.id));
    return visible;
  }, [reqs, collapsed]);

  const { initialNodes, initialEdges } = useMemo(() => {
    const filteredIds = new Set(filteredReqs.map(r => r.id));
    const visIds = new Set([...visibleNodeIds].filter(id => filteredIds.has(id)));

    const fmt = (v: number) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100));
    const stripHtml = (html: string) =>
      new DOMParser().parseFromString(html || '', 'text/html').body.textContent?.trim() ?? '';

    const nodes: Node[] = filteredReqs.filter(r => visIds.has(r.id)).map(req => {
      // Parametric compartments: prefer evaluated values (derived params get
      // their computed number), fall back to the raw declarations.
      const ev = evaluated.get(req.id);
      const params: BlockParam[] = (ev?.parameters ?? req.parameters ?? []).map((p) => {
        const value = 'value' in p ? p.value : null;
        const unit = p.unit ? ` ${p.unit}` : '';
        return {
          name: p.name,
          display: value != null ? `= ${fmt(value)}${unit}` : p.expr ? `= ${p.expr}` : '= ?',
          derived: !!p.expr,
          measured: (p as EvaluatedParameter).measured !== undefined,
        };
      });
      const constraints: BlockConstraint[] = (ev?.constraints ?? req.constraints ?? []).map((c) => ({
        expr: c.expr,
        status: (c as { status?: string }).status ?? 'none',
      }));
      return {
        id: req.id, type: 'requirementNode', position: { x: 0, y: 0 },
        data: {
          label: req.id, name: req.name || 'Untitled', status: req.status,
          priority: req.priority, type: req.type,
          verified: req.verification_status === 'passed',
          parent: req.parent, cascadeFrom: req.cascade_from,
          hasChildren: reqs.some(r => r.parent === req.id),
          collapsed: collapsed.has(req.id),
          childCount: childCounts.get(req.id) || 0,
          params, constraints,
          verdict: ev && ev.verdict !== 'none' ? ev.verdict : null,
          vcCount: (req.verification_cases ?? []).length,
          desc: stripHtml(req.description).slice(0, 160),
        },
        style: entranceDone ? {} : { opacity: 0, transform: 'scale(0)' },
      };
    });

    const edges: Edge[] = [];
    const seen = new Set<string>();
    const pushEdge = (src: string, tgt: string, typ: string, color: string, label: string) => {
      if (!visIds.has(src) || !visIds.has(tgt)) return;
      const k = `${src}-${tgt}-${typ}`;
      if (seen.has(k)) return; seen.add(k);
      const style = edgeMarkers[typ] || { markerEnd: MarkerType.ArrowClosed, strokeDasharray: 'none', strokeWidth: 1 };
      edges.push({
        id: k, source: src, target: tgt, type: 'floating',
        data: { color, label },
        style: { stroke: color, strokeWidth: style.strokeWidth, strokeDasharray: style.strokeDasharray, opacity: 0.45 },
        markerEnd: { type: style.markerEnd, color, width: 14, height: 14 },
      });
    };

    for (const req of reqs) {
      if (!visIds.has(req.id)) continue;
      for (const rel of req.relations || []) {
        pushEdge(req.id, rel.target, rel.type, edgeColors[rel.type] || '#64748b', rel.type);
      }
    }
    for (const link of traces) {
      pushEdge(link.source, link.target, link.type, edgeColors[link.type] || '#64748b', link.type);
    }
    for (const req of reqs) {
      if (!req.cascade_from) continue;
      pushEdge(req.cascade_from, req.id, 'cascades', edgeColors.cascades, 'cascade');
    }
    for (const req of reqs) {
      if (!req.parent) continue;
      // Parent edges: solid line, diamond-style composition marker
      const pk = `${req.parent}-${req.id}-parent`;
      if (seen.has(pk)) continue; seen.add(pk);
      edges.push({
        id: pk, source: req.parent, target: req.id, type: 'floating',
        data: { color: 'hsl(var(--muted-foreground) / 0.3)', label: '' },
        style: { stroke: 'hsl(var(--muted-foreground) / 0.3)', strokeWidth: 0.8, strokeDasharray: 'none', opacity: 0.35 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'hsl(var(--muted-foreground) / 0.3)', width: 12, height: 12 },
      });
    }

    // ── Component nodes & edges (when toggled on) ──────────────────────────
    if (showComponents) {
      const compColor = (type: string) => componentColors[type] || 'hsl(var(--muted-foreground))';
      const filteredComps = search
        ? components.filter(c => c.id.toLowerCase().includes(search.toLowerCase()) || c.name.toLowerCase().includes(search.toLowerCase()))
        : components;

      for (const comp of filteredComps) {
        nodes.push({
          id: `comp:${comp.id}`, type: 'requirementNode', position: { x: 0, y: 0 },
          data: {
            label: comp.id, name: comp.name || 'Untitled', status: 'component',
            priority: 'medium', type: comp.type,
            verified: false, parent: comp.parent ? `comp:${comp.parent}` : null,
            hasChildren: false, collapsed: false, childCount: 0,
            params: (comp.parameters || []).map((p: any) => ({
              name: p.name, display: p.value != null ? `= ${p.value} ${p.unit || ''}` : '= ?',
              derived: !!p.expr, measured: false,
            })),
            constraints: [], verdict: null, vcCount: 0,
            desc: comp.description || '',
            isComponent: true, compColor: compColor(comp.type),
          },
          style: entranceDone ? {} : { opacity: 0, transform: 'scale(0)' },
        });
      }

      for (const comp of components) {
        const srcId = `comp:${comp.id}`;
        // Parent edges
        if (comp.parent) {
          const pk = `${comp.parent}-${comp.id}-comp-parent`;
          if (!visIds.has(comp.parent) || seen.has(pk)) continue;
          seen.add(pk);
          edges.push({
            id: pk, source: `comp:${comp.parent}`, target: srcId, type: 'floating',
            data: { color: 'hsl(var(--muted-foreground) / 0.25)', label: '' },
            style: { stroke: 'hsl(var(--muted-foreground) / 0.25)', strokeWidth: 0.6, strokeDasharray: '3,3', opacity: 0.25 },
            markerEnd: { type: MarkerType.ArrowClosed, color: 'hsl(var(--muted-foreground) / 0.25)', width: 10, height: 10 },
          });
        }
        // Satisfies edges: component → requirement
        for (const rid of comp.satisfies || []) {
          if (!visIds.has(rid)) continue;
          const sk = `${comp.id}-${rid}-comp-satisfies`;
          if (seen.has(sk)) continue; seen.add(sk);
          edges.push({
            id: sk, source: srcId, target: rid, type: 'floating',
            data: { color: edgeColors.satisfies, label: 'satisfies' },
            style: { stroke: edgeColors.satisfies, strokeWidth: 1.2, strokeDasharray: '6,3', opacity: 0.40 },
            markerEnd: { type: MarkerType.ArrowClosed, color: edgeColors.satisfies, width: 14, height: 14 },
          });
        }
        // Component-to-component relations
        for (const rel of comp.relations || []) {
          const rk = `${comp.id}-${rel.target}-comp-rel-${rel.type}`;
          if (seen.has(rk)) continue; seen.add(rk);
          edges.push({
            id: rk, source: srcId, target: `comp:${rel.target}`, type: 'floating',
            data: { color: edgeColors[rel.type] || '#64748b', label: rel.type },
            style: { stroke: edgeColors[rel.type] || '#64748b', strokeWidth: 1, strokeDasharray: '4,3', opacity: 0.35 },
            markerEnd: { type: MarkerType.ArrowClosed, color: edgeColors[rel.type] || '#64748b', width: 12, height: 12 },
          });
        }
      }
    }

    return { initialNodes: nodes, initialEdges: edges };
  }, [reqs, filteredReqs, traces, visibleNodeIds, childCounts, collapsed, entranceDone, evaluated, components, showComponents, search]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const rfRef = useRef<ReactFlowInstance | null>(null);

  useEffect(() => {
    const laid = layoutMode === 'uml'
      ? hierarchyLayout(initialNodes, initialEdges, gs)
      : forceLayout(initialNodes, initialEdges);
    setNodes(laid);
    // UML mode plans all edges together with the orthogonal router: ports fan
    // out along block faces, parallel runs get separate lanes, and long or
    // backward edges travel corridors that stay clear of intervening blocks.
    // Force mode keeps floating centre-to-centre edges.
    if (layoutMode === 'uml') {
      const rects: NodeRect[] = laid.map((n) => ({
        id: n.id, x: n.position.x, y: n.position.y, w: NODE_W, h: NODE_H,
      }));
      const vertical = gs.rankdir === 'TB' || gs.rankdir === 'BT';
      const routes = routeEdges(
        rects,
        initialEdges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
        {
          rankdir: gs.rankdir,
          // Fan ports across the block width when flow is vertical; on the
          // side faces stay within the height every zoom level guarantees.
          portBand: vertical ? [28, NODE_W - 28] : [12, 44],
        },
      );
      setEdges(initialEdges.map((e) => {
        // Composition (parent) edges carry the diagram's structure, so in
        // block-diagram mode they read stronger than the relation overlays.
        const isParent = e.id.endsWith('-parent');
        return {
          ...e,
          type: 'ortho',
          data: { ...e.data, points: routes.get(e.id) },
          style: {
            ...(e.style as Record<string, unknown>),
            ...(isParent
              ? { stroke: 'hsl(var(--muted-foreground) / 0.55)', strokeWidth: 1.4, opacity: 0.7 }
              : { opacity: 0.55 }),
          },
        };
      }));
    } else {
      setEdges(initialEdges);
    }
    selectReq(null);
    // Re-fit once the laid-out nodes have rendered and been measured.
    const t = setTimeout(() => rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom }), 250);
    return () => clearTimeout(t);
  }, [initialNodes, initialEdges, layoutMode, gs.nodesep, gs.ranksep, gs.rankdir, gs.margin, gs.maxZoom, setNodes, setEdges]);

  useEffect(() => {
    if (!entranceDone && nodes.length > 0) {
      const timer = setTimeout(() => {
        setNodes(nds => nds.map((n, i) => ({
          ...n,
          style: { ...(n.style || {}), opacity: 1, transform: 'scale(1)', transition: `all 0.3s ease-out ${Math.min(i * 6, 400)}ms` },
        })));
        setEntranceDone(true);
      }, 80);
      return () => clearTimeout(timer);
    }
  }, [entranceDone, nodes.length]);

  // When selection changes externally (nav click, etc.), smoothly fit view.
  const prevSelectedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!entranceDone || !selectedReqId || selectedReqId === prevSelectedRef.current) return;
    prevSelectedRef.current = selectedReqId;
    // Single-frame delay so dimmed node states commit before camera moves.
    const raf = requestAnimationFrame(() => {
      const hasChildren = reqs.some(r => r.parent === selectedReqId);
      if (hasChildren) {
        const descendants = new Set<string>();
        const collect = (id: string) => {
          descendants.add(id);
          for (const r of reqs) { if (r.parent === id) collect(r.id); }
        };
        collect(selectedReqId);
        const subsetNodes = nodes.filter(n => descendants.has(n.id));
        if (subsetNodes.length > 0) {
          rfRef.current?.fitView({ nodes: subsetNodes, padding: 0.25, duration: 600, maxZoom: gs.maxZoom });
        }
      } else {
        const related = new Set<string>([selectedReqId]);
        for (const e of initialEdges) {
          if (e.source === selectedReqId) related.add(e.target);
          if (e.target === selectedReqId) related.add(e.source);
        }
        const subsetNodes = nodes.filter(n => related.has(n.id));
        if (subsetNodes.length > 0) {
          rfRef.current?.fitView({ nodes: subsetNodes, padding: 0.3, duration: 600, maxZoom: gs.maxZoom });
        }
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [selectedReqId, entranceDone]);

  const connectedIds = useMemo(() => {
    const highlightId = selectedReqId || hoveredNodeId;
    if (!highlightId) return new Set<string>();
    const connected = new Set<string>([highlightId]);
    for (const edge of initialEdges) {
      if (edge.source === highlightId) connected.add(edge.target);
      if (edge.target === highlightId) connected.add(edge.source);
    }
    return connected;
  }, [selectedReqId, hoveredNodeId, initialEdges]);

  const hasSelection = !!(selectedReqId || hoveredNodeId);

  const dimmedEdges = useMemo(() => {
    if (!hasSelection) return edges;
    return edges.map((e) => {
      const connected = e.source === selectedReqId || e.target === selectedReqId ||
        e.source === hoveredNodeId || e.target === hoveredNodeId;
      const stroke = (e.style as any)?.stroke as string | undefined;
      const dashed = ((e.style as any)?.strokeDasharray ?? 'none') !== 'none';
      return {
        ...e,
        data: { ...e.data, showLabel: connected },
        // Highlighted dashed relations drift slowly along their direction.
        className: connected && dashed ? 'rt-drift' : undefined,
        style: {
          ...((e.style as Record<string, any>) || {}),
          opacity: connected ? Math.max((e.style as any)?.opacity || 0.55, 0.9) : 0.04,
          // A hint of bloom on active edges — just enough to trace them.
          filter: connected && stroke ? `drop-shadow(0 0 2px ${stroke})` : undefined,
        },
      };
    });
  }, [edges, hasSelection, selectedReqId, hoveredNodeId]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (selectedReqId === node.id) navigate(`/project/${projectId}/requirements/${node.id}`);
      else { selectReq(node.id); setHoveredNodeId(null); }
    },
    [navigate, projectId, selectedReqId, selectReq],
  );

  const onNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if ((node.data as any).isComponent) {
        const compId = node.id.startsWith('comp:') ? node.id.slice(5) : node.id;
        navigate(`/project/${projectId}/components/${compId}`);
        return;
      }
      if ((node.data as any).hasChildren) {
        setCollapsed(prev => { const next = new Set(prev); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; });
      }
    },
    [navigate, projectId],
  );

  const onPaneClick = useCallback(() => { selectReq(null); setHoveredNodeId(null); }, [selectReq]);
  const handleNodeEnter = useCallback((_: React.MouseEvent, node: Node) => {
    if (!selectedReqId) setHoveredNodeId(node.id);
  }, [selectedReqId]);
  const handleNodeLeave = useCallback(() => { setHoveredNodeId(null); }, []);

  return (
    <div
      className="w-full h-full bg-background relative"
      // Subtle centre glow for depth so node blooms read against some atmosphere.
      // ReactFlow is transparent, so this backdrop shows through behind the nodes.
      style={{ background: 'radial-gradient(ellipse at 50% 38%, hsl(var(--foreground) / 0.035), transparent 62%), hsl(var(--background))' }}
    >
    {/* The remount key lives on this inner wrapper, NOT the outer div: the
        splash must survive the swap so the old diagram fades straight into
        the new one with no uncovered frame in between. */}
    <div className="w-full h-full" key={`${key}-${layoutMode}`}>
    <GraphSelectionCtx.Provider value={{ connectedIds, selectedReqId, hasSelection }}>
      <ReactFlow
        nodes={nodes}
        edges={dimmedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeMouseEnter={handleNodeEnter}
        onNodeMouseLeave={handleNodeLeave}
        onPaneClick={onPaneClick}
        onInit={(inst) => { rfRef.current = inst; }}
        colorMode={theme}
        nodeTypes={layoutMode === 'uml' ? blockNodeTypes : circleNodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3, minZoom: 0.3, maxZoom: gs.maxZoom }}
        minZoom={0.15}
        maxZoom={2.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'floating' }}
        defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
        style={{ background: 'transparent' }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={0.3} color="hsl(var(--border) / 0.2)" />

        {/* Loose, rounded buttons that speak the same language as the search
            and layout panels — the default is a hard-edged welded strip. */}
        <Controls
          className="!shadow-none !bg-transparent [&_button]:!bg-graph-panel [&_button]:!border [&_button]:!border-graph-border [&_button]:!text-graph-text [&_button]:!rounded-lg [&_button]:!mb-1 [&_button]:!shadow-sm [&_button]:hover:!bg-graph-control-hover [&_button_svg]:!fill-graph-text"
          showZoom showFitView showInteractive={false}
        />

        <MiniMap
          nodeColor={(node) => statusMinimapColors[(node.data?.status as string) || 'proposed'] || '#64748b'}
          bgColor="hsl(var(--graph-minimap))"
          maskColor="hsl(var(--graph-minimap) / 0.9)"
          className="!bg-graph-minimap !border-graph-border rounded-lg overflow-hidden shadow-lg"
          nodeBorderRadius={3} pannable zoomable
        />

        <Panel position="top-left" className="ml-2 mt-2 flex items-center gap-2">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-graph-muted" />
            <input
              className="pl-7 pr-2.5 py-1.5 w-44 rounded-lg bg-graph-panel border border-graph-border text-xs text-graph-text placeholder:text-graph-muted outline-none focus:ring-1 focus:ring-ring/20 transition-all shadow-sm"
              placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex rounded-lg bg-graph-panel border border-graph-border shadow-sm overflow-hidden">
            <button
              onClick={() => switchLayout('uml')}
              className={`p-1.5 transition-colors ${layoutMode === 'uml' ? 'bg-primary text-primary-foreground' : 'text-graph-text hover:bg-graph-control-hover'}`}
              title="UML block diagram"
            >
              <ListTree size={13} />
            </button>
            <button
              onClick={() => switchLayout('force')}
              className={`p-1.5 transition-colors ${layoutMode === 'force' ? 'bg-primary text-primary-foreground' : 'text-graph-text hover:bg-graph-control-hover'}`}
              title="Force-directed layout"
            >
              <Orbit size={13} />
            </button>
          </div>
          <div className="relative">
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`p-1.5 rounded-lg border shadow-sm transition-all ${
                showSettings || Object.keys(graphSettings).length > 0
                  ? 'bg-accent text-foreground border-graph-border'
                  : 'bg-graph-panel border-graph-border text-graph-text hover:bg-graph-control-hover'
              }`}
              title="Graph layout settings"
            >
              <SlidersHorizontal size={13} />
            </button>
            {showSettings && (
              <div className="absolute top-full left-0 mt-1.5 z-50 w-64 rounded-xl bg-graph-panel border border-graph-border shadow-2xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-semibold text-graph-text uppercase tracking-wider">Layout Settings</span>
                  <button onClick={() => setShowSettings(false)} className="text-graph-muted hover:text-graph-text">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                </div>
                <div className="space-y-3">
                  {/* Rank direction */}
                  <div>
                    <div className="text-[9px] text-graph-muted mb-1.5">Direction</div>
                    <div className="grid grid-cols-4 gap-1">
                      {(['LR','TB','RL','BT'] as const).map(d => (
                        <button key={d} onClick={() => updateGraphSetting('rankdir', d)}
                          className={`text-[10px] py-1 rounded font-mono border transition-colors ${
                            gs.rankdir === d ? 'bg-primary/20 text-primary border-primary/30' : 'border-graph-border text-graph-text hover:bg-graph-control-hover'
                          }`}>{d}</button>
                      ))}
                    </div>
                  </div>
                  {/* Sliders */}
                  {[
                    { key: 'nodesep', label: 'Node Spacing', min: 8, max: 60, val: gs.nodesep },
                    { key: 'ranksep', label: 'Rank Spacing', min: 60, max: 400, val: gs.ranksep },
                    { key: 'maxZoom', label: 'Max Zoom', min: 0.5, max: 5, step: 0.1, val: gs.maxZoom },
                    { key: 'margin', label: 'Margin', min: 10, max: 200, val: gs.margin },
                  ].map(({ key, label, min, max, step, val }) => (
                    <div key={key}>
                      <div className="flex justify-between text-[9px] mb-1">
                        <span className="text-graph-muted">{label}</span>
                        <span className="text-graph-text font-mono">{typeof val === 'number' ? Math.round(val * 10) / 10 : val}</span>
                      </div>
                      <input type="range" min={min} max={max} step={step || 1} value={val}
                        onChange={(e) => updateGraphSetting(key, step ? parseFloat(e.target.value) : parseInt(e.target.value))}
                        className="w-full h-1.5 rounded-full appearance-none bg-graph-border cursor-pointer
                          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
                          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-sm"
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-graph-border">
                  <button onClick={resetGraphSettings}
                    className="w-full text-[10px] text-graph-muted hover:text-graph-text hover:bg-graph-control-hover rounded py-1 transition-colors">
                    Reset to defaults
                  </button>
                </div>
              </div>
            )}
          </div>
          <button
            onClick={() => setShowComponents(!showComponents)}
            className={`p-1.5 rounded-lg border shadow-sm transition-all ${
              showComponents
                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                : 'bg-graph-panel border-graph-border text-graph-text hover:bg-graph-control-hover'
            }`}
            title={showComponents ? 'Components visible — click to hide' : 'Show components in graph'}
          >
            <Boxes size={13} />
          </button>
          <button onClick={loadData} className="p-1.5 rounded-lg bg-graph-panel border border-graph-border text-graph-text hover:text-foreground hover:bg-graph-control-hover transition-colors shadow-sm" title="Refresh">
            <RotateCw size={13} />
          </button>
        </Panel>

        <Panel position="top-right" className="mr-2 mt-2">
          <div className="rounded-lg bg-graph-panel/85 border border-graph-border px-2.5 py-1.5 shadow-sm opacity-75 hover:opacity-100 transition-opacity">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-graph-muted mb-1">Relations</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {Object.entries(edgeColors).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1.5 text-[10px] text-graph-text">
                  <span className="w-2.5 h-0.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <span>{type.replace('_', ' ')}</span>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel position="bottom-center" className="mb-3">
          <div className="text-[10px] text-graph-text bg-graph-panel border border-graph-border rounded-lg px-2.5 py-1.5 shadow-sm flex items-center gap-2">
            {layoutMode === 'uml' && (
              <>
                <ZoomLevelChip />
                <span className="opacity-40">|</span>
              </>
            )}
            <span>{reqs.length} requirements{showComponents ? `, ${components.length} components` : ''} · {initialEdges.length} edges · click to select · dbl-click expand</span>
          </div>
        </Panel>
      </ReactFlow>
      </GraphSelectionCtx.Provider>
      </div>

      {splash && <LoadingSplash label="Loading graph…" leaving={splash === 'leaving'} />}

      <style>{`
        .react-flow__node { font-family: var(--font-sans); }
        .react-flow__edge-path { transition: stroke-opacity 0.2s, opacity 0.25s ease, filter 0.25s ease; }
        .react-flow__edge.rt-drift .react-flow__edge-path {
          animation: rt-dash-drift 22s linear infinite;
        }
        @keyframes rt-dash-drift { to { stroke-dashoffset: -315; } }
        .react-flow__controls-button { width: 24px; height: 24px; }
        .react-flow__background { background-color: transparent !important; }
        .react-flow__minimap { background-color: hsl(var(--graph-minimap)) !important; }
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.5); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
