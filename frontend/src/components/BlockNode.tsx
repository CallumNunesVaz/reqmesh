import { memo, useState } from 'react';
import { Handle, Position, useStore, type NodeProps } from '@xyflow/react';
import { ChevronDown, ChevronUp, ChevronsUp, Minus, FlaskConical, Sigma } from 'lucide-react';
import { useGraphSelection } from './GraphPane';
import { statusColors } from './RequirementNode';
import { glow } from './graphColors';
import { zoomLevel, labelScale, type ZoomLevel } from './semanticZoom';

// UML/SysML block node for the diagram canvas. What it renders depends on the
// canvas altitude (semantic zoom): far out only the name survives; close in it
// grows stereotype, parameter and constraint compartments like a SysML block.

const priorityIndicators: Record<string, { color: string; icon: typeof ChevronUp }> = {
  low: { color: 'hsl(195,6%,62%)', icon: ChevronDown },
  medium: { color: 'hsl(207,90%,64%)', icon: Minus },
  high: { color: 'hsl(28,100%,53%)', icon: ChevronUp },
  critical: { color: 'hsl(0,84%,68%)', icon: ChevronsUp },
};

const constraintColors: Record<string, string> = {
  pass: 'hsl(179,100%,38%)',
  fail: 'hsl(0,84%,68%)',
  error: 'hsl(0,84%,68%)',
  unknown: 'hsl(45,90%,55%)',
  not_applicable: 'hsl(195,6%,62%)',
};

export interface BlockParam {
  name: string;
  /** Pre-formatted `= 1157 kg` / `= expr → 390 kg` display string. */
  display: string;
  derived: boolean;
  measured: boolean;
}

export interface BlockConstraint {
  expr: string;
  status: string;
}

export interface BlockNodeData {
  label: string;
  name: string;
  status: string;
  priority: string;
  type: string;
  cascadeFrom: string | null;
  hasChildren: boolean;
  collapsed: boolean;
  childCount?: number;
  onExpandCollapse?: () => void;
  elkHeight?: number;
  params: BlockParam[];
  constraints: BlockConstraint[];
  verdict: string | null;
  vcCount: number;
  desc: string;
}

export const BLOCK_W = 216;

function BlockNode({ data }: NodeProps) {
  const d = data as unknown as BlockNodeData;
  const [hover, setHover] = useState(false);
  const { connectedIds, selectedReqId, hasSelection } = useGraphSelection();
  // Selector returns the bucketed level, so nodes re-render only when the
  // zoom crosses a threshold — not on every wheel tick.
  const level: ZoomLevel = useStore((s) => zoomLevel(s.transform[2]));
  // Map-label trick for far-out altitudes (see semanticZoom.labelScale).
  const textScale = useStore((s) => labelScale(s.transform[2]));

  const colors = statusColors[d.status] || statusColors.proposed;
  const prio = priorityIndicators[d.priority] || priorityIndicators.medium;
  const PriorityIcon = prio.icon;
  const dimmed = hasSelection && !connectedIds.has(d.label);
  const isSelected = selectedReqId === d.label;
  const verdictColor = d.verdict ? constraintColors[d.verdict] || constraintColors.unknown : null;

  const glowFilter = isSelected
    ? `drop-shadow(0 0 9px ${glow(colors.fill, 0.4)}) drop-shadow(0 3px 8px rgba(0,0,0,0.35))`
    : hover
      ? `drop-shadow(0 0 7px ${glow(colors.fill, 0.28)}) drop-shadow(0 2px 6px rgba(0,0,0,0.3))`
      : `drop-shadow(0 0 3px ${glow(colors.fill, 0.13)}) drop-shadow(0 1px 3px rgba(0,0,0,0.22))`;

  const handles = (
    <>
      <Handle type="target" position={Position.Left} id="l" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Right} id="r" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Left} id="sl" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="sr" style={{ opacity: 0 }} />
    </>
  );

  // When a group is collapsed, its children are hidden — hint at the folded
  // subtree with a diagonal stack of same-size cards peeking out behind.
  const showStack = d.hasChildren && d.collapsed;
  const stackCard = (offset: number, op: number) => (
    <div
      className="absolute rounded-md border bg-card"
      style={{
        inset: 0,
        transform: `translate(${offset}px, ${offset}px)`,
        borderColor: 'hsl(var(--border))',
        opacity: (dimmed ? 0.18 : 1) * op,
        boxShadow: '0 1px 3px rgba(0,0,0,0.22)',
        pointerEvents: 'none',
      }}
    />
  );

  const frame = (children: React.ReactNode, clip = true) => (
    <div style={{ position: 'relative', width: BLOCK_W }}>
      {showStack && (
        <>
          {stackCard(11, 0.5)}
          {stackCard(6, 0.75)}
        </>
      )}
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        className={`relative rounded-md border bg-card ${clip ? 'overflow-hidden' : ''}`}
        style={{
          width: BLOCK_W,
          minHeight: minNodeH,
          opacity: dimmed ? 0.18 : 1,
          filter: glowFilter,
          borderColor: isSelected ? colors.fill : hover ? 'hsl(var(--foreground) / 0.3)' : 'hsl(var(--border))',
          boxShadow: isSelected ? `0 0 0 1px ${colors.fill}` : undefined,
          transition: 'opacity 0.25s ease, filter 0.25s ease, border-color 0.2s ease',
          cursor: 'pointer',
        }}
      >
        {handles}
        {children}
      </div>
    </div>
  );

  const shortName = (max: number) => {
    const n = d.name || d.label;
    return n.length > max ? n.slice(0, max - 1) + '…' : n;
  };

  const minNodeH = Math.max(d.elkHeight ?? 118, 56);

  // L1 — structure: a status-tinted slab whose label overflows the block like
  // a map label, so far-out still reads as named structure.
  if (level === 1) {
    return frame(
      <div
        className="relative flex items-center justify-center"
        style={{ height: minNodeH, background: glow(colors.fill, 0.2), borderRadius: 5 }}
      >
        <span
          className="absolute font-semibold text-center pointer-events-none"
          style={{
            fontSize: 15,
            transform: `scale(${textScale})`,
            whiteSpace: 'nowrap',
            color: 'hsl(var(--foreground))',
            textShadow: '0 1px 4px hsl(var(--background) / 0.9)',
          }}
        >
          {shortName(24)}
        </span>
      </div>,
      false,
    );
  }

  // L2 — blocks: id + name, gently scaled against the remaining distance.
  if (level === 2) {
    return frame(
      <div className="px-3 py-2.5 flex items-center gap-2.5" style={{ minHeight: minNodeH, background: glow(colors.fill, 0.08) }}>
        <span className="w-1.5 self-stretch rounded-full shrink-0" style={{ backgroundColor: colors.fill, opacity: 0.85 }} />
        <div className="min-w-0" style={{ transform: `scale(${textScale})`, transformOrigin: 'left center' }}>
          <div className="font-mono text-[10px] whitespace-nowrap" style={{ color: colors.text }}>{d.label}</div>
          <div className="font-medium text-[13px] leading-snug whitespace-nowrap" style={{ color: 'hsl(var(--foreground))' }}>
            {shortName(20)}
          </div>
        </div>
      </div>,
      false,
    );
  }

  // L3+ — the stereotyped block: Blueprint-style tinted title bar.
  const header = (
    <div
      className="px-2.5 py-1.5 flex items-baseline gap-1.5"
      style={{ background: `linear-gradient(90deg, ${glow(colors.fill, 0.28)}, ${glow(colors.fill, 0.08)})` }}
    >
      {d.hasChildren && (
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke={colors.text} strokeWidth="2.5" strokeLinecap="round" style={{ opacity: 0.55, flexShrink: 0 }}>
          <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
        </svg>
      )}
      <span className="text-[9px] font-semibold tracking-wide" style={{ color: colors.text }}>
        &#171;{(d.type || 'functional').replace(/_/g, ' ')}&#187;
      </span>
      <span className="font-mono text-[9px] text-muted-foreground">{d.label}</span>
      {d.hasChildren && (
        <button
          className="ml-auto flex items-center gap-0.5 px-1 py-0.5 rounded hover:bg-white/10 transition-colors"
          onClick={(e) => { e.stopPropagation(); d.onExpandCollapse?.(); }}
          title={d.collapsed ? `Expand (${d.childCount} hidden)` : 'Collapse'}
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" className="text-muted-foreground">
            <rect x="1.5" y="1.5" width="13" height="13" rx="3" stroke="currentColor" strokeWidth="1.4" />
            <line x1="5" y1="8" x2="11" y2="8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            {d.collapsed && <line x1="8" y1="5" x2="8" y2="11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
          </svg>
          <span className="text-[8.5px] text-muted-foreground">{d.childCount}</span>
        </button>
      )}
    </div>
  );

  const nameRow = (
    <div className="px-2.5 py-1.5 text-[12px] font-medium leading-snug" style={{ color: 'hsl(var(--foreground))' }}>
      {d.name || 'Untitled'}
    </div>
  );

  const footer = (
    <div className="px-2.5 py-1 border-t flex items-center gap-1.5" style={{ borderColor: 'hsl(var(--border) / 0.6)' }}>
      <span className="px-1.5 rounded text-[8.5px] font-semibold" style={{ backgroundColor: glow(colors.fill, 0.15), color: colors.text }}>
        {d.status}
      </span>
      {d.vcCount > 0 && (
        <span className="flex items-center gap-0.5 text-[8.5px] text-muted-foreground">
          <FlaskConical size={8} /> {d.vcCount}
        </span>
      )}
      {verdictColor && (
        <span className="flex items-center gap-0.5 text-[8.5px] font-semibold" style={{ color: verdictColor }} title={`Parametric constraints: ${d.verdict}`}>
          <Sigma size={8.5} /> {d.verdict === 'not_applicable' ? 'n/a' : d.verdict}
        </span>
      )}
      <PriorityIcon size={11} color={prio.color} strokeWidth={2.5} className="ml-auto shrink-0" />
    </div>
  );

  if (level === 3) {
    return frame(<>{header}{nameRow}{footer}</>);
  }

  // L4/L5 — compartments, in SysML order: values, then constraints.
  const paramRows = d.params.slice(0, level === 4 ? 4 : 8);
  const constraintRows = level === 5 ? d.constraints : [];

  return frame(
    <>
      {header}
      {nameRow}
      {level === 5 && d.desc && (
        <div className="px-2.5 pb-1.5 text-[9px] leading-snug text-muted-foreground line-clamp-3">{d.desc}</div>
      )}
      {paramRows.length > 0 && (
        <div className="border-t px-2.5 py-1.5" style={{ borderColor: 'hsl(var(--border) / 0.6)' }}>
          <div className="text-[7.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">values</div>
          {paramRows.map((p) => (
            <div key={p.name} className="font-mono text-[9px] leading-relaxed flex items-center gap-1" style={{ color: 'hsl(var(--foreground) / 0.85)' }}>
              {/* Derived values are italic, the SysML convention for computed properties */}
              <span className="truncate" style={{ fontStyle: p.derived ? 'italic' : 'normal' }}>{p.name} {p.display}</span>
              {p.measured && <FlaskConical size={8} className="shrink-0 text-cs-teal" />}
            </div>
          ))}
          {d.params.length > paramRows.length && (
            <div className="text-[8px] text-muted-foreground">+{d.params.length - paramRows.length} more</div>
          )}
        </div>
      )}
      {constraintRows.length > 0 && (
        <div className="border-t px-2.5 py-1.5" style={{ borderColor: 'hsl(var(--border) / 0.6)' }}>
          <div className="text-[7.5px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">constraints</div>
          {constraintRows.map((c, i) => (
            <div key={i} className="font-mono text-[8.5px] leading-relaxed flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: constraintColors[c.status] || 'hsl(var(--muted-foreground) / 0.4)' }} />
              <span className="truncate" style={{ color: 'hsl(var(--foreground) / 0.8)' }}>{c.expr}</span>
            </div>
          ))}
        </div>
      )}
      {footer}
    </>,
  );
}

export default memo(BlockNode);
