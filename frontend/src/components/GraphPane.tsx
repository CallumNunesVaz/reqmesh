import { useCallback, useEffect, useMemo, useState, useRef, createContext, useContext, memo } from 'react';
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
import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from 'd3-force';
import { Search, RotateCw, ListTree, Orbit, SlidersHorizontal, ChevronsUpDown, ChevronsDownUp, Filter, Waypoints, Share2, Save, ArrowLeftRight, ArrowDownLeft, ArrowUpRight, EyeOff, GitMerge } from 'lucide-react';
import { api, type Requirement, type TraceLink, type EvaluatedRequirement, type EvaluatedParameter, type Component } from '../api/client';
import CircularNode from './CircularNode';
import BlockNode, { BLOCK_W, STACK_OVERHANG, type BlockParam, type BlockConstraint } from './BlockNode';
import { statusColors } from './RequirementNode';
import OrthoEdge from './OrthoEdge';
import LoadingSplash from './LoadingSplash';
import { zoomLevel, LEVEL_LABELS } from './semanticZoom';
import { useTheme } from './ThemeProvider';
import { useSelectedReq, useContextPane, useHoveredEntity, useHoveredEntityBus } from './Layout';
import { useStore } from '../store';
import { useWhatIf } from './WhatIfContext';
import { requirementVerdict } from '../lib/whatIfVerdict';
import { formatReqType, reqTypeColor } from '../lib/requirementTypes';
import { effectiveHiddenComponents, filterableComponentIds, isReqHiddenByComponents, isReqHiddenByBaselines, migrateLegacyFilterList, requirementsRevealed, pruneUnknownIds } from '../lib/graphFilters';
import { hoistEdges } from '../lib/hoistEdges';
import { requirementsSatisfiedByComponent } from '../lib/crossHighlight';

const edgeColors: Record<string, string> = {
  refines: 'hsl(207,90%,64%)',
  satisfies: 'hsl(145,55%,42%)',
  verified_by: 'hsl(260,100%,78%)',
  derives: 'hsl(28,100%,53%)',
  conflicts: 'hsl(0,84%,68%)',
  duplicates: 'hsl(195,6%,62%)',
  cascades: 'hsl(300,60%,64%)',
};

// ── Filter-option colours ─────────────────────────────────────────────────
// Match the colour language used elsewhere: statuses reuse the canvas node
// status palette; priorities reuse the block priority indicators; types reuse
// the same `cs` palette tokens as the Requirements list (RequirementsPage).
const priorityFilterColors: Record<string, string> = {
  low: 'hsl(195,6%,62%)',
  medium: 'hsl(207,90%,64%)',
  high: 'hsl(28,100%,53%)',
  critical: 'hsl(0,84%,68%)',
};
const verifStatusFilterColors: Record<string, string> = {
  passed: 'hsl(145,55%,42%)',
  failed: 'hsl(0,84%,68%)',
  pending: 'hsl(195,6%,62%)',
  na: 'hsl(195,6%,62%)',
};
const statusOptionColor = (s: string) => statusColors[s]?.text;
const priorityOptionColor = (p: string) => priorityFilterColors[p];
const verifStatusOptionColor = (v: string) => verifStatusFilterColors[v];
const typeOptionColor = (t: string) => reqTypeColor(t);

const statusMinimapColors: Record<string, string> = {
  proposed: '#539fe6',
  approved: '#29ad55',
  implemented: '#b291ff',
  verified: '#009d96',
  rejected: '#ff5d64',
  deprecated: '#95a5a6',
};

// Reserved footprint per block for the layered layout.  Height is enlarged
// dynamically when a node has many edges entering or leaving its left/right
// faces so the orthogonal router's bend points never land outside the node.
const NODE_W = BLOCK_W;
const BASE_NODE_H = 118;
const MIN_EDGE_GAP = 8;  // vertical px between adjacent edge terminals — ELK's
                          // practical minimum with markers is wider than the
                          // spacing option suggests, so set this generously.

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

// Lazy, code-split ELK singleton — keeps the ~1 MB engine out of the main
// chunk and off the critical path until the graph is actually rendered.
let elkInstance: any = null;
async function getElk() {
  if (!elkInstance) {
    const ELK = (await import('elkjs/lib/elk.bundled.js')).default;
    elkInstance = new ELK();
  }
  return elkInstance;
}

const ELK_DIRECTION: Record<string, string> = { LR: 'RIGHT', RL: 'LEFT', TB: 'DOWN', BT: 'UP' };

interface ElkResult {
  positions: Map<string, { x: number; y: number }>;
  edgePoints: Map<string, { x: number; y: number }[]>;
  heights: Map<string, number>;
}

// Layered (Sugiyama) layout via ELK, the algorithm behind Eclipse/SysML
// editors. Unlike the old dagre pass — which ranked on the composition tree
// alone — this feeds BOTH composition and relation edges, so ELK's global
// crossing-minimisation places strongly-related requirements near each other.
// Composition edges are prioritised so the breakdown tree stays dominant.
// ELK also routes the edges orthogonally itself (bend points below), replacing
// the bespoke router. Node footprints stay fixed (NODE_W×NODE_H) on purpose:
// semantic zoom changes real heights, and measured heights would make the
// layout jump — and this way ELK's routing shares the exact rects it laid out.
async function elkLayout(
  nodes: Node[], edges: Edge[],
  gs: { nodesep: number; ranksep: number; rankdir: string; margin: number },
): Promise<ElkResult> {
  const elk = await getElk();
  const nodeIds = new Set(nodes.map((n) => n.id));
  const seen = new Set<string>();
  const elkEdges: any[] = [];
  for (const e of edges) {
    if (e.source === e.target || seen.has(e.id)) continue;
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    seen.add(e.id);
    elkEdges.push({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
      layoutOptions: e.id.endsWith('-parent') ? { 'elk.layered.priority.straightness': '10' } : {},
    });
  }

  // Compute per-node heights so nodes with many edges get enough vertical
  // face real-estate for ELK's orthogonal router to place all terminals.
  const fanIn = new Map<string, number>();
  const fanOut = new Map<string, number>();
  for (const e of elkEdges) {
    fanIn.set(e.targets[0], (fanIn.get(e.targets[0]) || 0) + 1);
    fanOut.set(e.sources[0], (fanOut.get(e.sources[0]) || 0) + 1);
  }
  const edgePad = 52; // ample top+bottom clearance so edge terminals stay
                        // well inside the rounded-rect boundary at every zoom
  const getNodeHeight = (nid: string) => {
    const maxFan = Math.max(fanIn.get(nid) || 0, fanOut.get(nid) || 0);
    return Math.max(
      BASE_NODE_H,
      Math.round(maxFan * MIN_EDGE_GAP + edgePad),
    );
  };

  // Un-inflated (visual) height per node, captured while building the layout
  // boxes so collapsed groups can render at their true size after routing.
  const visualHeight = new Map<string, number>();

  const graph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': ELK_DIRECTION[gs.rankdir] || 'RIGHT',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.spacing.nodeNode': String(gs.nodesep),
      'elk.layered.spacing.nodeNodeBetweenLayers': String(gs.ranksep),
      'elk.spacing.edgeNode': String(Math.max(12, Math.round(gs.nodesep / 2))),
      'elk.spacing.edgeEdge': String(Math.min(4, Math.max(2, Math.round(gs.nodesep / 10)))),
      'elk.spacing.portPort': '4',
      'elk.padding': `[top=${gs.margin},left=${gs.margin},bottom=${gs.margin},right=${gs.margin}]`,
      'elk.layered.cycleBreaking.strategy': 'GREEDY',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    },
    children: nodes.map((n) => {
      const nd = n.data as any;
      const h = getNodeHeight(n.id);
      visualHeight.set(n.id, h);
      // A collapsed group draws a card stack peeking past its bottom-right
      // corner. Inflate its *layout* box by that overhang (right + bottom) so
      // ELK keeps other nodes and routed edges clear of the stack. The rendered
      // node stays BLOCK_W × h — only the reserved footprint grows.
      const overhang = nd?.hasChildren && nd?.collapsed ? STACK_OVERHANG : 0;
      return { id: n.id, width: NODE_W + overhang, height: h + overhang };
    }),
    edges: elkEdges,
  };
  const res = await elk.layout(graph);
  const positions = new Map<string, { x: number; y: number }>();
  const heights = new Map<string, number>();
  for (const c of res.children || []) {
    positions.set(c.id, { x: c.x ?? 0, y: c.y ?? 0 });
    // Store the un-inflated visual height so the node renders at its true size.
    heights.set(c.id, visualHeight.get(c.id) ?? BASE_NODE_H);
  }
  const edgePoints = new Map<string, { x: number; y: number }[]>();
  for (const e of res.edges || []) {
    const pts: { x: number; y: number }[] = [];
    for (const sec of e.sections || []) {
      pts.push(sec.startPoint);
      for (const bp of sec.bendPoints || []) pts.push(bp);
      pts.push(sec.endPoint);
    }
    if (pts.length) edgePoints.set(e.id, pts);
  }
  return { positions, edgePoints, heights };
}

// Floating edge: connects the two node circles along the straight line
// between their centers, so arrows enter from the direction of the other
// node instead of a fixed top/bottom handle. Flat single-color stroke.
function FloatingEdge({ id, source, target, data, style, markerEnd }: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const { selectedReqId } = useGraphSelection();
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
  const hoisted = !!data?.hoisted;
  const count = (data?.count as number) || 1;
  const showLabel = !!(data?.showLabel && edgeLabel && !(hoisted && count > 1));

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{ ...style, stroke: edgeColor, fill: 'none', strokeLinecap: 'round' }}
        markerEnd={markerEnd}
        interactionWidth={selectedReqId ? 20 : 0}
      />
      {hoisted && count > 1 && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'none',
            }}
            className="nodrag nopan"
          >
            <span
              className="text-[9px] font-semibold px-1.5 py-px rounded-full bg-graph-panel border border-graph-border shadow-sm"
              style={{ color: edgeColor, whiteSpace: 'nowrap' }}
              title={`${count} relationships`}
            >
              &times;{count}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
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

// memo: edge components re-render whenever the edges array is rebuilt (every
// selection/hover restyle). Unchanged edges should bail out, not re-derive
// their geometry.
const edgeTypes = { floating: memo(FloatingEdge), ortho: OrthoEdge };

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

// A snapshot of the full graph view a user can save to a slot and jump back to:
// expansion state, focus, layout mode + settings, highlight controls, filters,
// and the exact camera. Persisted per project in localStorage.
interface SavedView {
  collapsed: string[];
  groupsOnly?: string[];
  selectedReqId: string | null;
  layoutMode: 'uml' | 'force';
  graphSettings: Record<string, any>;
  hopDepth: number;
  showAllLinks: boolean;
  linkDir?: LinkDir;
  filters: {
    search: string; status: string; priority: string; type: string;
    verStatus: string; verMethod: string; allocated: string;
    hiddenBaselines?: string[]; hiddenComponents?: string[];
    /** Legacy include-lists from before visibility was inverted; still read so
     *  saved views written earlier restore with their original meaning. */
    baselines?: string[]; components?: string[];
    /** Removed with requirement_kind; still read so saved views written before
     *  that stay loadable instead of failing to restore. */
    kind?: string;
  };
  viewport: { x: number; y: number; zoom: number } | null;
}
const VIEW_SLOTS = 3;

/** Which way the highlight walks out from the focused node. */
type LinkDir = 'both' | 'in' | 'out';

// Plain-text cache for HTML descriptions (see stripHtml in the node build).
const stripHtmlCache = new Map<string, string>();

// Above this many visible nodes the canvas drops to performance mode:
// viewport culling on, per-node glow filters / infinite animations off, hover
// neighbourhood highlighting off (click still highlights), minimap off. The
// cost that matters at scale is paint (drop-shadows defeat GPU compositing)
// and the all-node re-render a hover triggers — both are gated here.
const PERF_NODE_LIMIT = 100;

interface GraphPaneProps { projectId: string; }

export default function GraphPane({ projectId }: GraphPaneProps) {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const whatIf = useWhatIf();
  const [reqs, setReqs] = useState<Requirement[]>([]);
  const [traces, setTraces] = useState<TraceLink[]>([]);
  const [components, setComponents] = useState<Component[]>([]);
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
  const [filterStatus, setFilterStatus] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterVerStatus, setFilterVerStatus] = useState('');
  const [filterVerMethod, setFilterVerMethod] = useState('');
  const [filterAllocated, setFilterAllocated] = useState('');

  const hiddenBaselines = useStore((s) => s.hiddenBaselines);
  const setHiddenBaselines = useStore((s) => s.setHiddenBaselines);
  const toggleHiddenBaseline = useStore((s) => s.toggleHiddenBaseline);
  const hiddenComponents = useStore((s) => s.hiddenComponents);
  const toggleHiddenComponent = useStore((s) => s.toggleHiddenComponent);
  const setHiddenComponents = useStore((s) => s.setHiddenComponents);
  const [showFilters, setShowFilters] = useState(false);
  const [hideRoots, setHideRoots] = useState(false);
  const { selectedReqId, selectReq, derivationReq } = useSelectedReq();
  const { openContext } = useContextPane();
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  // Shared hover (canvas ↔ list). `hoveredEntity` re-renders only this pane on
  // a hover change; `setHoveredEntity` is the stable bus setter.
  const hoveredEntity = useHoveredEntity();
  const { set: setHoveredEntity } = useHoveredEntityBus();
  // How many relationship hops out from the focused node stay highlighted.
  const [hopDepth, setHopDepth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-graph-hop-depth') || '', 10);
    return saved >= 1 && saved <= 3 ? saved : 1;
  });
  const setHopDepthPersist = useCallback((n: number) => {
    setHopDepth(n);
    try { localStorage.setItem('rt-graph-hop-depth', String(n)); } catch {}
  }, []);
  // When on, light up *every* relationship among the highlighted nodes —
  // including cross-links between same-distance neighbours (e.g. two children
  // of the focus that also relate to each other), not just the radial paths
  // that fan out from the focused node.
  const [showAllLinks, setShowAllLinks] = useState(() => localStorage.getItem('rt-graph-all-links') === '1');
  const toggleAllLinks = useCallback(() => {
    setShowAllLinks((v) => {
      const next = !v;
      try { localStorage.setItem('rt-graph-all-links', next ? '1' : '0'); } catch {}
      return next;
    });
  }, []);
  // Which way the highlight walks from the focused node: both directions
  // (default), only links arriving at it, or only links leaving it.
  const [linkDir, setLinkDir] = useState<LinkDir>(() => {
    const saved = localStorage.getItem('rt-graph-link-dir');
    return saved === 'in' || saved === 'out' ? saved : 'both';
  });
  const setLinkDirPersist = useCallback((d: LinkDir) => {
    setLinkDir(d);
    try { localStorage.setItem('rt-graph-link-dir', d); } catch {}
  }, []);

  // "Show derivation" (driven from the requirement inspector): the transitive
  // closure of everything feeding into a requirement. Overrides the normal
  // hop-radius highlight until the selection changes.
  const [derived, setDerived] = useState<{ root: string; ids: Set<string> } | null>(null);
  // Set while a trace's expansion is settling, so the expand choreography
  // doesn't grab the selection/camera out from under it.
  const derivingRef = useRef(false);

  // Saved view slots (persisted per project) and a nonce that forces the layout
  // effect to re-run on restore even when nothing it depends on changed.
  const [views, setViews] = useState<(SavedView | null)[]>(() => {
    try {
      const raw = JSON.parse(localStorage.getItem(`rt-graph-views-${projectId}`) || 'null');
      if (Array.isArray(raw)) return Array.from({ length: VIEW_SLOTS }, (_, i) => raw[i] ?? null);
    } catch { /* ignore malformed */ }
    return Array(VIEW_SLOTS).fill(null);
  });
  const [layoutNonce, setLayoutNonce] = useState(0);
  // Set just before a restore triggers a relayout; consumed by the layout effect
  // to apply the saved focus + camera without the usual auto-fit fighting it.
  const restoreRef = useRef<{ viewport: SavedView['viewport']; selectedReqId: string | null } | null>(null);
  // Camera to apply after the next relayout when it isn't an auto-fit: a node id
  // to re-frame, '*' to fit everything, or null. Set by a layout-mode switch or
  // a collapse (single node / all) so the selection stays in view — mirroring
  // how expanding re-frames the node it opened.
  //: A pending camera intent, applied by `applyRefocus` once the relayout has
  //: put every node at its final position. A node id frames that node and its
  //: neighbours; `'*'` fits everything; `{ expand }` widens the current view to
  //: also take in the listed nodes.
  //:
  //: Everything that wants the camera goes through here rather than calling
  //: `fitView` directly. A component reveal that ran its own fit did work — and
  //: was then overridden three times by the fits already scheduled in this
  //: pipeline, leaving the requirements it had just framed off screen.
  const refocusRef = useRef<string | { expand: string[] } | null>(null);
  //: Set when an `{ expand }` refocus has just framed something deliberately.
  //: A reveal provokes a *second* relayout pass, and that pass finds `refocus`
  //: already consumed, falls through to its blanket "fit everything", and
  //: throws away the framing — measured, the requirements were correctly in
  //: shot and then gone again about a second later. The reveal keeps the camera
  //: until the user asks for something else.
  const suppressRefitRef = useRef(false);
  //: Claim the camera for the framing just applied, mirroring how a derivation
  //: trace claims it via `derivingRef`. Self-limiting: a reveal owns the camera
  //: for the relayouts it provokes, never indefinitely.
  const claimCamera = () => {
    suppressRefitRef.current = true;
    window.setTimeout(() => { suppressRefitRef.current = false; }, 1500);
  };
  // True while a layout-mode switch is being laid out, so the layout effect
  // releases the splash on completion (ELK can outlast any fixed timer) rather
  // than on a fixed delay.
  const switchingRef = useRef(false);
  // Declared here (not by the selection-fit effect) so a restore can pre-seed it
  // and stop that effect from re-framing the camera it just positioned.
  const prevSelectedRef = useRef<string | null>(null);
  const animatingRef = useRef(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Nodes expanded in "groups-only" mode: their leaf children stay hidden and
  // only the children that are themselves parents (subgroups) are revealed.
  const [groupsOnly, setGroupsOnly] = useState<Set<string>>(new Set());
  const [autoCollapsed, setAutoCollapsed] = useState(false);
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

  // Hoisted edges: a relationship whose endpoint is hidden by a collapsed group
  // is redrawn to the nearest visible ancestor instead of disappearing. Lived
  // in `graphSettings` so the saved-view slots (which snapshot and restore that
  // object) carry it too. Defaults on.
  const hoistEdgesEnabled = graphSettings.hoistEdges !== false;
  const toggleHoistEdges = () => updateGraphSetting('hoistEdges', !hoistEdgesEnabled);

  const switchLayout = (mode: 'uml' | 'force') => {
    if (mode === layoutMode) return;
    // Blur the old diagram and keep the splash up until the (potentially slow)
    // relayout finishes — the layout effect releases it once the new positions
    // are applied, then the graph is revealed instantly (no node fade / camera
    // pan) so the switch feels fast. All graph settings persist across the
    // switch; the focused node is preserved and re-framed in the new layout.
    holdSplash();
    localStorage.setItem('rt-graph-layout2', mode);
    refocusRef.current = selectedReqId;
    switchingRef.current = true;
    setLayoutMode(mode);
    // NB: no releaseSplash() here — completion drives it, not a fixed timer.
  };

  const loadSeqRef = useRef(0);

  const loadData = useCallback(() => {
    const vp = rfRef.current?.getViewport() ?? null;
    holdSplash();
    // Sequence guard. loadData re-fires on every graphVersion bump (undo, save,
    // any SSE change), so a slow earlier request could resolve *after* a newer
    // one and repaint the graph with pre-undo state until the next mutation.
    // The ELK layout below already guards this way; the data fetch did not.
    const seq = ++loadSeqRef.current;
    Promise.all([
      api.listRequirements(projectId),
      api.getTraces(projectId),
      api.getEvaluation(projectId).catch(() => null),
      api.listComponents(projectId).catch(() => []),
    ]).then(([requirements, traceData, evaluation, compData]) => {
      if (seq !== loadSeqRef.current) return;   // superseded
      setReqs(requirements); setTraces(traceData.links || []);
      setComponents(compData || []);
      setEvaluated(new Map((evaluation?.requirements ?? []).map((er) => [er.id, er])));
      setEntranceDone(false);
      if (vp) {
        setTimeout(() => {
          rfRef.current?.setViewport(vp, { duration: 0 });
        }, 50);
      }
      releaseSplash();
    }).catch((err) => {
      if (seq !== loadSeqRef.current) return;
      console.error(err);
      releaseSplash(150);
    });
  }, [projectId, holdSplash, releaseSplash]);

  useEffect(() => { loadData(); }, [loadData]);

  // Reactively reload graph when requirements are mutated elsewhere.
  const graphVersion = useStore((s) => s.graphVersion);
  const refocusGraph = useStore((s) => s.refocusGraph);
  const prevGraphVersion = useRef(graphVersion);
  const prevRefocusGraph = useRef(refocusGraph);
  useEffect(() => {
    if (graphVersion !== prevGraphVersion.current) {
      prevGraphVersion.current = graphVersion;
      loadData();
    }
  }, [graphVersion, loadData]);
  useEffect(() => {
    if (refocusGraph !== prevRefocusGraph.current) {
      prevRefocusGraph.current = refocusGraph;
      // Wait for React to commit the new nodes, then refit
      const id = requestAnimationFrame(() => {
        rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom, duration: 400 });
      });
      return () => cancelAnimationFrame(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refocusGraph]);

  const effectiveHidden = useMemo(
    () => effectiveHiddenComponents(components, hiddenComponents),
    [components, hiddenComponents],
  );

  const filteredReqs = useMemo(() => {
    let out = reqs;
    if (search) {
      const q = search.toLowerCase();
      out = out.filter(r => r.id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
    }
    if (filterStatus) out = out.filter(r => r.status === filterStatus);
    if (filterPriority) out = out.filter(r => r.priority === filterPriority);
    if (hiddenBaselines.length > 0) out = out.filter(r => !isReqHiddenByBaselines(r.baselines, hiddenBaselines));
    if (filterType) out = out.filter(r => r.type === filterType);
    if (filterVerStatus) out = out.filter(r => r.verification_status === filterVerStatus);
    if (filterVerMethod) out = out.filter(r => r.verification_method === filterVerMethod);
    if (filterAllocated) out = out.filter(r => r.allocated_to === filterAllocated);
    if (hiddenComponents.length > 0) out = out.filter(r => !isReqHiddenByComponents(r.id, components, effectiveHidden));
    if (hideRoots) out = out.filter(r => r.parent);
    return out;
  }, [reqs, search, filterStatus, filterPriority, hiddenBaselines, filterType,
      filterVerStatus, filterVerMethod, filterAllocated, hiddenComponents, components, effectiveHidden, hideRoots]);

  const distinct = (pick: (r: typeof reqs[number]) => string) =>
    [...new Set(reqs.map(pick).filter(Boolean))].sort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  const availableStatuses = useMemo(() => distinct(r => r.status), [reqs]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const availablePriorities = useMemo(() => distinct(r => r.priority), [reqs]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const availableTypes = useMemo(() => distinct(r => r.type), [reqs]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const availableVerStatuses = useMemo(() => distinct(r => r.verification_status), [reqs]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const availableVerMethods = useMemo(() => distinct(r => r.verification_method), [reqs]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const availableAllocations = useMemo(() => distinct(r => r.allocated_to), [reqs]);
  const availableBaselines = useMemo(() => {
    const set = new Set<string>();
    for (const r of reqs) {
      for (const b of r.baselines || []) {
        if (b) set.add(b);
      }
    }
    return [...set].sort();
  }, [reqs]);
  const availableComponents = useMemo(
    () => filterableComponentIds(components, hiddenComponents),
    [components, hiddenComponents],
  );
  const componentLabels = useMemo(
    () => new Map(components.map(c => [c.id, `${c.id}${c.name ? ` — ${c.name}` : ''}`])),
    [components],
  );

  // ── F5: prune unknown ids from hidden lists ──────────────────────────────

  // Prune hiddenComponents once components have loaded.  Don't prune while
  // components is still empty (loading state), because that would clear
  // everything.
  useEffect(() => {
    if (components.length === 0) return;
    const pruned = pruneUnknownIds(hiddenComponents, components.map((c) => c.id));
    if (pruned !== hiddenComponents) setHiddenComponents([...pruned]);
  }, [components, hiddenComponents, setHiddenComponents]);

  // Prune hiddenBaselines against the set of baselines that actually exist in
  // this project's requirements.  Same guard: don't prune while reqs haven't
  // loaded yet.
  useEffect(() => {
    if (availableBaselines.length === 0) return;
    const pruned = pruneUnknownIds(hiddenBaselines, availableBaselines);
    if (pruned !== hiddenBaselines) setHiddenBaselines([...pruned]);
  }, [availableBaselines, hiddenBaselines, setHiddenBaselines]);



  const clearFilters = () => {
    setSearch('');
    setFilterStatus('');
    setFilterPriority('');
    setHiddenBaselines([]);
    setFilterType('');
    setFilterVerStatus('');
    setFilterVerMethod('');
    setFilterAllocated('');
    setHiddenComponents([]);
  };
  const activeFilterCount = [
    search, filterStatus, filterPriority, filterType,
    filterVerStatus, filterVerMethod, filterAllocated,
  ].filter(Boolean).length + (hiddenBaselines.length > 0 ? 1 : 0) + (hiddenComponents.length > 0 ? 1 : 0);
  const hasActiveFilters = activeFilterCount > 0;

  const childrenByParent = useMemo(() => {
    const map = new Map<string | null, string[]>();
    for (const r of reqs) {
      const p = r.parent || null;
      if (!map.has(p)) map.set(p, []);
      map.get(p)!.push(r.id);
    }
    return map;
  }, [reqs]);

  const reqsById = useMemo(() => {
    const map = new Map<string, (typeof reqs)[number]>();
    for (const r of reqs) map.set(r.id, r);
    return map;
  }, [reqs]);

  const childCounts = useMemo(() => {
    const counts = new Map<string, number>();
    const childrenOf = (id: string | null) => childrenByParent.get(id) || [];
    function count(id: string): number {
      let total = 0;
      for (const cid of childrenOf(id)) {
        total += 1 + count(cid);
      }
      counts.set(id, total);
      return total;
    }
    for (const rid of childrenOf(null)) count(rid);
    return counts;
  }, [childrenByParent]);

  // Which nodes are parents, and per-node counts of direct subgroup children
  // (direct children that are themselves parents) — drives the two expand
  // buttons and their badges.
  const parentIds = useMemo(() => {
    const s = new Set<string>();
    for (const r of reqs) { if (r.parent) s.add(r.parent); }
    return s;
  }, [reqs]);
  const subgroupCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of reqs) {
      if (r.parent && parentIds.has(r.id)) counts.set(r.parent, (counts.get(r.parent) || 0) + 1);
    }
    return counts;
  }, [reqs, parentIds]);

  // Auto-collapse: on first load, fold every non-root group so the graph opens
  // as a groups overview — top-level roots stay expanded (showing their direct
  // child groups), and everything deeper is collapsed behind an expand button.
  useEffect(() => {
    if (autoCollapsed || reqs.length === 0) return;
    const toFold = new Set<string>();
    // childrenByParent is a Map, so Object.keys() returns [] — this Set was
    // always empty and auto-collapse silently never fired, opening every
    // project fully expanded.
    const isParent = new Set(
      [...childrenByParent.keys()].filter((k): k is string => k !== null));
    for (const r of reqs) {
      if (isParent.has(r.id) && r.parent) toFold.add(r.id);
    }
    if (toFold.size > 0) setCollapsed(toFold);
    setAutoCollapsed(true);
  }, [reqs, autoCollapsed, childrenByParent]);

  const expandAll = () => { setCollapsed(new Set()); setGroupsOnly(new Set()); };
  const collapseAll = () => {
    const all = new Set<string>();
    for (const r of reqs) {
      if (reqs.some(c => c.parent === r.id)) all.add(r.id);
    }
    // Re-frame the selection after the collapse (or fit everything if nothing
    // is focused), mirroring the expand refocus.
    refocusRef.current = selectedReqId ?? '*';
    setCollapsed(all);
    setGroupsOnly(new Set());
  };

  const visibleNodeIds = useMemo(() => {
    const visible = new Set<string>();
    function collect(id: string) {
      // A collapsed node is still shown (with its expand button); only its
      // descendants are hidden. So add it first, then stop recursing.
      visible.add(id);
      if (collapsed.has(id)) return;
      // In groups-only mode, reveal only the children that are parents; leaf
      // children stay hidden until the node is fully expanded.
      const gOnly = groupsOnly.has(id);
      for (const r of reqs) {
        if (r.parent !== id) continue;
        if (gOnly && !parentIds.has(r.id)) continue;
        collect(r.id);
      }
    }
    for (const r of reqs) { if (!r.parent) collect(r.id); }
    if (visible.size === 0) reqs.forEach(r => visible.add(r.id));
    return visible;
  }, [reqs, collapsed, groupsOnly, parentIds]);

  // Track which nodes were visible *before* the current collapsed state, so we
  // can detect newly-appearing children and give them an entrance animation.
  // Skip on the very first mount (all nodes are "new" then).
  const prevVisibleIdsRef = useRef<Set<string>>(new Set());
  const hasLaidOutOnceRef = useRef(false);
  const newChildrenIds = useMemo(() => {
    if (!hasLaidOutOnceRef.current) return new Set<string>();
    const fresh = new Set<string>();
    for (const id of visibleNodeIds) {
      if (!prevVisibleIdsRef.current.has(id)) fresh.add(id);
    }
    return fresh;
  }, [visibleNodeIds]);
  useEffect(() => {
    prevVisibleIdsRef.current = visibleNodeIds;
  }, [visibleNodeIds]);

  const { initialNodes, initialEdges } = useMemo(() => {
    const filteredIds = new Set(filteredReqs.map(r => r.id));
    const visIds = new Set([...visibleNodeIds].filter(id => filteredIds.has(id)));

    const fmt = (v: number) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100));
    const stripHtml = (html: string) => {
      const hit = stripHtmlCache.get(html);
      if (hit !== undefined) return hit;
      const text = new DOMParser().parseFromString(html || '', 'text/html').body.textContent?.trim() ?? '';
      stripHtmlCache.set(html, text);
      return text;
    };

    const wfEval = whatIf.impact?.evaluation;
    const wfRoots = whatIf.impact?.roots ?? [];
    const wfStepOwner = whatIf.impact?.steps[whatIf.stepIndex]?.owner ?? null;
    const wfRootOwners = new Set(wfRoots.map((r) => r.split('.')[0]));

    const previewByReq = new Map<string, { verdict: string; delta: string | null }>();
    if (wfEval) {
      const baseVMap = new Map<string, string>();
      for (const er of evaluated.values()) {
        if (er.verdict !== 'none') baseVMap.set(er.id, er.verdict);
      }
      for (const er of wfEval.requirements) {
        if (er.verdict === 'none') continue;
        const base = baseVMap.get(er.id);
        let delta: string | null = null;
        if (base && base !== er.verdict) {
          if (er.verdict === 'fail') delta = 'broke';
          else if (base === 'fail' && er.verdict === 'pass') delta = 'fixed';
          else delta = 'changed';
        }
        previewByReq.set(er.id, { verdict: er.verdict, delta });
      }
    }

    // Verdict of the requirement currently highlighted on the canvas (the
    // step owner).  Passed as node data so the node component can colour its
    // pulse by verdict — green for pass, red for fail, neutral for unknown.
    const wfStepVerdict = wfEval && wfStepOwner
      ? requirementVerdict(wfEval, wfStepOwner)
      : null;

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
        expr: c.expr || (c as { constraint_def?: string }).constraint_def || '',
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
          groupsOnly: groupsOnly.has(req.id),
          childCount: childCounts.get(req.id) || 0,
          subgroupCount: subgroupCounts.get(req.id) || 0,
          onSelect: () => selectReq(req.id),
          onAddChild: () => {
            selectReq(req.id);
            navigate(`/project/${projectId}/requirements?new=1&parent=${req.id}`);
          },
          // Simple one-level toggle (all direct children) — used by the force
          // layout node and double-click. Collapsing re-frames the selection.
          onExpandCollapse: () => {
            if (!collapsed.has(req.id)) { refocusRef.current = req.id; prevSelectedRef.current = req.id; }
            setGroupsOnly(prev => { const n = new Set(prev); n.delete(req.id); return n; });
            setCollapsed(prev => {
              const next = new Set(prev);
              if (next.has(req.id)) next.delete(req.id); else next.add(req.id);
              return next;
            });
          },
          // Button 1 (single chevron): reveal only the direct children that are
          // themselves parents (subgroups); leaf children stay hidden. Toggles
          // between groups-only and collapsed.
          onExpandGroups: () => {
            const wasCollapsed = collapsed.has(req.id);
            if (!wasCollapsed) { refocusRef.current = req.id; prevSelectedRef.current = req.id; }
            setCollapsed(prev => {
              const next = new Set(prev);
              if (next.has(req.id)) next.delete(req.id); else next.add(req.id);
              return next;
            });
            setGroupsOnly(prev => {
              const next = new Set(prev);
              if (wasCollapsed) next.add(req.id); else next.delete(req.id);
              return next;
            });
          },
          // Button 2 (double chevron): reveal ALL descendants (deep). Expands
          // when collapsed or groups-only; otherwise collapses the whole subtree.
          onToggleDescendants: () => {
            const expand = collapsed.has(req.id) || groupsOnly.has(req.id);
            if (!expand) { refocusRef.current = req.id; prevSelectedRef.current = req.id; }
            setCollapsed(prev => {
              const next = new Set(prev);
              if (expand) {
                const removeDescendants = (nodeId: string) => {
                  next.delete(nodeId);
                  for (const r of reqs) { if (r.parent === nodeId) removeDescendants(r.id); }
                };
                removeDescendants(req.id);
              } else {
                next.add(req.id);
                const collapseDescendants = (nodeId: string) => {
                  for (const r of reqs) {
                    if (r.parent === nodeId) { next.add(r.id); collapseDescendants(r.id); }
                  }
                };
                collapseDescendants(req.id);
              }
              return next;
            });
            // Either way, clear groups-only across the subtree so the reveal is
            // full (or the collapse is clean).
            setGroupsOnly(prev => {
              const next = new Set(prev);
              const clear = (nodeId: string) => {
                next.delete(nodeId);
                for (const r of reqs) { if (r.parent === nodeId) clear(r.id); }
              };
              clear(req.id);
              return next;
            });
          },
          params, constraints,
          verdict: ev && ev.verdict !== 'none' ? ev.verdict : null,
          previewVerdict: previewByReq.get(req.id)?.verdict ?? null,
          previewDelta: previewByReq.get(req.id)?.delta ?? null,
          isOverrideRoot: wfRootOwners.has(req.id),
          pulseActive: wfStepOwner === req.id,
          wfStepVerdict,
          vcCount: (req.verification_cases ?? []).length,
          desc: stripHtml(req.description).slice(0, 320),
          hasMissingInfo: !req.description || !req.name || !req.rationale || (req.verification_cases?.length ?? 0) === 0,
        },
        style: entranceDone ? {} : { opacity: 0 },
      };
    });

    const edges: Edge[] = [];
    const seen = new Set<string>();

    // Relation candidates (requirement relations, trace links, cascades) are
    // collected first, then hoisted: a hidden endpoint is redirected to its
    // nearest visible ancestor, so a collapsed graph keeps the relationship
    // line landing on the group standing in for what is inside it.
    const parentOf = new Map(reqs.map((r) => [r.id, r.parent]));
    const relationCandidates: { source: string; target: string; type: string }[] = [];
    for (const req of reqs) {
      for (const rel of req.relations || []) {
        relationCandidates.push({ source: req.id, target: rel.target, type: rel.type });
      }
    }
    for (const link of traces) {
      relationCandidates.push({ source: link.source, target: link.target, type: link.type });
    }
    for (const req of reqs) {
      if (req.cascade_from) relationCandidates.push({ source: req.cascade_from, target: req.id, type: 'cascades' });
    }

    const pushEdge = (src: string, tgt: string, typ: string, hoisted: boolean, count: number) => {
      // The id must be stable for a given (source, target, hoisted) triple so
      // the edge memo can bail out on unchanged edges instead of re-deriving
      // geometry on every selection/hover restyle.
      const k = hoisted ? `${src}-${tgt}-${typ}-hoist` : `${src}-${tgt}-${typ}`;
      if (seen.has(k)) return; seen.add(k);
      const style = edgeMarkers[typ] || { markerEnd: MarkerType.ArrowClosed, strokeDasharray: 'none', strokeWidth: 1 };
      const color = edgeColors[typ] || '#64748b';
      edges.push({
        id: k, source: src, target: tgt, type: 'floating',
        data: { color, label: typ, hoisted, count },
        // A hoisted edge is visually distinct: a short dash that reads as
        // "the endpoint is a group standing in for something inside it".
        style: {
          stroke: color,
          strokeWidth: style.strokeWidth,
          strokeDasharray: hoisted ? '2,3' : style.strokeDasharray,
          opacity: 0.45,
        },
        markerEnd: { type: style.markerEnd, color, width: 14, height: 14 },
      });
    };

    if (hoistEdgesEnabled) {
      for (const h of hoistEdges(relationCandidates, visIds, parentOf)) {
        pushEdge(h.source, h.target, h.type, h.hoisted, h.count);
      }
    } else {
      // Toggle off: the pre-hoist behaviour — an edge with a hidden endpoint is
      // simply dropped.
      const seenRel = new Set<string>();
      for (const r of relationCandidates) {
        if (!visIds.has(r.source) || !visIds.has(r.target)) continue;
        const k = `${r.source}-${r.target}-${r.type}`;
        if (seenRel.has(k)) continue; seenRel.add(k);
        pushEdge(r.source, r.target, r.type, false, 1);
      }
    }

    for (const req of reqs) {
      if (!req.parent) continue;
      // A parent edge into a hidden child is internal to a collapsed group —
      // drop it rather than draw a dangling line to a node that isn't there.
      if (!visIds.has(req.id)) continue;
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

    return { initialNodes: nodes, initialEdges: edges };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqs, filteredReqs, traces, visibleNodeIds, childCounts, collapsed, entranceDone, evaluated, whatIf.impact, whatIf.stepIndex, hoistEdgesEnabled]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const rfRef = useRef<ReactFlowInstance | null>(null);
  const graphBoxRef = useRef<HTMLDivElement>(null);

  // React Flow stamps every edge `<g>` with the `nopan` class so a click-drag
  // that starts on an edge never pans the view. Here an edge is neither
  // draggable nor reconnectable, and an edge click is a no-op unless a
  // requirement is already selected — so the class only blocks the very pan it
  // was meant to leave alone. Strip it from edge groups (NOT from the edge
  // label badges, which use `nopan` deliberately to stay interactive). React
  // Flow re-applies the class whenever the edge store updates, so watch for
  // mutations rather than relying on a single pass.
  useEffect(() => {
    const strip = () => {
      graphBoxRef.current
        ?.querySelectorAll<SVGGElement>('.react-flow__edge.nopan')
        .forEach((el) => el.classList.remove('nopan'));
    };
    strip();
    const root = graphBoxRef.current;
    if (!root) return;
    const observer = new MutationObserver(strip);
    observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  // The "Reset view" action: frame all currently-visible nodes.
  const resetView = useCallback(() => {
    rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom, duration: 400 });
  }, [gs.maxZoom]);
  // Distinguish a structural relayout (mode/settings change, first mount) from
  // an incremental data refresh. Only the former should re-fit the camera and
  // clear the selection; a live data update must preserve position and focus.
  const layoutSigRef = useRef<string | null>(null);
  const hasLaidOutRef = useRef(false);
  // Guards the one-shot startup fit (effect lives after `nodes` is declared).
  const didInitialFit = useRef(false);
  // Monotonic id so a stale async ELK result (from a superseded relayout or a
  // rapid filter change) is discarded instead of clobbering the current one.
  const layoutReqIdRef = useRef(0);

  // ── F1: expand the view when revealing a component brings requirements back ──

  const prevHiddenComponentsRef = useRef(hiddenComponents);

  // This only records the *intent*. The camera is moved by `applyRefocus`,
  // which the layout effect calls once the relayout has placed every node.
  //
  // Doing the fit here instead does not work, and fails in a way that looks
  // like success: revealing grows `initialNodes`, so at this point React Flow
  // has never heard of the ids to frame and `fitView` silently drops the ones
  // it does not know. Even once that is waited out, this pipeline already
  // schedules its own fits on 40-250ms timers, and they simply land last —
  // measured, the reveal framed the requirements correctly at t+700ms and was
  // then overridden three times, ending with them off screen.
  useEffect(() => {
    const prev = prevHiddenComponentsRef.current;
    if (prev === hiddenComponents) return;
    prevHiddenComponentsRef.current = hiddenComponents;
    if (!entranceDone) return;
    const revealed = requirementsRevealed(
      components, prev, hiddenComponents, reqs.map((r) => r.id));
    if (revealed.length > 0) refocusRef.current = { expand: revealed };
  }, [hiddenComponents, components, reqs, entranceDone]);


  // ── Saved view slots ──────────────────────────────────────────────────────
  const persistViews = useCallback((next: (SavedView | null)[]) => {
    try { localStorage.setItem(`rt-graph-views-${projectId}`, JSON.stringify(next)); } catch { /* quota */ }
  }, [projectId]);

  const saveView = useCallback((slot: number) => {
    const snapshot: SavedView = {
      collapsed: [...collapsed],
      groupsOnly: [...groupsOnly],
      selectedReqId,
      layoutMode,
      graphSettings,
      hopDepth,
      showAllLinks,
      linkDir,
      filters: {
        search, status: filterStatus, priority: filterPriority,
        type: filterType, verStatus: filterVerStatus, verMethod: filterVerMethod,
        allocated: filterAllocated,
        hiddenBaselines: [...hiddenBaselines],
        hiddenComponents: [...hiddenComponents],
      },
      viewport: rfRef.current?.getViewport() ?? null,
    };
    setViews((prev) => {
      const next = [...prev];
      next[slot] = snapshot;
      persistViews(next);
      return next;
    });
  }, [collapsed, groupsOnly, selectedReqId, layoutMode, graphSettings, hopDepth, showAllLinks, linkDir, search,
      filterStatus, filterPriority, hiddenBaselines, filterType, filterVerStatus, filterVerMethod,
      filterAllocated, hiddenComponents, persistViews]);

  const clearView = useCallback((slot: number) => {
    setViews((prev) => {
      const next = [...prev];
      next[slot] = null;
      persistViews(next);
      return next;
    });
  }, [persistViews]);

  const restoreView = useCallback((slot: number) => {
    const v = views[slot];
    if (!v) return;
    // The layout effect will apply focus + camera once the relayout settles.
    restoreRef.current = { viewport: v.viewport, selectedReqId: v.selectedReqId };
    setCollapsed(new Set(v.collapsed));
    setGroupsOnly(new Set(v.groupsOnly ?? []));
    if (v.layoutMode !== layoutMode) {
      try { localStorage.setItem('rt-graph-layout2', v.layoutMode); } catch { /* ignore */ }
      setLayoutMode(v.layoutMode);
    }
    setGraphSettings(v.graphSettings || {});
    try { localStorage.setItem(`rt-graph-settings-${projectId}`, JSON.stringify(v.graphSettings || {})); } catch { /* ignore */ }
    setHopDepthPersist(v.hopDepth ?? 1);
    setShowAllLinks(v.showAllLinks ?? false);
    try { localStorage.setItem('rt-graph-all-links', v.showAllLinks ? '1' : '0'); } catch { /* ignore */ }
    setLinkDirPersist(v.linkDir ?? 'both');
    const f = v.filters || ({} as SavedView['filters']);
    setSearch(f.search ?? '');
    setFilterStatus(f.status ?? '');
    setFilterPriority(f.priority ?? '');
    setHiddenBaselines(f.hiddenBaselines ?? migrateLegacyFilterList(f.baselines, availableBaselines));
    setFilterType(f.type ?? '');
    setFilterVerStatus(f.verStatus ?? '');
    setFilterVerMethod(f.verMethod ?? '');
    setFilterAllocated(f.allocated ?? '');
    setHiddenComponents(f.hiddenComponents ?? migrateLegacyFilterList(f.components, components.map(c => c.id)));
    // Guarantee the layout effect runs (and thus consumes restoreRef) even if
    // the restored config is identical to the current one.
    setLayoutNonce((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [views, layoutMode, projectId, setHopDepthPersist, components, availableBaselines]);

  useEffect(() => {
    const layoutSig = `${layoutMode}|${gs.nodesep}|${gs.ranksep}|${gs.rankdir}|${gs.margin}|${gs.maxZoom}`;
    const firstRun = !hasLaidOutRef.current;
    const layoutChanged = layoutSigRef.current !== layoutSig;
    layoutSigRef.current = layoutSig;
    hasLaidOutRef.current = true;
    const shouldRefit = firstRun || layoutChanged;
    // A restore in flight: apply the saved focus + camera instead of auto-fitting.
    const restore = restoreRef.current;
    // A layout-mode switch in flight: keep the focused node and re-frame it,
    // and reveal instantly (no camera animation) once positions are final.
    const refocus = refocusRef.current;
    const switching = switchingRef.current;
    // Re-fit only on a structural relayout — a live data refresh keeps the
    // user's current selection and viewport intact. During a restore the saved
    // camera wins; during a layout switch the focus is preserved — so in both
    // cases skip clearing the selection.
    const refit = () => {
      if (!shouldRefit || restore) return;
      if (!refocus) selectReq(null);
      return { duration: 300 };
    }; // fitView called inline below with correct duration

    // Re-frame the camera after a structural change that keeps the selection:
    // a layout switch (instant, no animation) or a collapse (animated, like the
    // expand refocus). `refocus` is a node id to frame, '*' to fit everything,
    // or null for no refocus. Returns true when it handled the camera.
    const applyRefocus = () => {
      const target = refocus;
      refocusRef.current = null;
      if (!target) return false;
      const duration = switching ? 0 : 500;
      if (typeof target === 'object') {
        // Expand rather than reframe: keep what the user is already looking at
        // and widen until the newly revealed nodes are in shot too. Read the
        // live React Flow nodes, not the `nodes` state — this runs from a
        // scheduled callback, and the state closed over here can be a relayout
        // behind.
        const live = rfRef.current?.getNodes() ?? [];
        const vp = rfRef.current?.getViewport();
        const box = graphBoxRef.current;
        if (!vp || !box || live.length === 0) return true;
        const { width: paneW, height: paneH } = box.getBoundingClientRect();
        const union = new Set(target.expand);
        for (const n of live) {
          const m = n.measured;
          if (!m?.width || !m?.height) continue;
          const x = n.position.x * vp.zoom + vp.x;
          const y = n.position.y * vp.zoom + vp.y;
          if (x + m.width * vp.zoom > 0 && x < paneW
            && y + m.height * vp.zoom > 0 && y < paneH) union.add(n.id);
        }
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        rfRef.current?.fitView({
          nodes: [...union].map((id) => ({ id })),
          padding: 0.25,
          maxZoom: gs.maxZoom,
          duration: reduced ? 0 : 600,
        });
        claimCamera();
        return true;
      }
      if (target === '*') {
        rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom, duration });
        return true;
      }
      // A collapse may have hidden the target — walk up to its nearest visible
      // ancestor (the group it now lives inside) so there's always something to
      // frame.
      let id: string | null = target;
      while (id && !visibleNodeIds.has(id)) id = reqsById.get(id)?.parent ?? null;
      if (!id) { rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom, duration }); return true; }
      const related = new Set<string>([id]);
      for (const e of initialEdges) {
        if (e.source === id) related.add(e.target);
        if (e.target === id) related.add(e.source);
      }
      rfRef.current?.fitView({
        nodes: [...related].map((nid) => ({ id: nid })),
        padding: 0.3, maxZoom: gs.maxZoom, duration,
      });
      return true;
    };

    // Apply a pending restore's focus + camera once nodes are at final positions.
    const applyRestore = () => {
      if (!restore) return;
      restoreRef.current = null;
      // Seed prevSelectedRef so the selection-fit effect won't re-frame.
      prevSelectedRef.current = restore.selectedReqId;
      selectReq(restore.selectedReqId);
      if (restore.viewport) {
        rfRef.current?.setViewport(restore.viewport, { duration: 450 });
      }
    };

    // UML mode: ELK lays out (over composition + relations) AND routes the
    // edges orthogonally. It's async, so guard against stale results.
    if (layoutMode === 'uml') {
      const reqId = ++layoutReqIdRef.current;
      // Every phased-animation timer is tracked here so a re-run (data refresh,
      // filter/mode change) can cancel the whole chain. `schedule` also bails if
      // a newer layout superseded this one before the timer fired, so stale
      // closures can never clobber a fresher layout.
      const timers: ReturnType<typeof setTimeout>[] = [];
      const schedule = (fn: () => void, ms: number) => {
        const t = setTimeout(() => {
          if (reqId !== layoutReqIdRef.current) return; // superseded — discard
          fn();
        }, ms);
        timers.push(t);
      };
      elkLayout(initialNodes, initialEdges, gs).then(({ positions, edgePoints, heights }) => {
        if (reqId !== layoutReqIdRef.current) return; // superseded — discard

        // A restore is a full relayout, never the expand choreography.
        const expanding = newChildrenIds.size > 0 && !restore;
        const newIds = new Set(newChildrenIds);
        const r = refit();

        if (expanding) {
          animatingRef.current = true;
          const origDash = new Map<string, string | undefined>();
          const edgeLen = new Map<string, number>();
          for (const e of initialEdges) {
            origDash.set(e.id, (e.style as any)?.strokeDasharray);
            const pts = (e.data as any)?.points as { x: number; y: number }[] | undefined;
            if (pts && pts.length > 1) {
              let len = 0;
              for (let i = 1; i < pts.length; i++) {
                len += Math.abs(pts[i].x - pts[i - 1].x) + Math.abs(pts[i].y - pts[i - 1].y);
              }
              edgeLen.set(e.id, Math.round(len + 1));
            }
          }

          const edgeLenFn = (e: Edge) => edgeLen.get(e.id) ?? 600;
          const maxLen = Math.max(1, ...edgeLen.values());
          const retractMs = (len: number) => Math.max(60, Math.round((len / maxLen) * 300));
          const retractAnimStyle = (len: number) => ({
            '--edge-len': String(len),
            strokeDasharray: `${len} ${len}`,
            strokeDashoffset: '0',
            animation: `retractEdge ${retractMs(len)}ms ease-in forwards`,
          });

          // Phase 1 — retract edges into sources (CSS animation).
          setEdges((eds) => eds.map((e) => ({ ...e, style: retractAnimStyle(edgeLenFn(e)) as any })));

          // Phase 2 — after retract, slide nodes to new ELK positions. The
          // transform transition is set inline (per-node) only here, since the
          // expand choreography is the one place a position *slide* is wanted.
          schedule(() => {
            setNodes(initialNodes.map((n) => {
              const p = positions.get(n.id);
              const isNew = newIds.has(n.id);
              return p ? { ...n, position: { x: p.x, y: p.y }, data: { ...n.data, elkHeight: heights.get(n.id) ?? BASE_NODE_H }, style: { ...(n.style as any), opacity: isNew ? 0 : undefined, transition: 'transform 0.35s ease-out' } } : n;
            }));
            // Phase 3 — after nodes settle, grow new edges + fade children.
            schedule(() => {
              const newEdgeLen = (pts: { x: number; y: number }[] | undefined) => {
                if (!pts || pts.length < 2) return 600;
                let len = 0;
                for (let i = 1; i < pts.length; i++) len += Math.abs(pts[i].x - pts[i - 1].x) + Math.abs(pts[i].y - pts[i - 1].y);
                return Math.round(len + 1);
              };
              const maxGrowLen = Math.max(1, ...[...initialEdges]
                .map((e) => newEdgeLen(edgePoints.get(e.id)))
                .filter((n): n is number => n > 0));
              const growMs = (len: number) => Math.max(60, Math.round((len / maxGrowLen) * 500));
              const growAnimStyle = (e: Edge) => {
                const len = newEdgeLen(edgePoints.get(e.id));
                return {
                  '--edge-len': String(len),
                  strokeDasharray: `${len} ${len}`,
                  strokeDashoffset: '0',
                  animation: `growEdge ${growMs(len)}ms ease-out forwards`,
                  ...(e.id.endsWith('-parent') ? { stroke: 'hsl(var(--muted-foreground) / 0.55)', strokeWidth: 1.4, opacity: 0.7 } : { opacity: 0.55 }),
                };
              };
              setEdges(initialEdges.map((e) => ({
                ...e, type: 'ortho' as const, data: { ...e.data, points: edgePoints.get(e.id) }, style: growAnimStyle(e) as any,
              })));
              setNodes((nds) => nds.map((n) => {
                const isNew = newIds.has(n.id);
                return { ...n, style: { ...(n.style as any)!, opacity: 1, transition: `opacity 0.5s ease-out${isNew ? ' 0.1s' : ''}` } };
              }));
              // Phase 4 — cleanup after grow animation finishes.
              const cleanupMs = growMs(maxGrowLen) + 60;
              schedule(() => {
                setEdges((eds) => eds.map((e) => {
                  const clean = { ...(e.style as any)! };
                  delete clean['--edge-len']; delete clean.animation;
                  const nativeDash = origDash.get(e.id);
                  if (nativeDash != null && nativeDash !== 'none') clean.strokeDasharray = nativeDash;
                  else delete clean.strokeDasharray;
                  return { ...e, style: clean };
                }));
                animatingRef.current = false;
                if (switching) { switchingRef.current = false; releaseSplash(); }
                const expandedParents = new Set([...newChildrenIds].map(cid => initialNodes.find(n => n.id === cid)?.data?.parent).filter(Boolean) as string[]);
                const expandedNodeId = [...expandedParents][0];
                // A derivation trace expands many groups at once and owns both
                // the selection and the camera; without this guard the usual
                // "focus what you just expanded" behaviour would steal them
                // and silently cancel the trace.
                if (expandedNodeId && !derivingRef.current && !suppressRefitRef.current) {
                  selectReq(expandedNodeId);
                  requestAnimationFrame(() => {
                    rfRef.current?.fitView({ nodes: initialNodes.filter(n => n.id === expandedNodeId), padding: 0.2, maxZoom: gs.maxZoom, duration: 500 });
                  });
                }
                derivingRef.current = false;
              }, cleanupMs);
            }, 400);
          }, 350);
        } else {
          // Non-expand relayout (first load, refresh, mode/settings change):
          // drop the nodes straight onto their final ELK positions — no
          // transform transition exists globally, so there's no slide — then
          // fade them in via opacity only.
          setNodes(initialNodes.map((n) => {
            const p = positions.get(n.id);
            return p ? {
              ...n,
              position: { x: p.x, y: p.y },
              data: { ...n.data, elkHeight: heights.get(n.id) ?? BASE_NODE_H },
            } : n;
          }));
          if (!entranceDone) {
            schedule(() => {
              setNodes((nds) => nds.map((n, i) => ({
                ...n,
                style: { ...(n.style as any), opacity: 1, transition: `opacity 0.3s ease-out ${Math.min(i * 4, 250)}ms` },
              })));
              setEntranceDone(true);
            }, 40);
          }
          if (restore) schedule(applyRestore, 60);
          // Positions are final — reveal by lifting the layout-switch splash.
          if (switching) { switchingRef.current = false; releaseSplash(120); }
        }
        if (r || refocus) {
          schedule(() => {
            if (applyRefocus()) return;
            // A deliberate framing from the pass before still owns the camera.
            if (suppressRefitRef.current) return;
            rfRef.current?.fitView({
              padding: 0.12,
              maxZoom: gs.maxZoom,
              duration: switching ? 0 : (expanding ? 700 : 300),
            });
          }, switching ? 40 : (expanding ? 200 : 250));
        }
        if (!expanding) {
          setEdges(initialEdges.map((e) => {
            const isParent = e.id.endsWith('-parent');
            return {
              ...e,
              type: 'ortho',
              data: { ...e.data, points: edgePoints.get(e.id) },
              style: {
                ...(e.style as Record<string, unknown>),
                ...(isParent
                  ? { stroke: 'hsl(var(--muted-foreground) / 0.55)', strokeWidth: 1.4, opacity: 0.7 }
                  : { opacity: 0.55 }),
              },
            };
          }));
        }
        hasLaidOutOnceRef.current = true;
      }).catch((err) => {
        console.error('ELK layout failed', err);
        if (switching) { switchingRef.current = false; releaseSplash(); }
      });
      return () => {
        // Supersede any in-flight ELK result and cancel every pending phase
        // timer so a re-run never gets clobbered by the previous animation.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        layoutReqIdRef.current++;
        timers.forEach(clearTimeout);
        animatingRef.current = false;
        // If the switch-triggered layout was superseded before ELK settled
        // (e.g. an SSE data change fired loadData mid-computation), the
        // splash was held by switchLayout and the .then() bailed at the
        // reqId guard — release it here so the spinner doesn't stick.
        if (switching) { switchingRef.current = false; releaseSplash(); }
      };
    }

    // Force mode: synchronous d3-force + floating centre-to-centre edges.
    // Nodes land at their final positions immediately (no transform transition),
    // then fade in opacity only.
    setNodes(forceLayout(initialNodes, initialEdges));
    setEdges(initialEdges);
    const r = refit();
    const timers: ReturnType<typeof setTimeout>[] = [];
    if (!entranceDone) {
      timers.push(setTimeout(() => {
        setNodes(nds => nds.map((n, i) => ({
          ...n,
          style: { ...n.style, opacity: 1, transition: `opacity 0.3s ease-out ${Math.min(i * 4, 250)}ms` },
        })));
        setEntranceDone(true);
      }, 40));
    }
    if (restore) timers.push(setTimeout(applyRestore, 60));
    // Force layout is synchronous — positions are final now; lift the splash.
    if (switching) { switchingRef.current = false; releaseSplash(120); }
    if (r || refocus) {
      timers.push(setTimeout(() => {
        if (applyRefocus()) return;
        if (suppressRefitRef.current) return;
        rfRef.current?.fitView({ padding: 0.12, maxZoom: gs.maxZoom, duration: switching ? 0 : (r ? r.duration : 500) });
      }, switching ? 40 : 250));
    }
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialNodes, initialEdges, layoutMode, entranceDone, layoutNonce, gs.nodesep, gs.ranksep, gs.rankdir, gs.margin, gs.maxZoom, setNodes, setEdges]);

  // Run "Reset view" once on startup. The layout effect's first-run fit is
  // invalidated by the initial auto-collapse pass (its timer is cleared when
  // the collapsed node set re-lays out), so without this the canvas opens
  // unfitted. Firing after the entrance settles guarantees the collapsed set is
  // laid out and measured; the ref stops live reloads from re-framing.
  useEffect(() => {
    if (didInitialFit.current || !entranceDone || nodes.length === 0) return;
    didInitialFit.current = true;
    requestAnimationFrame(resetView);
  }, [entranceDone, nodes.length, resetView]);

  // When selection changes externally (nav click, etc.), smoothly fit view.
  // Also auto-expand any collapsed ancestor chain so the selected node is
  // always visible — a requirement opened via "Show in graph" shouldn't stay
  // hidden behind a folded parent group.
  useEffect(() => {
    if (!entranceDone || !selectedReqId || selectedReqId === prevSelectedRef.current) return;
    // A selection can land before the node exists — executing a change request
    // that proposes a new requirement selects it while the graph reload is
    // still in flight. Consuming the selection here would frame nothing and
    // never retry, so wait for the data instead. `reqs` and `nodes` are deps
    // for exactly this; the prevSelectedRef guard above stops the extra runs
    // from costing anything once the framing has happened.
    if (!reqs.some((r) => r.id === selectedReqId)) return;

    const byId = new Map(reqs.map(r => [r.id, r]));
    const toExpand = new Set<string>();
    let cursor: string | null = selectedReqId;
    while (cursor) {
      const node = byId.get(cursor);
      const ancestor: string | null = node ? node.parent ?? null : null;
      if (ancestor && (collapsed.has(ancestor) || groupsOnly.has(ancestor))) {
        toExpand.add(ancestor);
      }
      cursor = ancestor;
    }
    if (toExpand.size > 0) {
      prevSelectedRef.current = selectedReqId;
      const newCollapsed = new Set(collapsed);
      const newGroupsOnly = new Set(groupsOnly);
      for (const id of toExpand) { newCollapsed.delete(id); newGroupsOnly.delete(id); }
      setCollapsed(newCollapsed);
      setGroupsOnly(newGroupsOnly);
      refocusRef.current = selectedReqId;
      return;
    }

    // Ancestors are all open, so the node belongs on screen — if it is not laid
    // out yet the relayout is still in flight. Wait for it rather than framing
    // an empty subset.
    if (!nodes.some((n) => n.id === selectedReqId)) return;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedReqId, entranceDone, reqs, nodes]);

  // ── "Show derivation" (triggered from the requirement inspector) ─────────
  // Walk incoming relations transitively from the target: everything that
  // links *into* it, everything that links into those, and so on. Then reveal
  // the whole closure — any collapsed ancestor along the way is expanded, so
  // nothing in the trace stays hidden inside a folded group.
  useEffect(() => {
    if (!derivationReq) return;
    const root = derivationReq.id;

    // Relation edges only. Composition (parent→child) edges describe where a
    // requirement *lives*, not what it derives from; following them would drag
    // in whole sibling subtrees and drown the trace.
    const incoming = new Map<string, string[]>();
    for (const r of reqs) {
      for (const rel of r.relations || []) {
        const list = incoming.get(rel.target);
        if (list) list.push(r.id); else incoming.set(rel.target, [r.id]);
      }
    }
    for (const link of traces) {
      const list = incoming.get(link.target);
      if (list) list.push(link.source); else incoming.set(link.target, [link.source]);
    }

    const ids = new Set<string>([root]);
    const queue = [root];
    while (queue.length) {
      const id = queue.shift()!;
      for (const src of incoming.get(id) || []) {
        if (!ids.has(src)) { ids.add(src); queue.push(src); }
      }
    }

    // Reveal every node in the trace: un-collapse each of its ancestors, and
    // clear groups-only on them (that mode hides non-parent children).
    const byId = new Map(reqs.map((r) => [r.id, r]));
    const ancestors = new Set<string>();
    for (const id of ids) {
      let p = byId.get(id)?.parent ?? null;
      while (p) { ancestors.add(p); p = byId.get(p)?.parent ?? null; }
    }
    if (ancestors.size) {
      derivingRef.current = true;
      setCollapsed((prev) => {
        const next = new Set(prev);
        let changed = false;
        for (const a of ancestors) if (next.delete(a)) changed = true;
        return changed ? next : prev;
      });
      setGroupsOnly((prev) => {
        const next = new Set(prev);
        let changed = false;
        for (const a of ancestors) if (next.delete(a)) changed = true;
        return changed ? next : prev;
      });
    }

    setDerived({ root, ids });
    // Frame the trace once the expansion has laid out.
    refocusRef.current = null;
    const t = setTimeout(() => {
      const subset = [...ids].map((id) => ({ id }));
      if (subset.length) {
        rfRef.current?.fitView({ nodes: subset, padding: 0.25, duration: 600, maxZoom: gs.maxZoom });
      }
    }, ancestors.size ? 420 : 60);
    // Backstop: if this expansion never produced new children, the choreography
    // that normally clears the guard won't run, so release it here.
    const release = setTimeout(() => { derivingRef.current = false; }, 2500);
    return () => { clearTimeout(t); clearTimeout(release); };
  }, [derivationReq, reqs, traces, gs.maxZoom]);

  // A derivation trace belongs to one node — drop it as soon as focus moves.
  useEffect(() => {
    if (derived && derived.root !== selectedReqId) setDerived(null);
  }, [selectedReqId, derived]);

  // BFS out `hopDepth` rings from the focused node, recording each reached
  // node's hop distance so edges can be classed as radial (distances differ)
  // vs same-level cross-links (distances equal).
  const focus = useMemo(() => {
    const highlightId = selectedReqId || hoveredNodeId;
    if (!highlightId) return { ids: new Set<string>(), dist: new Map<string, number>() };
    const adj = new Map<string, string[]>();
    const link = (a: string, b: string) => {
      const list = adj.get(a);
      if (list) list.push(b); else adj.set(a, [b]);
    };
    // 'out' walks source→target, 'in' walks target→source, 'both' is undirected.
    for (const edge of initialEdges) {
      if (linkDir !== 'in') link(edge.source, edge.target);
      if (linkDir !== 'out') link(edge.target, edge.source);
    }
    const dist = new Map<string, number>([[highlightId, 0]]);
    let frontier = [highlightId];
    for (let d = 0; d < hopDepth && frontier.length; d++) {
      const next: string[] = [];
      for (const id of frontier) {
        for (const nb of adj.get(id) || []) {
          if (!dist.has(nb)) { dist.set(nb, d + 1); next.push(nb); }
        }
      }
      frontier = next;
    }
    return { ids: new Set(dist.keys()), dist };
  }, [selectedReqId, hoveredNodeId, initialEdges, hopDepth, linkDir]);
  // A live derivation trace replaces the hop-radius highlight entirely.
  const derivationActive = !!derived && derived.root === selectedReqId;

  //: `reqsById` is a memo over `reqs`, so it changes identity on every data
  //: refresh — an SSE event from another user, a graph-version bump. Reading it
  //: through a ref keeps it out of the effect's dependencies: framing must
  //: follow a *new evaluation*, not a background reload that re-expanded groups
  //: and pulled the camera away mid-read.
  const reqsByIdRef = useRef(reqsById);
  reqsByIdRef.current = reqsById;

  // ── What-if camera framing ──────────────────────────────────────────────
  // When a new evaluation arrives, expand any collapsed ancestor of every
  // affected requirement so it has a node, then frame the whole closure so the
  // user sees what changed. Follows the same pattern as the derivation-trace
  // effect above: expand collapsed ancestors, wait for relayout, fit subset,
  // and claim the camera with a time-bounded flag.
  useEffect(() => {
    if (!whatIf.impact) return;

    const roots = whatIf.impact.roots ?? [];
    const affected = whatIf.impact.affected ?? [];
    const union = new Set<string>([...roots, ...affected]);
    if (union.size === 0) return;

    // Expand collapsed ancestors so every id in the union has a node.
    const ancestors = new Set<string>();
    for (const id of union) {
      const byId = reqsByIdRef.current;
      let p = byId.get(id)?.parent ?? null;
      while (p) { ancestors.add(p); p = byId.get(p)?.parent ?? null; }
    }

    if (ancestors.size) {
      derivingRef.current = true;
      setCollapsed((prev) => {
        const next = new Set(prev);
        let changed = false;
        for (const a of ancestors) if (next.delete(a)) changed = true;
        return changed ? next : prev;
      });
      setGroupsOnly((prev) => {
        const next = new Set(prev);
        let changed = false;
        for (const a of ancestors) if (next.delete(a)) changed = true;
        return changed ? next : prev;
      });
    }

    refocusRef.current = null;
    // Frame the union once the expansion has laid out.
    const t = setTimeout(() => {
      const subset = [...union].map((id) => ({ id }));
      if (subset.length) {
        rfRef.current?.fitView({ nodes: subset, padding: 0.25, duration: 600, maxZoom: gs.maxZoom });
      }
    }, ancestors.size ? 420 : 60);

    const release = setTimeout(() => { derivingRef.current = false; }, 2500);
    return () => { clearTimeout(t); clearTimeout(release); };
  }, [whatIf.impact, gs.maxZoom]);

  const wfActive = !!whatIf.impact;
  const wfConnectedIds = useMemo(() => {
    if (!whatIf.impact) return new Set<string>();
    const roots = whatIf.impact.roots ?? [];
    const owners = new Set(roots.map((r: string) => r.split('.')[0]));
    const affected = whatIf.impact.affected ?? [];
    return new Set([...owners, ...affected]);
  }, [whatIf.impact]);

  const connectedIds = wfActive ? wfConnectedIds
    : derivationActive ? derived!.ids : focus.ids;

  const hasSelection = wfActive || derivationActive || !!(selectedReqId || hoveredNodeId);

  // Fidelity drops automatically on big graphs — see PERF_NODE_LIMIT.
  const perfMode = initialNodes.length > PERF_NODE_LIMIT;

  const dimmedEdges = useMemo(() => {
    if (!hasSelection) return edges;
    return edges.map((e) => {
      // Both ends must be in the highlighted neighbourhood. By default only
      // radial edges (endpoints at different hop distances) light — the paths
      // fanning out from the focus. With "show all links" on, same-distance
      // cross-links between neighbours light too.
      const bothIn = connectedIds.has(e.source) && connectedIds.has(e.target);
      // In a derivation trace every link inside the closure is part of the
      // story, so they all light. Otherwise: radial edges only by default,
      // and "radial" respects the chosen direction — with an incoming/outgoing
      // filter an edge must also point the way the walk travelled.
      const ds = focus.dist.get(e.source);
      const dt = focus.dist.get(e.target);
      const radial = linkDir === 'out' ? dt === (ds ?? -99) + 1
        : linkDir === 'in' ? ds === (dt ?? -99) + 1
        : ds !== dt;
      const connected = derivationActive
        ? bothIn
        : bothIn && (showAllLinks || radial);
      const stroke = (e.style as any)?.stroke as string | undefined;
      const dashed = ((e.style as any)?.strokeDasharray ?? 'none') !== 'none';
      return {
        ...e,
        data: { ...e.data, showLabel: connected },
        // Highlighted dashed relations drift slowly along their direction.
        className: connected && dashed && !perfMode ? 'rt-drift' : undefined,
        style: {
          ...(e.style as Record<string, any>),
          opacity: connected ? Math.max((e.style as any)?.opacity || 0.55, 0.9) : 0.04,
          // A hint of bloom on active edges — just enough to trace them.
          // (Skipped in perf mode: SVG filters force slow re-rasterisation.)
          filter: connected && stroke && !perfMode ? `drop-shadow(0 0 2px ${stroke})` : undefined,
        },
      };
    });
  }, [edges, hasSelection, connectedIds, focus, showAllLinks, perfMode, linkDir, derivationActive]);

  const handleNodeDoubleClick = useCallback(
    (node: Node) => {
      // Reveal the inspector first, and for every node — not just ones with
      // children. Double-clicking a leaf otherwise does nothing visible, and on
      // a node *with* children it collapsed the subtree while the detail it had
      // selected stayed hidden behind a shut pane.
      selectReq(node.id);
      openContext();
      if (!(node.data as any).hasChildren) return;
      // Collapsing via double-click re-frames the node too (expanding is handled
      // by the expand choreography). Double-click doesn't change the selection,
      // so no prevSelectedRef seeding is needed.
      if ((node.data as any).collapsed === false) refocusRef.current = node.id;
      setGroupsOnly(prev => { const n = new Set(prev); n.delete(node.id); return n; });
      setCollapsed(prev => { const next = new Set(prev); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; });
    },
    [selectReq, openContext],
  );

  // Double-click is detected here rather than through ReactFlow's
  // onNodeDoubleClick, which never fires for these nodes: the first click
  // selects, the node re-renders with its selected styling, and the browser
  // only emits `dblclick` when both clicks land on the *same* DOM element.
  // Measured on the running app — two onNodeClick calls, zero onNodeDoubleClick
  // — which also means the collapse-on-double-click this was meant to drive has
  // never worked. Timing beats the DOM here because the ref survives re-render.
  const lastClickRef = useRef<{ id: string; t: number }>({ id: '', t: 0 });
  const DOUBLE_CLICK_MS = 400;

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const now = Date.now();
      const prev = lastClickRef.current;
      const isDouble = prev.id === node.id && now - prev.t < DOUBLE_CLICK_MS;
      lastClickRef.current = { id: node.id, t: isDouble ? 0 : now };

      if (isDouble) { handleNodeDoubleClick(node); return; }

      if (selectedReqId === node.id) navigate(`/project/${projectId}/requirements/${node.id}`);
      else { selectReq(node.id); setHoveredNodeId(null); }
    },
    [navigate, projectId, selectedReqId, selectReq, handleNodeDoubleClick],
  );


  const onPaneClick = useCallback(() => { selectReq(null); setHoveredNodeId(null); setHoveredEntity(null); }, [selectReq, setHoveredEntity]);
  const handleNodeEnter = useCallback((_: React.MouseEvent, node: Node) => {
    // Cross-highlight is cheap (targeted node updates) so it runs in perf mode;
    // the neighbourhood highlight below is the one gated there.
    setHoveredEntity({ kind: 'requirement', id: node.id });
    if (perfMode) return;
    if (!selectedReqId && !animatingRef.current) setHoveredNodeId(node.id);
  }, [selectedReqId, perfMode, setHoveredEntity]);
  const handleNodeLeave = useCallback(() => { setHoveredNodeId(null); setHoveredEntity(null); }, [setHoveredEntity]);

  // ── Cross-highlight (shared hover) ───────────────────────────────────────
  // The hovered entity lives in Layout (see HoveredEntityCtx). Highlight the
  // corresponding node(s) here by toggling `crossHighlighted` on their data —
  // targeted, so only the affected nodes re-render, never the whole graph.
  const crossHighlightRef = useRef<Set<string>>(new Set());
  const crossTargetIds = useMemo(() => {
    if (!hoveredEntity) return new Set<string>();
    if (hoveredEntity.kind === 'requirement') return new Set([hoveredEntity.id]);
    if (hoveredEntity.kind === 'component') {
      return new Set(requirementsSatisfiedByComponent(hoveredEntity.id, components));
    }
    return new Set<string>();
  }, [hoveredEntity, components]);

  useEffect(() => {
    const prev = crossHighlightRef.current;
    const next = crossTargetIds;
    const affected = new Set([...prev, ...next]);
    if (affected.size === 0) return;
    crossHighlightRef.current = next;
    setNodes((nds) => nds.map((n) => {
      if (!affected.has(n.id)) return n;
      const now = next.has(n.id);
      const was = !!(n.data as any).crossHighlighted;
      if (was === now) return n;
      return { ...n, data: { ...n.data, crossHighlighted: now } };
    }));
  }, [crossTargetIds, setNodes]);

  // Stable context value: without the memo every GraphPane render hands all
  // nodes a fresh object and forces a full node re-render pass.
  const selectionCtxValue = useMemo(
    () => ({ connectedIds, selectedReqId, hasSelection }),
    [connectedIds, selectedReqId, hasSelection],
  );

  return (
    <div
      ref={graphBoxRef}
      className={`w-full h-full bg-background relative @container${perfMode ? ' rt-perf' : ''}`}
      // Subtle centre glow for depth so node blooms read against some atmosphere.
      // ReactFlow is transparent, so this backdrop shows through behind the nodes.
      style={{ background: 'radial-gradient(ellipse at 50% 38%, hsl(var(--foreground) / 0.035), transparent 62%), hsl(var(--background))' }}
    >
    {/* The remount key lives on this inner wrapper, NOT the outer div: the
        splash must survive the swap so the old diagram fades straight into
        the new one with no uncovered frame in between. */}
    <div className="w-full h-full">
    <GraphSelectionCtx.Provider value={selectionCtxValue}>
      <ReactFlow
        nodes={nodes}
        edges={dimmedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeMouseEnter={handleNodeEnter}
        onNodeMouseLeave={handleNodeLeave}
        onPaneClick={onPaneClick}
        onEdgeClick={(_event, edge) => {
          if (!selectedReqId) return;
          const otherNode = edge.source === selectedReqId ? edge.target : edge.source;
          selectReq(otherNode);
        }}
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
        // Viewport culling: on big graphs only nodes/edges inside the view
        // are mounted, so zoomed-in work stays fast no matter the graph size.
        // Off for small graphs — the per-move visibility pass isn't free.
        onlyRenderVisibleElements={perfMode}
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

        {/* Hidden below @lg (512px): on a narrow pane the minimap eats a third
            of the canvas and collides with the bottom status text. Skipped
            entirely in perf mode — it redraws every node on every viewport
            move, which is exactly the work a big graph can't afford. */}
        {!perfMode && (
          <MiniMap
            nodeColor={(node) => statusMinimapColors[(node.data?.status as string) || 'proposed'] || '#64748b'}
            bgColor="hsl(var(--graph-minimap))"
            maskColor="hsl(var(--graph-minimap) / 0.9)"
            className="!bg-graph-minimap !border-graph-border rounded-lg overflow-hidden shadow-lg !hidden @lg:!block"
            nodeBorderRadius={3} pannable zoomable
          />
        )}

        {/* flex-wrap + max-w: the toolbar folds to extra rows on a narrow pane
            instead of overflowing off-canvas. The @2xl cap reserves ~200px on
            the right for the legend once it becomes visible. */}
        <Panel position="top-left" className="ml-2 mt-2 mr-2 flex flex-wrap items-center gap-2 max-w-[calc(100%-1rem)] @2xl:max-w-[calc(100%-14rem)]">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-graph-muted" />
            <input
              className="pl-7 pr-2.5 py-1.5 w-32 @lg:w-44 rounded-lg bg-graph-panel border border-graph-border text-xs text-graph-text placeholder:text-graph-muted outline-none focus:ring-1 focus:ring-ring/20 transition-all shadow-sm"
              placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="relative">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`relative p-1.5 rounded-lg border shadow-sm transition-all ${
                showFilters || hasActiveFilters
                  ? 'bg-accent text-foreground border-graph-border'
                  : 'bg-graph-panel border-graph-border text-graph-text hover:bg-graph-control-hover'
              }`}
              title="Filters"
            >
              <Filter size={13} />
              {activeFilterCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-[15px] h-[15px] px-1 rounded-full bg-primary text-primary-foreground text-[9px] font-semibold flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </button>
            {showFilters && (
              <div className="absolute top-full left-0 mt-1.5 z-50 w-60 max-w-[calc(100cqw-1.5rem)] rounded-xl bg-graph-panel border border-graph-border shadow-2xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-semibold text-graph-text uppercase tracking-wider">Filters</span>
                  <button onClick={() => setShowFilters(false)} className="text-graph-muted hover:text-graph-text" aria-label="Close filters" title="Close filters">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                </div>
                <div className="space-y-2.5 max-h-[60vh] overflow-y-auto pr-0.5">
                  <FilterField label="Status" options={availableStatuses} value={filterStatus} onChange={setFilterStatus} colorOf={statusOptionColor} />
                  <FilterField label="Priority" options={availablePriorities} value={filterPriority} onChange={setFilterPriority} colorOf={priorityOptionColor} />
                  {availableBaselines.length > 0 && (
                    <div>
                      <div className="text-[9px] text-graph-muted mb-1">Baselines</div>
                      <div className="space-y-0.5 max-h-32 overflow-y-auto">
                        {availableBaselines.map((b) => {
                          const checked = !hiddenBaselines.includes(b);
                          return (
                            <label key={b} className="flex items-center gap-1.5 py-0.5 cursor-pointer hover:bg-graph-control-hover rounded px-1 transition-colors">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleHiddenBaseline(b)}
                                className="w-3 h-3 rounded border-graph-border accent-graph-text cursor-pointer"
                              />
                              <span className="text-[11px] text-graph-text">{b}</span>
                              <span className="text-[9px] text-graph-muted ml-auto">
                                {reqs.filter(r => r.baselines?.includes(b)).length}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  <FilterField label="Type" options={availableTypes} value={filterType} onChange={setFilterType} format={formatReqType} colorOf={typeOptionColor} />
                  <FilterField label="Verification status" options={availableVerStatuses} value={filterVerStatus} onChange={setFilterVerStatus} colorOf={verifStatusOptionColor} />
                  <FilterField label="Verification method" options={availableVerMethods} value={filterVerMethod} onChange={setFilterVerMethod} />
                  <FilterField label="Allocated team" options={availableAllocations} value={filterAllocated} onChange={setFilterAllocated} />
                  {availableComponents.length > 0 && (
                    <div>
                      <div className="text-[9px] text-graph-muted mb-1">Components</div>
                      <div className="space-y-0.5 max-h-32 overflow-y-auto">
                        {availableComponents.map((cid) => {
                          const checked = !effectiveHidden.has(cid);
                          const label = componentLabels.get(cid) || cid;
                          const reqCount = components.find(c => c.id === cid)?.satisfies?.length ?? 0;
                          const inherited = effectiveHidden.has(cid) && !hiddenComponents.includes(cid);
                          return (
                            <label key={cid} className="flex items-center gap-1.5 py-0.5 cursor-pointer hover:bg-graph-control-hover rounded px-1 transition-colors">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleHiddenComponent(cid)}
                                className="w-3 h-3 rounded border-graph-border accent-graph-text cursor-pointer disabled:opacity-50 disabled:cursor-default"
                                disabled={inherited}
                              />
                              <span className="text-[11px] text-graph-text truncate max-w-[140px]">{label}</span>
                              <span className="text-[9px] text-graph-muted ml-auto shrink-0" title={`Satisfies ${reqCount} requirements`}>{reqCount}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
                {hasActiveFilters && (
                  <div className="mt-3 pt-3 border-t border-graph-border">
                    <button onClick={clearFilters}
                      className="w-full text-[10px] text-graph-muted hover:text-graph-text hover:bg-graph-control-hover rounded py-1 transition-colors">
                      Clear all filters ({filteredReqs.length}/{reqs.length} visible)
                    </button>
                  </div>
                )}
              </div>
            )}
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
              <div className="absolute top-full left-0 mt-1.5 z-50 w-64 max-w-[calc(100cqw-1.5rem)] rounded-xl bg-graph-panel border border-graph-border shadow-2xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-semibold text-graph-text uppercase tracking-wider">Layout Settings</span>
                  <button onClick={() => setShowSettings(false)} className="text-graph-muted hover:text-graph-text" aria-label="Close layout settings" title="Close layout settings">
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
          <div className="flex rounded-lg bg-graph-panel border border-graph-border shadow-sm overflow-hidden">
            <button
              onClick={expandAll}
              className="p-1.5 text-graph-text hover:text-foreground hover:bg-graph-control-hover transition-colors"
              title="Expand all"
            >
              <ChevronsUpDown size={13} />
            </button>
            <button
              onClick={collapseAll}
              className="p-1.5 text-graph-text hover:text-foreground hover:bg-graph-control-hover transition-colors border-l border-graph-border"
              title="Collapse all"
            >
              <ChevronsDownUp size={13} />
            </button>
          </div>
          <button
            onClick={() => setHideRoots((v) => !v)}
            className={`p-1.5 rounded-lg border shadow-sm transition-colors ${
              hideRoots
                ? 'bg-primary/15 text-primary border-primary/30'
                : 'bg-graph-panel text-graph-text border-graph-border hover:text-foreground hover:bg-graph-control-hover'
            }`}
            title={hideRoots ? 'Show root nodes' : 'Hide root nodes (no parent)'}
          >
            <EyeOff size={13} />
          </button>
          {/* Highlight radius: how many relationship hops out from the selected
              node stay lit (1 = direct neighbours only, up to 3). Hidden on
              very narrow panes — it's a persisted power-user pref, and the
              toolbar must fold to two rows at the 320px floor, not three. */}
          <div
            className="hidden @md:flex items-center rounded-lg bg-graph-panel border border-graph-border shadow-sm overflow-hidden"
            title="Highlight radius — hops from the selected node to keep lit"
          >
            <span className="pl-2 pr-1 text-graph-muted" aria-hidden><Waypoints size={13} /></span>
            {[1, 2, 3].map((n) => (
              <button
                key={n}
                onClick={() => setHopDepthPersist(n)}
                className={`px-2 py-1.5 text-[11px] font-mono border-l border-graph-border transition-colors ${
                  hopDepth === n ? 'bg-primary text-primary-foreground' : 'text-graph-text hover:bg-graph-control-hover'
                }`}
                title={`Highlight ${n} hop${n > 1 ? 's' : ''} out`}
                aria-pressed={hopDepth === n}
              >
                {n}
              </button>
            ))}
          </div>
          {/* Link direction: whether the highlight follows relationships out
              of the focused node, into it, or both ways (the default). */}
          <div
            className="hidden @md:flex items-center rounded-lg bg-graph-panel border border-graph-border shadow-sm overflow-hidden"
            title="Link direction — which relationships the highlight follows"
          >
            {([
              { id: 'both', icon: ArrowLeftRight, label: 'Both directions' },
              { id: 'in', icon: ArrowDownLeft, label: 'Incoming links only' },
              { id: 'out', icon: ArrowUpRight, label: 'Outgoing links only' },
            ] as const).map(({ id, icon: Icon, label }, i) => (
              <button
                key={id}
                onClick={() => setLinkDirPersist(id)}
                className={`p-1.5 transition-colors ${i > 0 ? 'border-l border-graph-border' : ''} ${
                  linkDir === id ? 'bg-primary text-primary-foreground' : 'text-graph-text hover:bg-graph-control-hover'
                }`}
                title={label}
                aria-pressed={linkDir === id}
              >
                <Icon size={13} />
              </button>
            ))}
          </div>
          {/* Toggle: also light cross-links between same-distance highlighted
              neighbours, not just the radial paths from the focused node. */}
          <button
            onClick={toggleAllLinks}
            className={`hidden @md:block p-1.5 rounded-lg border shadow-sm transition-all ${
              showAllLinks
                ? 'bg-primary text-primary-foreground border-graph-border'
                : 'bg-graph-panel border-graph-border text-graph-text hover:bg-graph-control-hover'
            }`}
            title={showAllLinks
              ? 'Showing all links between highlighted nodes — click for radial paths only'
              : 'Show all links between highlighted nodes (incl. cross-links)'}
            aria-pressed={showAllLinks}
          >
            <Share2 size={13} />
          </button>
          {/* Toggle: hoist relationship edges whose endpoint is hidden by a
              collapsed group up to that group, so the line still reaches it
              instead of silently disappearing. */}
          <button
            onClick={toggleHoistEdges}
            className={`hidden @md:block p-1.5 rounded-lg border shadow-sm transition-all ${
              hoistEdgesEnabled
                ? 'bg-primary text-primary-foreground border-graph-border'
                : 'bg-graph-panel border-graph-border text-graph-text hover:bg-graph-control-hover'
            }`}
            title={hoistEdgesEnabled
              ? 'Hoisting hidden edges to collapsed groups — click to hide them'
              : 'Hidden edges are dropped — click to hoist them to collapsed groups'}
            aria-label="Toggle hoisted edges"
            aria-pressed={hoistEdgesEnabled}
          >
            <GitMerge size={13} />
          </button>
          {/* Saved view slots: click a filled slot to jump to it, an empty slot
              to save the current view. Shift-click overwrites; right-click clears. */}
          <div
            className="hidden @lg:flex items-center rounded-lg bg-graph-panel border border-graph-border shadow-sm overflow-hidden"
            title="Saved views — click to jump, shift-click to save, right-click to clear"
          >
            <span className="pl-2 pr-1 text-graph-muted" aria-hidden><Save size={13} /></span>
            {Array.from({ length: VIEW_SLOTS }, (_, i) => {
              const filled = !!views[i];
              return (
                <button
                  key={i}
                  onClick={(e) => { if (e.shiftKey || !filled) saveView(i); else restoreView(i); }}
                  onContextMenu={(e) => { e.preventDefault(); if (filled) clearView(i); }}
                  className={`px-2 py-1.5 text-[11px] font-mono border-l border-graph-border transition-colors ${
                    filled ? 'bg-primary/15 text-primary hover:bg-primary/25' : 'text-graph-muted hover:bg-graph-control-hover'
                  }`}
                  title={filled
                    ? `Jump to view ${i + 1} · shift-click to overwrite · right-click to clear`
                    : `Save current view to slot ${i + 1}`}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
          <button onClick={loadData} className="p-1.5 rounded-lg bg-graph-panel border border-graph-border text-graph-text hover:text-foreground hover:bg-graph-control-hover transition-colors shadow-sm" title="Refresh">
            <RotateCw size={13} />
          </button>
          <button onClick={resetView} className="p-1.5 rounded-lg bg-graph-panel border border-graph-border text-graph-text hover:text-foreground hover:bg-graph-control-hover transition-colors shadow-sm" title="Reset view" aria-label="Reset view">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          </button>
        </Panel>

        {/* Relations legend — reference chrome; below @2xl it would collide
            with the (wrapping) toolbar, so it only appears on wider panes. */}
        <Panel position="top-right" className="mr-2 mt-2 hidden @2xl:block">
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

        <Panel position="bottom-center" className="mb-3 max-w-[94cqw] flex flex-col items-center gap-1.5">
          {/* A derivation trace is a modal-ish view: say so, and give it an
              exit that isn't "click something else and hope". It rides above
              the status chip — the top-left toolbar wraps into the top-centre
              slot on narrow panes, so a banner up there would collide. */}
          {derivationActive && (
            <div className="flex items-center gap-2 rounded-lg bg-primary/15 border border-primary/40 px-2.5 py-1.5 shadow-sm text-[11px] text-foreground max-w-full">
              <Waypoints size={12} className="text-primary shrink-0" />
              <span className="truncate">
                Derivation of <span className="font-mono">{derived!.root}</span> —{' '}
                {derived!.ids.size - 1} contributing requirement{derived!.ids.size === 2 ? '' : 's'}
              </span>
              <button
                onClick={() => setDerived(null)}
                className="shrink-0 rounded px-1 text-graph-muted hover:text-foreground hover:bg-graph-control-hover"
                title="Clear derivation trace"
                aria-label="Clear derivation trace"
              >
                <svg width="11" height="11" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
              </button>
            </div>
          )}
          <div className="text-[10px] text-graph-text bg-graph-panel border border-graph-border rounded-lg px-2.5 py-1.5 shadow-sm flex items-center gap-2 whitespace-nowrap overflow-hidden max-w-full">
            {layoutMode === 'uml' && (
              <>
                <ZoomLevelChip />
                <span className="opacity-40">|</span>
              </>
            )}
            <span>
              {filteredReqs.length}{filteredReqs.length !== reqs.length ? ` / ${reqs.length}` : ''} requirements · {initialEdges.length} edges
              <span className="hidden @xl:inline"> · click to select · dbl-click expand</span>
            </span>
            {perfMode && (
              <span
                className="text-graph-muted"
                title={`Performance mode — over ${PERF_NODE_LIMIT} nodes on screen: glow/animations off, offscreen nodes unrendered, hover highlight off (click still highlights)`}
              >
                · ⚡ perf
              </span>
            )}
          </div>
        </Panel>
      </ReactFlow>
      </GraphSelectionCtx.Provider>
      </div>

      {splash && <LoadingSplash label="Loading graph…" leaving={splash === 'leaving'} />}

      <style>{`
        /* No global transform transition: nodes appear at their final layout
           position and fade in (opacity). A position *slide* is opted into
           inline, per-node, only during the expand/collapse choreography. */
        .react-flow__node { font-family: var(--font-sans); }
        .react-flow__edge-path { transition: stroke-opacity 0.2s, opacity 0.25s ease, filter 0.25s ease; }
        @keyframes retractEdge { to { stroke-dashoffset: var(--edge-len); } }
        @keyframes growEdge { from { stroke-dashoffset: var(--edge-len); } to { stroke-dashoffset: 0; } }
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
        /* Shared node keyframes, hoisted here so BlockNode/CircularNode don't
           each inject a per-instance <style> tag (one per node adds up). */
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes scrollDesc {
          0%, 15% { transform: translateY(0); }
          85%, 100% { transform: translateY(min(0px, calc(-100% + var(--desc-h, 46px)))); }
        }
        @keyframes rtPulse {
          0%, 100% { filter: drop-shadow(0 0 6px currentColor) drop-shadow(0 0 14px currentColor) !important; }
          50% { filter: drop-shadow(0 0 16px currentColor) drop-shadow(0 0 28px currentColor) !important; }
        }
        .rt-pulse {
          animation: rtPulse 0.6s ease-in-out infinite;
        }
        /* Nodes are absolutely positioned islands: containment tells the
           browser a node's internal layout/style can't leak out, shrinking
           invalidation scope during pan/zoom. (No 'paint' — tooltips and side
           labels intentionally overflow node bounds.) */
        .react-flow__node { contain: layout style; }
        /* Performance mode (rt-perf, set above PERF_NODE_LIMIT nodes): kill the
           per-node drop-shadow glows — SVG-style filters force every frame of
           a pan/zoom to re-rasterise instead of compositing on the GPU — and
           every infinite animation (desc scrollers, pulse rings, edge drift).
           !important is required to beat the inline styles. */
        .rt-perf .react-flow__node div {
          filter: none !important;
          animation: none !important;
          transition: none !important;
        }
        .rt-perf .react-flow__edge-path { animation: none !important; filter: none !important; }
      `}</style>
    </div>
  );
}

/** A labelled full-width dropdown for the Filters popover. Hides itself when
 *  there are no options (e.g. a project with no components or teams). */
function FilterField({ label, options, value, onChange, format, colorOf }: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  format?: (v: string) => string;
  colorOf?: (v: string) => string | undefined;
}) {
  if (options.length === 0) return null;
  const selectedColor = value ? colorOf?.(value) : undefined;
  return (
    <div>
      <div className="text-[9px] text-graph-muted mb-1">{label}</div>
      <select
        className="w-full appearance-none pl-2 pr-6 py-1.5 rounded-lg bg-graph-panel border border-graph-border text-[11px] text-graph-text outline-none focus:ring-1 focus:ring-ring/20 transition-all cursor-pointer hover:bg-graph-control-hover"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%236b7280'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 6px center',
          color: selectedColor,
          fontWeight: selectedColor ? 600 : undefined,
        }}
        aria-label={label}
      >
        <option value="" style={{ color: 'hsl(var(--graph-panel-text))' }}>All</option>
        {options.map((o) => {
          const c = colorOf?.(o);
          return (
            <option key={o} value={o} style={c ? { color: c } : undefined}>
              {format ? format(o) : o}
            </option>
          );
        })}
      </select>
    </div>
  );
}
