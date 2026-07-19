import { memo, useMemo } from 'react';
import { BaseEdge, EdgeLabelRenderer, type EdgeProps } from '@xyflow/react';
import { roundedPath, type Pt } from './orthoRoute';

// Renders a pre-routed orthogonal edge (see orthoRoute.ts). The whole
// diagram's paths are planned together, so this component only turns its
// polyline into rounded SVG and adds the presentation layer: a label on the
// longest segment and, when the edge is part of the active selection, a
// slow traveling pulse that shows the link's direction.

function OrthoEdge({ id, data, style, markerEnd }: EdgeProps) {
  const pts = (data?.points as Pt[] | undefined) ?? [];

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

  const edgeColor = (data?.color as string) || (style as { stroke?: string })?.stroke || 'hsl(207,90%,64%)';
  const edgeLabel = (data?.label as string) || '';
  const active = !!data?.showLabel;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{ ...style, stroke: edgeColor, fill: 'none', strokeLinecap: 'round' }}
        markerEnd={markerEnd}
      />
      {active && (
        // Direction pulse: a dot glides source → target along the exact path.
        <circle r={2.2} fill={edgeColor} opacity={0.9} style={{ pointerEvents: 'none' }}>
          <animateMotion dur="2.8s" repeatCount="indefinite" path={path} calcMode="linear" />
        </circle>
      )}
      {active && edgeLabel && (
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

export default memo(OrthoEdge);
