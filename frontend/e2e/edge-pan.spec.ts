import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * A click-drag that starts on an edge must pan the viewport, not be swallowed
 * by the edge. React Flow stamps every edge with a `nopan` class and a 20px
 * invisible interaction path, so before this fix a drag that began on an edge
 * was a no-op. We assert the *behaviour* — the viewport transform moves — and
 * deliberately never assert the `interactionWidth`/`nopan` plumbing.
 */

async function waitForCanvas(app: any) {
  await expect(app.locator('.react-flow').first()).toBeVisible({ timeout: 20_000 });

  // Nodes mount at {0,0} with opacity:0 until the layout lands; wait until one
  // has a real bounding box.
  await expect.poll(async () => {
    const box = await app.locator('.react-flow').first().locator('.react-flow__node').first().boundingBox();
    return box;
  }, { timeout: 15_000 }).not.toBeNull();

  // Edges mount with the nodes; wait until at least one exists.
  await expect.poll(async () => {
    return app.locator('.react-flow').first().locator('.react-flow__edge').count();
  }, { timeout: 15_000 }).toBeGreaterThan(0);

  // Geometry stability: two consecutive reads of the first few nodes agree.
  let prev: string | null = null;
  await expect.poll(async () => {
    const nodes = app.locator('.react-flow').first().locator('.react-flow__node');
    const count = await nodes.count();
    if (count === 0) return null;
    const boxes: { x: number; y: number }[] = [];
    for (let i = 0; i < Math.min(count, 5); i++) {
      const box = await nodes.nth(i).boundingBox();
      if (box) boxes.push({ x: Math.round(box.x), y: Math.round(box.y) });
    }
    const key = JSON.stringify(boxes);
    if (prev !== null && key === prev) return true;
    prev = key;
    return false;
  }, { timeout: 15_000 }).toBe(true);

  // The splash overlays the canvas while it settles; wait for it to unmount so
  // the pointer events below actually reach the graph.
  await expect(app.locator('.rm-splash')).toHaveCount(0, { timeout: 20_000 });
}

async function openGraph(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await waitForCanvas(app);
}

function viewportTransform(app: any): Promise<string> {
  return app.evaluate(() => document.querySelector('.react-flow__viewport')?.style.transform ?? '');
}

/** A screen point on the visible stroke of the first (or named) edge, at a
 *  given fraction along its length. The default midpoint is fine for the pan
 *  tests; the click test uses a point near the target, where edges converging
 *  on a node approach from distinct directions (their source-side fan and
 *  midpoints overlap other edges once hidden endpoints are hoisted). */
function edgeMidpoint(app: any, edgeId?: string, t = 0.5) {
  return app.evaluate(({ id, t }) => {
    const g = id
      ? [...document.querySelectorAll('.react-flow__edge')].find((e) => e.getAttribute('data-id') === id)
      : document.querySelector('.react-flow__edge');
    if (!g) return null;
    const p = g.querySelector('.react-flow__edge-path');
    if (!p) return null;
    const pt = p.getPointAtLength(p.getTotalLength() * t);
    const m = p.getScreenCTM();
    return {
      id: g.getAttribute('data-id'),
      x: m.a * pt.x + m.c * pt.y + m.e,
      y: m.b * pt.x + m.d * pt.y + m.f,
    };
  }, { id: edgeId, t });
}

async function dragBy(app: any, from: { x: number; y: number }, dx: number, dy: number) {
  await app.mouse.move(from.x, from.y);
  await app.mouse.down();
  const steps = 12;
  for (let i = 1; i <= steps; i++) {
    await app.mouse.move(from.x + (dx * i) / steps, from.y + (dy * i) / steps);
  }
  await app.mouse.up();
}

/** The requirement id of the node currently selected in the app (uml mode:
 *  the selected node's frame carries a `box-shadow: 0 0 0 1px` ring). */
function selectedReqId(app: any): Promise<string | null> {
  return app.evaluate(() => {
    for (const n of document.querySelectorAll('.react-flow__node')) {
      const ring = [...n.querySelectorAll('div')].find((d) =>
        (d.getAttribute('style') || '').includes('box-shadow: 0 0 0 1px'));
      if (ring) return n.getAttribute('data-id');
    }
    return null;
  });
}

test('a drag starting on an edge pans the viewport (uml)', async ({ app, server }) => {
  await openGraph(app, server);

  const pt = await edgeMidpoint(app);
  expect(pt).toBeTruthy();

  const before = await viewportTransform(app);
  await dragBy(app, pt!, 140, 140);
  const after = await viewportTransform(app);

  expect(after).not.toBe(before);
});

test('a drag starting on an edge pans the viewport (force)', async ({ app, server }) => {
  await openGraph(app, server);
  await app.locator('[title="Force-directed layout"]').first().click();
  await waitForCanvas(app);

  const pt = await edgeMidpoint(app);
  expect(pt).toBeTruthy();

  const before = await viewportTransform(app);
  await dragBy(app, pt!, 140, 140);
  const after = await viewportTransform(app);

  expect(after).not.toBe(before);
});

test('with a requirement selected, clicking an edge selects the other end', async ({ app, server }) => {
  await openGraph(app, server);

  // Select the first node.
  const node = app.locator('.react-flow__node').first();
  const nodeId = await node.getAttribute('data-id');
  expect(nodeId).toBeTruthy();
  const box = await node.boundingBox();
  expect(box).toBeTruthy();
  await app.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await expect.poll(() => selectedReqId(app), { timeout: 5_000 }).toBe(nodeId);

  // Find an edge incident to the selected node and its other endpoint.
  const edge = await app.evaluate((id) => {
    const g = [...document.querySelectorAll('.react-flow__edge')].find((e) => {
      const m = (e.getAttribute('aria-label') || '').match(/^Edge from (.+) to (.+)$/);
      return m && (m[1] === id || m[2] === id);
    });
    if (!g) return null;
    const m = (g.getAttribute('aria-label') || '').match(/^Edge from (.+) to (.+)$/);
    const otherEnd = m![1] === id ? m![2] : m![1];
    return { edgeId: g.getAttribute('data-id'), otherEnd };
  }, nodeId);
  expect(edge).toBeTruthy();
  expect(edge!.otherEnd).not.toBe(nodeId);

  const pt = await edgeMidpoint(app, edge!.edgeId!, 0.85);
  expect(pt).toBeTruthy();
  await app.mouse.click(pt!.x, pt!.y);

  await expect.poll(() => selectedReqId(app), { timeout: 5_000 }).toBe(edge!.otherEnd);
});
