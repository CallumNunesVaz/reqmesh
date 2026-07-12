import { memo, useState } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useGraphSelection } from './GraphPane';

const statusColors: Record<string, { fill: string; text: string }> = {
  proposed: { fill: 'hsl(207,90%,64%)', text: '#93c5fd' },
  approved: { fill: 'hsl(145,55%,42%)', text: '#4ade80' },
  implemented: { fill: 'hsl(260,100%,78%)', text: '#c4b5fd' },
  verified: { fill: 'hsl(179,100%,31%)', text: '#2dd4bf' },
  rejected: { fill: 'hsl(0,84%,68%)', text: '#fca5a5' },
  deprecated: { fill: 'hsl(195,6%,62%)', text: '#a1a1aa' },
};

const priorityIndicators: Record<string, { color: string; label: string }> = {
  low: { color: 'hsl(195,6%,62%)', label: '○' },
  medium: { color: 'hsl(207,90%,64%)', label: '◐' },
  high: { color: 'hsl(28,100%,53%)', label: '◉' },
  critical: { color: 'hsl(0,84%,68%)', label: '●' },
};

interface RequirementNodeData {
  label: string;
  name: string;
  status: string;
  priority: string;
  type: string;
  verified: boolean;
  cascadeFrom: string | null;
  hasChildren: boolean;
  collapsed: boolean;
  childCount?: number;
}

const BOX_W = 172;
const BOX_H = 62;
const HEADER_H = 20;
const FOOTER_H = 14;

function RequirementNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as RequirementNodeData;
  const [hover, setHover] = useState(false);
  const { connectedIds, selectedReqId, hasSelection } = useGraphSelection();
  const colors = statusColors[nodeData.status] || statusColors.proposed;
  const prio = priorityIndicators[nodeData.priority] || priorityIndicators.medium;
  const isCascade = !!nodeData.cascadeFrom;
  const childCount = nodeData.childCount || 0;
  const dimmed = hasSelection && !connectedIds.has(nodeData.label);
  const isSelected = selectedReqId === nodeData.label;
  const hasKids = nodeData.hasChildren;

  const w = BOX_W;
  const h = BOX_H;

  const typeUpper = (nodeData.type || 'functional').replace(/_/g, ' ');
  const shortName = nodeData.name
    ? nodeData.name.length > 28
      ? nodeData.name.slice(0, 26) + '\u2026'
      : nodeData.name
    : 'Untitled';

  return (
    <div
      className="relative"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: w,
        height: h,
        opacity: dimmed ? 0.22 : 1,
        filter: hover ? 'brightness(1.15) drop-shadow(0 2px 6px rgba(0,0,0,0.25))' : 'drop-shadow(0 1px 2px rgba(0,0,0,0.15))',
        transition: 'opacity 0.25s ease, filter 0.2s ease',
        cursor: 'pointer',
      }}
    >
      <Handle type="target" position={Position.Left} id="l" style={{ opacity: 0, top: h / 2 }} />
      <Handle type="target" position={Position.Right} id="r" style={{ opacity: 0, top: h / 2 }} />
      <Handle type="source" position={Position.Left} id="sl" style={{ opacity: 0, top: h / 2 }} />
      <Handle type="source" position={Position.Right} id="sr" style={{ opacity: 0, top: h / 2 }} />

      <svg width={w} height={h} className="overflow-visible block">
        <defs>
          <filter id={`uml-glow-${nodeData.label}`} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur in="SourceGraphic" stdDeviation={hover ? 4 : 2} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Selection ring */}
        {isSelected && (
          <rect
            x={-3} y={-3} width={w + 6} height={h + 6} rx={7} ry={7}
            fill="none" stroke={colors.fill} strokeWidth={1.8} strokeDasharray="5,3" opacity={0.7}
          />
        )}

        {/* Card body */}
        <rect x={0} y={0} width={w} height={h} rx={5} ry={5}
          fill="hsl(var(--card))"
          stroke={hover ? 'hsl(var(--foreground) / 0.25)' : 'hsl(var(--border))'}
          strokeWidth={hover ? 1.2 : 0.8}
          filter={`url(#uml-glow-${nodeData.label})`}
        />
        {/* Status color left accent */}
        <rect x={0} y={0} width={4} height={h} rx={5} ry={5} fill={colors.fill}
          style={{ clipPath: 'inset(0 0 0 0 round 5px 0 0 5px)' }}
        />
        {/* Header divider */}
        <line x1={4} y1={HEADER_H} x2={w} y2={HEADER_H}
          stroke="hsl(var(--border))" strokeWidth={0.5} opacity={0.6} />
        {/* Footer divider */}
        <line x1={4} y1={h - FOOTER_H} x2={w} y2={h - FOOTER_H}
          stroke="hsl(var(--border))" strokeWidth={0.3} opacity={0.4} />

        {/* Header: <<stereotype>> ID */}
        <text x={10} y={HEADER_H - 6}
          fill={colors.text} fontSize="8" fontFamily="sans-serif" fontWeight={600}>
          &#171;{typeUpper}&#187;
          <tspan fill="hsl(var(--muted-foreground))" fontSize="7.5" dx={3}>{nodeData.label}</tspan>
        </text>

        {/* Middle: name */}
        <text x={10} y={HEADER_H + 14}
          fill="hsl(var(--foreground))" fontSize="10" fontFamily="sans-serif" fontWeight={500}>
          {shortName}
        </text>
        {isCascade && (
          <text x={w - 14} y={HEADER_H + 14}
            fill="hsl(var(--muted-foreground))" fontSize="9" textAnchor="end" opacity={0.6}>
            ⧉
          </text>
        )}
        {hasKids && (
          <text x={w - 8} y={HEADER_H + 26}
            fill="hsl(var(--muted-foreground))" fontSize="7.5" textAnchor="end" opacity={0.5}>
            +{childCount}
          </text>
        )}

        {/* Footer: status + priority */}
        <rect x={8} y={h - FOOTER_H + 1} width={44} height={11} rx={3} ry={3}
          fill={colors.fill + '25'} />
        <text x={12} y={h - 4} fill={colors.text} fontSize="7" fontFamily="sans-serif" fontWeight={600}>
          {nodeData.status}
        </text>
        <text x={w - 12} y={h - 4} fill={prio.color} fontSize="11" textAnchor="end">
          {prio.label}
        </text>
      </svg>

      {/* Hover tooltip */}
      {hover && (
        <div
          className="absolute left-1/2 -translate-x-1/2 z-50 pointer-events-none"
          style={{ bottom: h + 6 }}
        >
          <div
            className="bg-popover text-popover-foreground rounded-lg border shadow-lg px-3 py-2.5 min-w-[200px] max-w-[260px]"
            style={{ animation: 'fadeIn 0.12s ease-out' }}
          >
            <div className="font-mono text-[10px] text-muted-foreground mb-0.5">
              {nodeData.label}
              {isCascade && <span className="ml-1 text-cs-pink">⧉</span>}
              {childCount > 0 && <span className="ml-1 text-muted-foreground">({childCount} children)</span>}
            </div>
            <div className="font-semibold text-sm leading-tight mb-1.5">
              {nodeData.name || 'Untitled'}
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize"
                style={{ backgroundColor: colors.fill + '20', color: colors.fill }}>
                {nodeData.status}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize bg-muted text-muted-foreground">
                {nodeData.priority}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize bg-muted text-muted-foreground">
                {typeUpper}
              </span>
            </div>
            {isCascade && (
              <div className="mt-1.5 pt-1.5 border-t text-[10px] text-cs-pink font-medium">
                Cascaded from {nodeData.cascadeFrom}
              </div>
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

export default memo(RequirementNode);
