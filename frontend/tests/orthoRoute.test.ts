import { describe, it, expect } from 'vitest';
import { routeEdges, roundedPath, assignLanes, findCorridor, type NodeRect, type Pt } from '../src/components/orthoRoute';

const W = 216;
const H = 118;
const rect = (id: string, x: number, y: number): NodeRect => ({ id, x, y, w: W, h: H });

/** Every consecutive point pair must share an x or a y — no diagonals. */
function expectOrthogonal(pts: Pt[]) {
  expect(pts.length).toBeGreaterThanOrEqual(2);
  for (let i = 0; i + 1 < pts.length; i++) {
    const dx = Math.abs(pts[i + 1].x - pts[i].x);
    const dy = Math.abs(pts[i + 1].y - pts[i].y);
    expect(Math.min(dx, dy), `segment ${i} is diagonal`).toBeLessThan(0.01);
  }
}

describe('routeEdges', () => {
  it('routes a forward edge from the source right face to the target left face', () => {
    const nodes = [rect('A', 0, 0), rect('B', 400, 0)];
    const routes = routeEdges(nodes, [{ id: 'e', source: 'A', target: 'B' }]);
    const pts = routes.get('e')!;
    expectOrthogonal(pts);
    expect(pts[0].x).toBeCloseTo(W);           // leaves A's right face
    expect(pts[pts.length - 1].x).toBeCloseTo(400);  // enters B's left face
  });

  it('fans multiple out-edges across distinct ports on the source face', () => {
    const nodes = [rect('A', 0, 200), rect('B', 400, 0), rect('C', 400, 200), rect('D', 400, 400)];
    const edges = ['B', 'C', 'D'].map((t) => ({ id: `e${t}`, source: 'A', target: t }));
    const routes = routeEdges(nodes, edges);
    const startYs = edges.map((e) => routes.get(e.id)![0].y);
    expect(new Set(startYs.map((y) => Math.round(y))).size).toBe(3);
    // Ports stay on the node's edge.
    for (const y of startYs) {
      expect(y).toBeGreaterThan(200);
      expect(y).toBeLessThan(200 + H);
    }
  });

  it('gives overlapping vertical runs in a channel distinct lanes', () => {
    // Two edges crossing in the same channel: A(top)→D(bottom), B(bottom)→C(top).
    const nodes = [rect('A', 0, 0), rect('B', 0, 300), rect('C', 400, 0), rect('D', 400, 300)];
    const routes = routeEdges(nodes, [
      { id: 'ad', source: 'A', target: 'D' },
      { id: 'bc', source: 'B', target: 'C' },
    ]);
    const laneX = (pts: Pt[]) => {
      // The vertical run is the segment with the biggest y extent.
      let best = 0; let bx = 0;
      for (let i = 0; i + 1 < pts.length; i++) {
        const dy = Math.abs(pts[i + 1].y - pts[i].y);
        if (dy > best) { best = dy; bx = pts[i].x; }
      }
      return bx;
    };
    expect(Math.abs(laneX(routes.get('ad')!) - laneX(routes.get('bc')!))).toBeGreaterThan(4);
  });

  it('routes a rank-spanning edge around blocks in intermediate ranks', () => {
    // A → C spans rank 1, which holds M directly in the straight-line path.
    const nodes = [rect('A', 0, 0), rect('M', 400, 0), rect('C', 800, 0)];
    const routes = routeEdges(nodes, [
      { id: 'am', source: 'A', target: 'M' },
      { id: 'mc', source: 'M', target: 'C' },
      { id: 'ac', source: 'A', target: 'C' },
    ]);
    const pts = routes.get('ac')!;
    expectOrthogonal(pts);
    // No horizontal segment crossing M's rank may pass through M's body.
    for (let i = 0; i + 1 < pts.length; i++) {
      const [p, q] = [pts[i], pts[i + 1]];
      if (Math.abs(p.y - q.y) > 0.01) continue;  // vertical
      const lo = Math.min(p.x, q.x);
      const hi = Math.max(p.x, q.x);
      if (hi <= 400 || lo >= 400 + W) continue;  // doesn't cross M's rank
      const inBody = p.y > 0 && p.y < H;
      expect(inBody, `run at y=${p.y} passes through M`).toBe(false);
    }
  });

  it('routes a backward edge orthogonally into the target left face', () => {
    const nodes = [rect('A', 0, 0), rect('B', 400, 0)];
    const routes = routeEdges(nodes, [
      { id: 'fwd', source: 'A', target: 'B' },
      { id: 'back', source: 'B', target: 'A' },
    ]);
    const pts = routes.get('back')!;
    expectOrthogonal(pts);
    expect(pts[0].x).toBeCloseTo(400 + W);       // leaves B's right face
    expect(pts[pts.length - 1].x).toBeCloseTo(0);  // enters A's left face
  });

  it('supports vertical rank directions', () => {
    const nodes = [rect('A', 0, 0), rect('B', 0, 400)];
    const routes = routeEdges(nodes, [{ id: 'e', source: 'A', target: 'B' }], { rankdir: 'TB' });
    const pts = routes.get('e')!;
    expectOrthogonal(pts);
    expect(pts[0].y).toBeCloseTo(H);           // leaves A's bottom face
    expect(pts[pts.length - 1].y).toBeCloseTo(400);  // enters B's top face
  });

  it('skips self-loops and edges to unknown nodes', () => {
    const nodes = [rect('A', 0, 0)];
    const routes = routeEdges(nodes, [
      { id: 'self', source: 'A', target: 'A' },
      { id: 'ghost', source: 'A', target: 'Z' },
    ]);
    expect(routes.size).toBe(0);
  });
});

describe('assignLanes', () => {
  it('separates overlapping intervals and shares lanes between disjoint ones', () => {
    const { lanes, count } = assignLanes([
      { lo: 0, hi: 100 },   // overlaps second
      { lo: 50, hi: 150 },  // overlaps first
      { lo: 200, hi: 300 }, // disjoint — may reuse a lane
    ]);
    expect(lanes[0]).not.toBe(lanes[1]);
    expect(count).toBe(2);
  });
});

describe('findCorridor', () => {
  it('returns a gap clear of every blocked rank', () => {
    const ranks = [[{ id: 'M', m0: 0, m1: 10, c0: 0, c1: 118 }]];
    const [g0, g1] = findCorridor(ranks, 0, 0, 59, 8);
    // 59 is inside M's body, so the corridor must sit above or below it.
    expect(g1 <= -8 || g0 >= 126).toBe(true);
  });
});

describe('roundedPath', () => {
  it('rounds corners with quadratic curves and keeps straights as lines', () => {
    const d = roundedPath([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }]);
    expect(d.startsWith('M 0,0')).toBe(true);
    expect(d).toContain('Q 100,0');
    expect(d.endsWith('L 100,100')).toBe(true);
  });

  it('handles degenerate inputs', () => {
    expect(roundedPath([])).toBe('');
    expect(roundedPath([{ x: 1, y: 2 }])).toBe('M 1,2');
  });
});
