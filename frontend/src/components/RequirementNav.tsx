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
  PanelRight,
  PanelRightClose,
  ChevronDown,
  GitPullRequest,
  AlertTriangle,
  BarChart3,
  Boxes,
} from 'lucide-react';
import { api, type RequirementTreeNode } from '../api/client';
import { useStore } from '../store';
import { useGraphPane, useSelectedReq } from './Layout';

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

  return (
    <div>
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

interface RequirementNavProps { width?: number; }

export default function RequirementNav({ width = 300 }: RequirementNavProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [tree, setTree] = useState<RequirementTreeNode[]>([]);
  const [search, setSearch] = useState('');
  const { graphOpen, toggleGraph } = useGraphPane();
  const { selectedReqId, selectReq } = useSelectedReq();
  const dataVersion = useStore((s) => s.dataVersion);

  useEffect(() => {
    if (!projectId) return;
    api.getRequirementTree(projectId).then(setTree).catch(console.error);
  }, [projectId, dataVersion]);

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

  function countNodes(nodes: RequirementTreeNode[]): number {
    return nodes.reduce((c, n) => c + 1 + countNodes(n.children), 0);
  }

  const navItems = [
    { to: `/project/${projectId}`, label: 'Overview', icon: Home },
    { to: `/project/${projectId}/requirements`, label: 'Requirements', icon: ClipboardList },
    { to: `/project/${projectId}/specifications`, label: 'Specifications', icon: FileText },
    { to: `/project/${projectId}/components`, label: 'Components', icon: Boxes },
    { to: `/project/${projectId}/verification`, label: 'Verification', icon: CheckCircle2 },
    { to: `/project/${projectId}/traces`, label: 'Traces', icon: GitBranch },
    { to: `/project/${projectId}/change-requests`, label: 'Changes', icon: GitPullRequest },
    { to: `/project/${projectId}/risks`, label: 'Risks', icon: AlertTriangle },
    { to: `/project/${projectId}/metrics`, label: 'Metrics', icon: BarChart3 },
  ];

  if (collapsed) {
    return (
      <div className="w-10 bg-sidebar border-r shrink-0 flex flex-col items-center py-3 gap-2 z-20">
        <button
          onClick={() => setCollapsed(false)}
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
        <div className="mt-auto mb-2">
          <button
            onClick={toggleGraph}
            className={`p-1.5 rounded-md transition-all ${graphOpen ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'}`}
            title={graphOpen ? 'Hide graph' : 'Show graph'}
          >
            {graphOpen ? <PanelRightClose size={16} /> : <PanelRight size={16} />}
          </button>
        </div>
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
            onClick={() => setCollapsed(true)}
            className="p-1 rounded-md text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
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
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Hierarchy</span>
          <span className="text-[10px] text-muted-foreground">{countNodes(filtered)}</span>
        </div>
        {filtered.length === 0 ? (
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
        )}
      </div>

      <div className="p-2 border-t">
        <button
          onClick={toggleGraph}
          className={`flex items-center gap-2 w-full px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
            graphOpen
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent'
          }`}
        >
          {graphOpen ? <PanelRightClose size={14} /> : <PanelRight size={14} />}
          {graphOpen ? 'Hide Graph' : 'Show Graph'}
        </button>
      </div>
    </motion.div>
  );
}
