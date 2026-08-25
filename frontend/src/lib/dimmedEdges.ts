import type { Edge } from '@xyflow/react';

// Dimming the graph when a node is selected: every edge not in the highlighted
// neighbourhood drops to near-invisible. The naive version maps over *all*
// edges and mints a new object (new `data`, new `style`, new `className`) for
// each one on every selection change, so at 1,500 edges that is 1,500
// allocations and 1,500 changed prop identities per click — and every edge
// component re-renders whether or not its own state changed.
//
// Task 149 removed the allocation/re-render cost by returning the *same* object
// identity for an edge whose computed state is unchanged, so `memo(...)`-wrapped
// edge components bail out instead of re-deriving their geometry. This pass
// keeps that guarantee. What it no longer does is write a fresh `opacity` and
// `filter` into each edge's inline `style` — that was the remaining cost (one
// click dirtied ~1,500 SVG elements and forced a full style + paint pass).
//
// Dimming is now expressed as a `rt-dimming` class on the React Flow container
// plus a `rt-connected` class on edges inside the highlighted neighbourhood;
// the opacity values, the drop-shadow bloom and the dashed drift animation live
// in CSS (`frontend/src/styles/index.css`). A selection change flips a handful
// of class attributes and CSS does the rest in one style pass. The unconnected
// majority needs no per-edge attribute at all — it is the default under
// `rt-dimming`.
//
// `data.dimmed` is still computed here: the hoisted ×N badge is portalled out
// of the SVG by `EdgeLabelRenderer` and therefore cannot inherit the ancestor
// opacity the CSS dimming provides, so it reads this flag to recede in step.

export interface EdgeDimOptions {
  hasSelection: boolean;
  connectedIds: ReadonlySet<string>;
  focusDist: ReadonlyMap<string, number>;
  linkDir: 'both' | 'in' | 'out';
  showAllLinks: boolean;
  perfMode: boolean;
  derivationActive: boolean;
}

export interface EdgeDimEntry {
  /** The undimmed edge this entry was derived from. */
  source: Edge;
  dimmed: Edge;
  connected: boolean;
  className: string | undefined;
}

export interface EdgeDimResult {
  edges: Edge[];
  /** The map to feed back in as `prev` on the next pass. */
  prev: Map<string, EdgeDimEntry>;
}

export function dimEdges(
  edges: readonly Edge[],
  prev: ReadonlyMap<string, EdgeDimEntry>,
  o: EdgeDimOptions,
): EdgeDimResult {
  if (!o.hasSelection) {
    return { edges: edges as Edge[], prev: new Map() };
  }

  const next = new Map<string, EdgeDimEntry>();
  const out = edges.map((e) => {
    // Both ends must be in the highlighted neighbourhood. By default only
    // radial edges (endpoints at different hop distances) light — the paths
    // fanning out from the focus. With "show all links" on, same-distance
    // cross-links between neighbours light too.
    const bothIn = o.connectedIds.has(e.source) && o.connectedIds.has(e.target);
    // In a derivation trace every link inside the closure is part of the
    // story, so they all light. Otherwise: radial edges only by default,
    // and "radial" respects the chosen direction — with an incoming/outgoing
    // filter an edge must also point the way the walk travelled.
    const ds = o.focusDist.get(e.source);
    const dt = o.focusDist.get(e.target);
    const radial = o.linkDir === 'out' ? dt === (ds ?? -99) + 1
      : o.linkDir === 'in' ? ds === (dt ?? -99) + 1
      : ds !== dt;
    const connected = o.derivationActive ? bothIn : bothIn && (o.showAllLinks || radial);
    // Dashed edges get the travelling dash animation while connected. The dash
    // pattern is construction data, not a per-selection write, so reading it
    // here costs nothing and the class is only ~100 elements.
    const dashed = (((e.style as Record<string, any> | undefined)?.strokeDasharray ?? 'none') !== 'none');
    const className = connected ? `rt-connected${dashed && !o.perfMode ? ' rt-drift' : ''}` : undefined;

    const hit = prev.get(e.id);
    if (hit && hit.source === e && hit.connected === connected && hit.className === className) {
      next.set(e.id, hit);
      return hit.dimmed;
    }

    const dimmed: Edge = {
      ...e,
      // `dimmed` rather than reusing `showLabel`: an unconnected edge has
      // showLabel false, but so does *every* edge when nothing is selected, and
      // the hoisted badge must stay at full strength in that case. dimEdges
      // returns early with no selection, so `dimmed` is simply absent there.
      data: { ...e.data, showLabel: connected, dimmed: !connected },
      className,
    };
    next.set(e.id, { source: e, dimmed, connected, className });
    return dimmed;
  });
  return { edges: out, prev: next };
}
