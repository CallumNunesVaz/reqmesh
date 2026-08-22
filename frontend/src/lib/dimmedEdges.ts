import type { Edge } from '@xyflow/react';

// Dimming the graph when a node is selected: every edge not in the highlighted
// neighbourhood drops to near-invisible. The naive version maps over *all*
// edges and mints a new object (new `data`, new `style`, new `className`) for
// each one on every selection change, so at 1,500 edges that is 1,500
// allocations and 1,500 changed prop identities per click — and every edge
// component re-renders whether or not its own state changed.
//
// This keeps an id-keyed map of the previous pass and returns the *same* object
// identity for an edge whose computed `connected`/`opacity`/`className`/`filter`
// are unchanged, so `memo(...)`-wrapped edge components bail out instead of
// re-deriving their geometry.

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
  opacity: number;
  className: string | undefined;
  filter: string | undefined;
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
    const style = e.style as Record<string, any> | undefined;
    const stroke = style?.stroke as string | undefined;
    const dashed = ((style?.strokeDasharray ?? 'none') !== 'none');
    const opacity = connected ? Math.max((style?.opacity as number) || 0.55, 0.9) : 0.04;
    // A hint of bloom on active edges — just enough to trace them.
    // (Skipped in perf mode: SVG filters force slow re-rasterisation.)
    const filter = connected && stroke && !o.perfMode ? `drop-shadow(0 0 2px ${stroke})` : undefined;
    const className = connected && dashed && !o.perfMode ? 'rt-drift' : undefined;

    const hit = prev.get(e.id);
    if (hit && hit.source === e && hit.connected === connected && hit.opacity === opacity
      && hit.className === className && hit.filter === filter) {
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
      style: {
        ...(e.style as Record<string, any>),
        opacity,
        filter,
      },
    };
    next.set(e.id, { source: e, dimmed, connected, opacity, className, filter });
    return dimmed;
  });
  return { edges: out, prev: next };
}
