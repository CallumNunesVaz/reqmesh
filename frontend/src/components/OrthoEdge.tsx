import { memo, useMemo } from 'react';
import { BaseEdge, EdgeLabelRenderer, type EdgeProps } from '@xyflow/react';
import { roundedPath, type Pt } from './orthoRoute';
import { useGraphSelection } from './GraphPane';

// Renders a pre-routed orthogonal edge (see orthoRoute.ts). The whole
// diagram's paths are planned together, so this component only turns its
// polyline into rounded SVG and adds the presentation layer: a label on the
// longest segment and, when the edge is part of the active selection, a
// slow traveling pulse that shows the link's direction.

// Stable "no points" sentinel so `data?.points ?? EMPTY_PTS` does not mint a
// fresh array per render and churn the `path` memo below.
const EMPTY_PTS: Pt[] = [];

function OrthoEdge({ id, data, style, markerEnd }: EdgeProps) {
  // EMPTY_PTS, not a fresh `[]`: a new array every render invalidates the
  // useMemo below on each pass, which is what exhaustive-deps was complaining
  // about. A stable reference fixes it properly instead of silencing it.
  const pts = (data?.points as Pt[] | undefined) ?? EMPTY_PTS;
  const { selectedReqId } = useGraphSelection();

  const { path, labelX, labelY } = useMemo(() => {
    if (pts.length < 2) return { path: '', labelX: 0, labelY: 0 };
    let bi = 0;
    let bLen = -1;
    for (let i = 0; i + 1 < pts.length; i++) {
      const len = Math.abs(pts[i + 1].x - pts[i].x) + Math.abs(pts[i + 1].y - pts[i].y);
      if (len > bLen) { bLen = len; bi = i; }
    }
    return {
      path: roundedPath(pts, 10),
      labelX: (pts[bi].x + pts[bi + 1].x) / 2,
      labelY: (pts[bi].y + pts[bi + 1].y) / 2,
    };
  }, [pts]);

  if (!path) return null;

  const edgeColor = (data?.color as string) || (style as { stroke?: string })?.stroke || 'hsl(var(--cs-blue))';
  const edgeLabel = (data?.label as string) || '';
  const active = !!data?.showLabel;
  const hoisted = !!data?.hoisted;
  const count = (data?.count as number) || 1;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{ ...style, stroke: edgeColor, fill: 'none', strokeLinecap: 'round', ...(active ? { cursor: 'pointer', pointerEvents: 'auto' as any } : {}) }}
        markerEnd={markerEnd}
        interactionWidth={selectedReqId ? 20 : 0}
      />
      {hoisted && count > 1 && (
        // A hoisted edge is several relations collapsed onto one group pair —
        // badge the count so the merge reads as intentional, not as a missing
        // line. Always shown, not gated on selection.
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
      {active && (
        // Direction pulse: a dot glides source → target along the exact path.
        <circle r={2.2} fill={edgeColor} opacity={0.9} style={{ pointerEvents: 'none' }}>
          <animateMotion dur="2.8s" repeatCount="indefinite" path={path} calcMode="linear" />
        </circle>
      )}
      {active && edgeLabel && !(hoisted && count > 1) && (
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
              className="text-[9px] font-semibold px-1.5 py-px rounded bg-graph-node border border-graph-node-border shadow-sm"
              style={{ color: edgeColor, whiteSpace: 'nowrap' }}>
              {edgeLabel}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(OrthoEdge);
