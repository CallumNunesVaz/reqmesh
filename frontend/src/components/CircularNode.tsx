import { memo, useState } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useGraphSelection } from './GraphPane';
import { glow } from './graphColors';

const statusFillColors: Record<string, string> = {
  proposed: 'hsl(207,90%,64%)',
  approved: 'hsl(145,55%,42%)',
  implemented: 'hsl(260,100%,78%)',
  verified: 'hsl(179,100%,31%)',
  rejected: 'hsl(0,84%,68%)',
  deprecated: 'hsl(195,6%,62%)',
};

const priorityRingColors: Record<string, string> = {
  low: 'hsl(195,6%,62%)',
  medium: 'hsl(207,90%,64%)',
  high: 'hsl(28,100%,53%)',
  critical: 'hsl(0,84%,68%)',
};

interface CircularNodeData {
  label: string;
  name: string;
  status: string;
  priority: string;
  type: string;
  cascadeFrom: string | null;
  childCount?: number;
}

function CircularNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as CircularNodeData;
  const [hover, setHover] = useState(false);
  const { connectedIds, selectedReqId, hasSelection } = useGraphSelection();
  const fill = statusFillColors[nodeData.status] || statusFillColors.proposed;
  const ringColor = priorityRingColors[nodeData.priority] || 'hsl(195,6%,62%)';
  const isCascade = !!nodeData.cascadeFrom;
  const childCount = nodeData.childCount || 0;
  const dimmed = hasSelection && !connectedIds.has(nodeData.label);
  const isSelected = selectedReqId === nodeData.label;

  const cr = childCount > 1 ? Math.min(22, 14 + childCount * 1.2) : 14;
  const nodeW = cr * 2 + 4;

  // Soft, status-tinted bloom on every node; strongest when selected.
  const glowFilter = isSelected
    ? `drop-shadow(0 0 16px ${glow(fill, 0.6)}) drop-shadow(0 0 6px ${glow(fill, 0.9)})`
    : hover
      ? `drop-shadow(0 0 12px ${glow(fill, 0.5)})`
      : `drop-shadow(0 0 7px ${glow(fill, 0.32)})`;

  return (
    <div
      className="relative"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: nodeW,
        height: nodeW,
        opacity: dimmed ? 0.18 : 1,
        filter: glowFilter,
        transform: hover && !dimmed ? 'scale(1.06)' : 'scale(1)',
        transition: 'opacity 0.25s ease, filter 0.25s ease, transform 0.2s ease',
      }}
    >
      <Handle type="target" position={Position.Top} id="t" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Bottom} id="b" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Left} id="l" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Right} id="r" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Top} id="st" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="sb" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Left} id="sl" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="sr" style={{ opacity: 0 }} />

      <svg width={nodeW} height={nodeW} className="overflow-visible block">
        <defs>
          <filter id={`circ-glow-${nodeData.label}`} x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur in="SourceGraphic" stdDeviation={hover ? 3.5 : 2} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {isSelected && (
          <circle cx={nodeW/2} cy={nodeW/2} r={cr + 5} fill="none"
            stroke={fill} strokeWidth="1.6" opacity="0.9" />
        )}

        <circle cx={nodeW/2} cy={nodeW/2} r={cr}
          fill={fill}
          opacity={isSelected ? 0.5 : hover ? 0.4 : 0.2}
          filter={`url(#circ-glow-${nodeData.label})`}
          style={{ transition: 'opacity 0.25s ease' }}
        />

        <circle cx={nodeW/2} cy={nodeW/2} r={cr}
          fill={fill}
          stroke={hover ? 'hsl(var(--foreground))' : ringColor}
          strokeWidth={hover ? 2 : (nodeData.priority === 'critical' || nodeData.priority === 'high' ? 3 : 1)}
          strokeOpacity={hover ? 0.9 : 0.55}
          style={{ cursor: 'pointer', transition: 'stroke-width 0.15s' }}
        />

        {isCascade && (
          <text x={nodeW/2} y={nodeW/2 + 4}
            textAnchor="middle" dominantBaseline="central"
            fill="rgba(255,255,255,0.9)" fontSize={cr > 16 ? 11 : 9}
            style={{ pointerEvents: 'none', userSelect: 'none' }}>
            ⧉
          </text>
        )}
      </svg>

      <div style={{
        position: 'absolute',
        left: nodeW + 8,
        top: '50%',
        transform: 'translateY(-50%)',
        lineHeight: 1.25,
        pointerEvents: 'none',
        whiteSpace: 'nowrap',
      }}>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'hsl(var(--muted-foreground))',
          fontWeight: 500,
          letterSpacing: '0.02em',
        }}>
          {nodeData.label}
        </div>
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'hsl(var(--foreground))',
          maxWidth: 140,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {nodeData.name || 'Untitled'}
        </div>
      </div>

      {hover && (
        <div
          className="absolute left-1/2 -translate-x-1/2 z-50 pointer-events-none"
          style={{ top: nodeW + 4 }}
        >
          <div
            className="bg-popover text-popover-foreground rounded-lg border shadow-lg px-3 py-2.5 min-w-[180px] max-w-[240px]"
            style={{ animation: 'fadeIn 0.12s ease-out' }}
          >
            <div className="font-mono text-[10px] text-muted-foreground mb-0.5">
              {nodeData.label}
              {isCascade && <span className="ml-1 text-cs-pink">⧉</span>}
              {childCount > 0 && <span className="ml-1 text-muted-foreground">({childCount} children)</span>}
            </div>
            <div className="font-semibold text-sm leading-tight mb-1.5">{nodeData.name || 'Untitled'}</div>
            <div className="flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize"
                style={{ backgroundColor: fill + '20', color: fill }}>
                {nodeData.status}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize bg-muted text-muted-foreground">
                {nodeData.priority}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium capitalize bg-muted text-muted-foreground">
                {nodeData.type?.replace('_', ' ') || ''}
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

export default memo(CircularNode);
