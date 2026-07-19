import { memo, useState } from 'react';
import { Handle, Position, useStore, type NodeProps } from '@xyflow/react';
import { Copy, Sigma } from 'lucide-react';
import { useGraphSelection } from './GraphPane';
import { glow, shiftLightness } from './graphColors';
import { zoomLevel, labelScale, type ZoomLevel } from './semanticZoom';

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
  params?: { name: string; display: string }[];
  verdict?: string | null;
  vcCount?: number;
}

const verdictColors: Record<string, string> = {
  pass: 'hsl(179,100%,38%)',
  fail: 'hsl(0,84%,68%)',
  error: 'hsl(0,84%,68%)',
  unknown: 'hsl(45,90%,55%)',
};

function CircularNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as CircularNodeData;
  const [hover, setHover] = useState(false);
  const { connectedIds, selectedReqId, hasSelection } = useGraphSelection();
  // Semantic zoom: far out only the hub (parent) nodes keep their names, as
  // scaled map labels; close in every node reveals id, status and parametrics.
  const level: ZoomLevel = useStore((s) => zoomLevel(s.transform[2]));
  const textScale = useStore((s) => labelScale(s.transform[2]));
  const fill = statusFillColors[nodeData.status] || statusFillColors.proposed;
  const ringColor = priorityRingColors[nodeData.priority] || 'hsl(195,6%,62%)';
  const isCascade = !!nodeData.cascadeFrom;
  const childCount = nodeData.childCount || 0;
  const dimmed = hasSelection && !connectedIds.has(nodeData.label);
  const isSelected = selectedReqId === nodeData.label;

  const cr = childCount > 1 ? Math.min(22, 14 + childCount * 1.2) : 14;
  const nodeW = cr * 2 + 4;
  const urgent = nodeData.priority === 'critical' || nodeData.priority === 'high';

  // A restrained, status-tinted bloom: enough to lift the node off the canvas,
  // not enough to smear its edge. This is the node's ONLY glow — an SVG blur
  // used to double it up, which is what made every node read as a fuzzy blob.
  const glowFilter = isSelected
    ? `drop-shadow(0 0 6px ${glow(fill, 0.45)})`
    : hover
      ? `drop-shadow(0 0 5px ${glow(fill, 0.3)})`
      : `drop-shadow(0 0 3px ${glow(fill, 0.16)})`;

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
          {/* Lit from the top-left, so a flat disc reads as a sphere. Both
              stops derive from the one status colour. */}
          <radialGradient id={`circ-fill-${nodeData.label}`} cx="34%" cy="28%" r="80%">
            <stop offset="0%" stopColor={shiftLightness(fill, 13)} />
            <stop offset="100%" stopColor={shiftLightness(fill, -7)} />
          </radialGradient>
        </defs>

        {isSelected && (
          <circle cx={nodeW/2} cy={nodeW/2} r={cr + 8} fill="none"
            stroke={fill} strokeWidth="1.25" opacity="0.7" />
        )}

        {/* Priority is a thin rim on the core, not a fat one and not a
            detached orbit: both read as a second colour competing with the
            status fill instead of qualifying it. Low/medium stay quiet so the
            urgent ones actually stand out. */}
        <circle cx={nodeW/2} cy={nodeW/2} r={cr}
          fill={`url(#circ-fill-${nodeData.label})`}
          stroke={hover ? 'hsl(var(--foreground))' : ringColor}
          strokeWidth={hover ? 1.5 : urgent ? 1.4 : 0.9}
          strokeOpacity={hover ? 0.9 : urgent ? 0.8 : 0.35}
          style={{ cursor: 'pointer', transition: 'stroke-opacity 0.15s ease, stroke-width 0.15s ease' }}
        />

        {isCascade && (
          <Copy
            x={nodeW/2 - 5} y={nodeW/2 - 5} width={10} height={10}
            color="rgba(255,255,255,0.92)"
            style={{ pointerEvents: 'none' }}
          />
        )}
      </svg>

      {/* Side label — content follows the semantic zoom level. L1 keeps only
          hub names (scaled like map labels) so the far-out view reads as
          subsystem structure instead of 57 colliding captions. */}
      {(level > 1 || childCount > 0) && (
        <div style={{
          position: 'absolute',
          left: nodeW + 12,
          top: '50%',
          transform: `translateY(-50%) scale(${level <= 2 ? textScale : 1})`,
          transformOrigin: 'left center',
          lineHeight: 1.25,
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
        }}>
          {level >= 3 && (
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'hsl(var(--muted-foreground))',
              fontWeight: 500,
              letterSpacing: '0.02em',
            }}>
              {nodeData.label}
            </div>
          )}
          <div style={{
            fontSize: level === 1 ? 12 : 11,
            fontWeight: 600,
            color: 'hsl(var(--foreground))',
            maxWidth: 140,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            textShadow: level <= 2 ? '0 1px 4px hsl(var(--background) / 0.9)' : undefined,
          }}>
            {nodeData.name || 'Untitled'}
          </div>
          {level >= 4 && (
            <div className="flex items-center gap-1" style={{ fontSize: 9 }}>
              <span style={{ color: fill, fontWeight: 600 }}>{nodeData.status}</span>
              {level >= 5 && <span style={{ color: 'hsl(var(--muted-foreground))' }}>&middot; {nodeData.priority}</span>}
              {(nodeData.vcCount ?? 0) > 0 && level >= 5 && (
                <span style={{ color: 'hsl(var(--muted-foreground))' }}>&middot; {nodeData.vcCount} VC</span>
              )}
              {nodeData.verdict && (
                <span className="flex items-center gap-0.5" style={{ color: verdictColors[nodeData.verdict] || verdictColors.unknown, fontWeight: 600 }}>
                  <Sigma size={8} /> {nodeData.verdict === 'not_applicable' ? 'n/a' : nodeData.verdict}
                </span>
              )}
            </div>
          )}
          {level >= 5 && (nodeData.params?.length ?? 0) > 0 && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'hsl(var(--foreground) / 0.75)' }}>
              {nodeData.params!.slice(0, 3).map((p) => (
                <div key={p.name}>{p.name} {p.display}</div>
              ))}
              {nodeData.params!.length > 3 && (
                <div style={{ color: 'hsl(var(--muted-foreground))' }}>+{nodeData.params!.length - 3} more</div>
              )}
            </div>
          )}
        </div>
      )}

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
              {isCascade && <Copy size={9} className="inline ml-1 text-cs-pink" />}
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
