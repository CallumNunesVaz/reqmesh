import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  PanelLeftClose,
  PanelLeft,
  Search,
  X,
  ChevronRight,
  ClipboardList,
  FileText,
  CheckCircle2,
  GitBranch,
  Home,
  ChevronDown,
  GitPullRequest,
  AlertTriangle,
  BarChart3,
  Boxes,
} from 'lucide-react';
import { api, type RequirementTreeNode } from '../api/client';
import { useStore } from '../store';
import { useSelectedReq } from './Layout';

const statusDots: Record<string, string> = {
  proposed: 'bg-blue-400',
  approved: 'bg-green-400',
  implemented: 'bg-purple-400',
  verified: 'bg-emerald-400',
  rejected: 'bg-red-400',
  deprecated: 'bg-zinc-400',
};

function TreeNode({
  node,
  depth,
  projectId,
  navigate,
  currentPath,
  selectedReqId,
  onSelect,
}: {
  node: RequirementTreeNode;
  depth: number;
  projectId: string;
  navigate: (path: string) => void;
  currentPath: string;
  selectedReqId: string | null;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  const isRouteActive = currentPath.endsWith(`/requirements/${node.id}`);
  const isSelected = selectedReqId === node.id || isRouteActive;

  useEffect(() => {
    if (!selectedReqId || !hasChildren) return;
    const hasDescendant = (n: RequirementTreeNode): boolean =>
      n.id === selectedReqId || n.children.some(hasDescendant);
    if (hasDescendant(node)) setExpanded(true);
  }, [selectedReqId, hasChildren, node]);

  return (
    <div id={`nav-${node.id}`}>
      <button
        onClick={() => {
          onSelect(node.id);
          navigate(`/project/${projectId}/requirements/${node.id}`);
        }}
        className={`flex items-center gap-1.5 w-full pr-2 py-1 text-xs rounded-md transition-all group ${
          isSelected
            ? 'bg-primary/10 text-primary'
            : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'
        }`}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {hasChildren ? (
          <span
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="p-0.5 rounded hover:bg-sidebar-accent shrink-0 text-muted-foreground"
          >
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </span>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDots[node.status] || 'bg-zinc-400'}`} />
        <span className="font-mono shrink-0 text-[10px] opacity-50">{node.id}</span>
        <span className="truncate flex-1 text-left pl-1">{node.name || 'Untitled'}</span>
      </button>
      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              projectId={projectId}
              navigate={navigate}
              currentPath={currentPath}
              selectedReqId={selectedReqId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Contextual panel: the tree under the nav follows the active section ──────
// Requirements keep the requirement hierarchy; Specifications show the spec
// breakdown, Components the physical tree, and the record sections (VCs,
// traces, changes, risks) show their lists — all filterable, all deep-linking.

type Section = 'requirements' | 'specifications' | 'components' | 'verification' | 'traces' | 'changes' | 'risks';

const SECTION_TITLES: Record<Section, string> = {
  requirements: 'Hierarchy',
  specifications: 'Specifications',
  components: 'Component Tree',
  verification: 'Verification Cases',
  traces: 'Trace Links',
  changes: 'Change Requests',
  risks: 'Risks',
};

function sectionFor(pathname: string): Section {
  if (pathname.includes('/specifications')) return 'specifications';
  if (pathname.includes('/components')) return 'components';
  if (pathname.includes('/verification')) return 'verification';
  if (pathname.includes('/traces')) return 'traces';
  if (pathname.includes('/change-requests')) return 'changes';
  if (pathname.includes('/risks')) return 'risks';
  return 'requirements';
}

interface PanelItem {
  id: string;
  label: string;
  sub?: string;
  /** Tailwind bg-* class for the status dot. */
  dot: string;
  to: string;
  children: PanelItem[];
  /** Trace rows put both ids in the label; suppress the id column. */
  showId?: boolean;
}

const COMPONENT_DOTS: Record<string, string> = {
  system: 'bg-blue-400', subsystem: 'bg-purple-400', assembly: 'bg-orange-400',
  part: 'bg-green-400', software: 'bg-teal-400', interface: 'bg-pink-400',
};
const VC_DOTS: Record<string, string> = {
  passed: 'bg-green-400', failed: 'bg-red-400', in_progress: 'bg-blue-400', pending: 'bg-zinc-400',
};
const CHANGE_DOTS: Record<string, string> = {
  submitted: 'bg-blue-400', in_review: 'bg-amber-400', approved: 'bg-green-400',
  rejected: 'bg-red-400', implemented: 'bg-purple-400',
};
const RISK_DOTS: Record<string, string> = {
  critical: 'bg-red-400', high: 'bg-orange-400', medium: 'bg-amber-400', low: 'bg-zinc-400',
};

function filterPanel(items: PanelItem[], q: string): PanelItem[] {
  if (!q) return items;
  const lower = q.toLowerCase();
  return items.reduce<PanelItem[]>((acc, item) => {
    const matches = item.id.toLowerCase().includes(lower) || item.label.toLowerCase().includes(lower);
    const kids = filterPanel(item.children, q);
    if (matches || kids.length > 0) acc.push({ ...item, children: kids });
    return acc;
  }, []);
}

function countPanel(items: PanelItem[]): number {
  return items.reduce((c, i) => c + 1 + countPanel(i.children), 0);
}

function PanelNode({ item, depth, navigate, focusId }: {
  item: PanelItem; depth: number; navigate: (to: string) => void; focusId: string | null;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = item.children.length > 0;
  const isSelected = focusId === item.id;

  return (
    <div>
      <button
        onClick={() => navigate(item.to)}
        className={`flex items-center gap-1.5 w-full pr-2 py-1 text-xs rounded-md transition-all ${
          isSelected ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'
        }`}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {hasChildren ? (
          <span
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="p-0.5 rounded hover:bg-sidebar-accent shrink-0 text-muted-foreground"
          >
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </span>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${item.dot}`} />
        {item.showId !== false && <span className="font-mono shrink-0 text-[10px] opacity-50">{item.id}</span>}
        <span className="truncate flex-1 text-left pl-1">{item.label}</span>
        {item.sub && <span className="shrink-0 text-[9px] text-muted-foreground opacity-70">{item.sub}</span>}
      </button>
      {expanded && hasChildren && (
        <div>
          {item.children.map((child) => (
            <PanelNode key={child.id} item={child} depth={depth + 1} navigate={navigate} focusId={focusId} />
          ))}
        </div>
      )}
    </div>
  );
}

interface RequirementNavProps {
  width?: number;
  /** Collapse state lives in Layout, which owns the pane's width — the
      container must actually give the space back to the canvas. */
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function RequirementNav({ width = 300, collapsed, onToggleCollapse }: RequirementNavProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [tree, setTree] = useState<RequirementTreeNode[]>([]);
  // Items are tagged with the section they were loaded for, so switching
  // sections never briefly shows the previous section's rows.
  const [panel, setPanel] = useState<{ section: Section; items: PanelItem[] }>({ section: 'requirements', items: [] });
  const [search, setSearch] = useState('');
  const { selectedReqId, selectReq } = useSelectedReq();
  const dataVersion = useStore((s) => s.dataVersion);

  const section = sectionFor(location.pathname);
  const focusId = new URLSearchParams(location.search).get('focus');

  useEffect(() => {
    if (!projectId) return;
    api.getRequirementTree(projectId).then(setTree).catch(console.error);
  }, [projectId, dataVersion]);

  useEffect(() => {
    if (!selectedReqId) return;
    const el = document.getElementById(`nav-${selectedReqId}`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selectedReqId]);

  // The non-requirement sections each load their own list/tree on demand.
  useEffect(() => {
    if (!projectId || section === 'requirements') return;
    let alive = true;
    const set = (items: PanelItem[]) => { if (alive) setPanel({ section, items }); };
    const base = `/project/${projectId}`;

    if (section === 'specifications') {
      api.listSpecifications(projectId).then((specs) => {
        const byId = new Map(specs.map((s) => [s.id, s]));
        const childIds = new Set(specs.flatMap((s) => s.children));
        const build = (s: (typeof specs)[number]): PanelItem => ({
          id: s.id, label: s.name, sub: `${s.requirements.length} reqs`, dot: 'bg-yellow-400',
          to: `${base}/specifications?focus=${encodeURIComponent(s.id)}`,
          children: s.children.map((c) => byId.get(c)).filter((c): c is NonNullable<typeof c> => !!c).map(build),
        });
        set(specs.filter((s) => !childIds.has(s.id)).map(build));
      }).catch(() => set([]));
    } else if (section === 'components') {
      api.listComponents(projectId).then((comps) => {
        const ids = new Set(comps.map((c) => c.id));
        const build = (parent: string | null): PanelItem[] =>
          comps.filter((c) => (c.parent && ids.has(c.parent) ? c.parent : null) === parent).map((c) => ({
            id: c.id, label: c.name,
            sub: c.quantity > 1 ? `${c.type} ×${c.quantity}` : c.type,
            dot: COMPONENT_DOTS[c.type] || 'bg-zinc-400',
            to: `${base}/components/${encodeURIComponent(c.id)}`,
            children: build(c.id),
          }));
        set(build(null));
      }).catch(() => set([]));
    } else if (section === 'verification') {
      api.listVerificationCases(projectId).then((vcs) => set(vcs.map((v) => ({
        id: v.id, label: v.name, sub: v.method, dot: VC_DOTS[v.status] || 'bg-zinc-400',
        to: `${base}/verification?focus=${encodeURIComponent(v.id)}`, children: [],
      })))).catch(() => set([]));
    } else if (section === 'traces') {
      api.getTraces(projectId).then((t) => set((t.links || []).flatMap((l, i) => [
        { id: `${i}-src`, label: `${l.source} → ${l.target}`, sub: l.type, dot: 'bg-blue-400',
          to: `${base}/requirements/${encodeURIComponent(l.source)}`, children: [], showId: false },
        { id: `${i}-tgt`, label: `← ${l.target}`, sub: l.type, dot: 'bg-emerald-400',
          to: `${base}/requirements/${encodeURIComponent(l.target)}`, children: [], showId: false },
      ]))).catch(() => set([]));
    } else if (section === 'changes') {
      api.listChangeRequests(projectId).then((crs) => set(crs.map((c) => ({
        id: c.id, label: c.title, sub: c.status.replace('_', ' '), dot: CHANGE_DOTS[c.status] || 'bg-zinc-400',
        to: `${base}/change-requests?focus=${encodeURIComponent(c.id)}`, children: [],
      })))).catch(() => set([]));
    } else if (section === 'risks') {
      api.listRisks(projectId).then((risks) => set(risks.map((r) => ({
        id: r.id, label: r.title, sub: r.severity, dot: RISK_DOTS[r.severity] || 'bg-zinc-400',
        to: `${base}/risks?focus=${encodeURIComponent(r.id)}`, children: [],
      })))).catch(() => set([]));
    }
    return () => { alive = false; };
  }, [projectId, dataVersion, section]);

  function filterTree(nodes: RequirementTreeNode[], q: string): RequirementTreeNode[] {
    if (!q) return nodes;
    const lower = q.toLowerCase();
    return nodes.reduce<RequirementTreeNode[]>((acc, node) => {
      const matches =
        node.id.toLowerCase().includes(lower) ||
        node.name.toLowerCase().includes(lower);
      const filteredChildren = filterTree(node.children, q);
      if (matches || filteredChildren.length > 0) {
        acc.push({ ...node, children: filteredChildren });
      }
      return acc;
    }, []);
  }

  const filtered = filterTree(tree, search);
  const filteredPanel = filterPanel(panel.section === section ? panel.items : [], search);

  function countNodes(nodes: RequirementTreeNode[]): number {
    return nodes.reduce((c, n) => c + 1 + countNodes(n.children), 0);
  }

  const navItems = [
    { to: `/project/${projectId}`, label: 'Overview', icon: Home },
    { to: `/project/${projectId}/requirements`, label: 'Requirements', icon: ClipboardList },
    { to: `/project/${projectId}/specifications`, label: 'Specifications', icon: FileText },
    { to: `/project/${projectId}/components`, label: 'Components', icon: Boxes },
    { to: `/project/${projectId}/verification`, label: 'Verification', icon: CheckCircle2 },
    { to: `/project/${projectId}/traces`, label: 'Trace Matrix', icon: GitBranch },
    { to: `/project/${projectId}/change-requests`, label: 'Change Requests', icon: GitPullRequest },
    { to: `/project/${projectId}/risks`, label: 'Risks', icon: AlertTriangle },
    { to: `/project/${projectId}/metrics`, label: 'Metrics', icon: BarChart3 },
  ];

  if (collapsed) {
    return (
      <div className="w-10 bg-sidebar border-r h-full shrink-0 flex flex-col items-center py-3 gap-2 z-20">
        <button
          onClick={onToggleCollapse}
          className="p-1.5 rounded-md text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
          title="Expand sidebar"
        >
          <PanelLeft size={16} />
        </button>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.to;
          return (
            <button
              key={item.to}
              onClick={() => navigate(item.to)}
              className={`p-1.5 rounded-md transition-all ${active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'}`}
              title={item.label}
            >
              <Icon size={16} />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <motion.div
      className="bg-sidebar flex flex-col h-full z-20 overflow-hidden"
      animate={{ width }}
      initial={{ width }}
      style={{ width }}
    >
      <div className="p-3 border-b">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Navigate</span>
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded-md text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
            title="Collapse sidebar"
          >
            <PanelLeftClose size={14} />
          </button>
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.to;
          return (
            <button
              key={item.to}
              onClick={() => navigate(item.to)}
              className={`flex items-center gap-2 w-full px-3 py-1.5 text-xs font-medium rounded-lg transition-all mb-0.5 ${
                active
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'
              }`}
            >
              <Icon size={14} />
              {item.label}
            </button>
          );
        })}

        <div className="mt-3 pt-3 border-t">
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="w-full pl-7 pr-6 py-1.5 rounded-md bg-sidebar-accent text-xs text-sidebar-foreground placeholder:text-muted-foreground outline-none border border-transparent focus:border-ring/30 transition-colors"
              placeholder="Filter tree..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-sidebar-foreground">
                <X size={12} />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        <div className="flex items-center justify-between px-2 pt-1 pb-2">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{SECTION_TITLES[section]}</span>
          <span className="text-[10px] text-muted-foreground">
            {section === 'requirements' ? countNodes(filtered) : countPanel(filteredPanel)}
          </span>
        </div>
        {section === 'requirements' ? (
          filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">No requirements found.</p>
          ) : (
            filtered.map((node) => (
              <TreeNode
                key={node.id}
                node={node}
                depth={0}
                projectId={projectId!}
                navigate={navigate}
                currentPath={location.pathname}
                selectedReqId={selectedReqId}
                onSelect={selectReq}
              />
            ))
          )
        ) : filteredPanel.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-4">Nothing found.</p>
        ) : (
          filteredPanel.map((item) => (
            <PanelNode key={item.id} item={item} depth={0} navigate={navigate} focusId={focusId} />
          ))
        )}
      </div>

    </motion.div>
  );
}
