import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

async function waitForCanvas(app: any) {
  await expect(app.locator('.react-flow').first()).toBeVisible({ timeout: 20_000 });

  // Nodes mount at {x:0,y:0} with opacity:0 until entranceDone. Wait until at
  // least one node has a non-zero bounding box (ELK has landed).
  await expect.poll(async () => {
    const node = app.locator('.react-flow').first().locator('.react-flow__node').first();
    const box = await node.boundingBox();
    if (!box) return null;
    return box;
  }, { timeout: 10_000 }).not.toBeNull();

  // Now wait for geometry stability: two consecutive reads are identical.
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
  }, { timeout: 10_000 }).toBe(true);
}

async function zoomToLevel3(app: any) {
  const collapse = app.locator('[title="Collapse sidebar"]');
  if (await collapse.count()) {
    // Expand sidebar first (it may already be collapsed from a prior test).
    const expand = app.locator('[title="Expand sidebar"]');
    if (await expand.count()) {
      // Already collapsed — skip toggle.
    } else {
      await collapse.first().click();
      await app.waitForTimeout(300);
    }
  }

  // Anchor the zoom on the node's top-left corner, not its centre: the add-child
  // button hangs off that corner (left: -9), and zooming toward the centre
  // pushes the corner — and the button — off the left edge of the pane as the
  // node grows. Anchoring on the corner keeps the button in view at any zoom.
  const node = app.locator('.react-flow__node').first();
  const box = await node.boundingBox();
  if (box) {
    await app.mouse.move(box.x + 4, box.y + 4);
  }

  // The button is gated on level >= 3 (zoom >= 0.6). Scroll-zoom in.
  // After fitView the demo project is at L1 (the graph is denser with hoisted
  // edges); each wheel tick adds ~13%, so 8 ticks lands at L4.
  for (let i = 0; i < 8; i++) {
    await app.mouse.wheel(0, -120);
    await app.waitForTimeout(150);
  }

  // Move the mouse off the node so hover state resets before tests begin.
  await app.locator('.react-flow__controls').first().hover();
  await app.waitForTimeout(200);
}

test('hovering a node reveals the add-child button', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await waitForCanvas(app);
  await zoomToLevel3(app);

  await expect(app.locator('[title="Add child requirement"]').first()).toHaveCount(0);

  const node = app.locator('.react-flow__node').first();
  await node.hover();

  await expect(app.locator('[title="Add child requirement"]').first()).toBeVisible();

  await app.locator('.react-flow__controls').first().hover();
  await expect(app.locator('[title="Add child requirement"]').first()).toHaveCount(0);
});

test('clicking + opens the create form with the correct parent', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await waitForCanvas(app);
  await zoomToLevel3(app);

  const node = app.locator('.react-flow__node').first();
  const parentId = await node.getAttribute('data-id');
  expect(parentId).toBeTruthy();

  await node.hover();
  await app.locator('[title="Add child requirement"]').first().click();

  await expect(app.getByRole('heading', { name: new RegExp(`New child of ${parentId}`) })).toBeVisible();
  await expect(app).not.toHaveURL(/new=1/);

  const parentSelect = app.locator('[role="dialog"] select').first();
  await expect(parentSelect).toHaveValue(parentId!);
});

test('creating from the + button sets the correct parent', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await waitForCanvas(app);
  await zoomToLevel3(app);

  const node = app.locator('.react-flow__node').first();
  const parentId = await node.getAttribute('data-id');
  expect(parentId).toBeTruthy();

  await node.hover();
  await app.locator('[title="Add child requirement"]').first().click();

  await expect(app.getByRole('heading', { name: new RegExp(`New child of ${parentId}`) })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: new RegExp(`New child of ${parentId}`) })).toHaveCount(0, { timeout: 15_000 });

  const created = await app.evaluate(async ({ p, id }: any) => {
    const r = await fetch(`/api/projects/${p}/requirements/${id}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, { p: P, id: newId });
  expect(created).not.toBeNull();
  expect(created.parent).toBe(parentId);
});

test('add-child button does not render in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app, false);
  await waitForCanvas(app);
  await zoomToLevel3(app);

  const node = app.locator('.react-flow__node').first();
  await node.hover();

  await expect(app.locator('[title="Add child requirement"]').first()).toHaveCount(0);
});

test('clicking + on an already-selected node does not navigate to detail page', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await waitForCanvas(app);
  await zoomToLevel3(app);

  const node = app.locator('.react-flow__node').first();
  const nodeId = await node.getAttribute('data-id');

  await node.click();
  await app.waitForTimeout(450);

  // Selecting the node re-fits the camera to its whole subtree, zooming back
  // out below the level the add-child button appears at — zoom back in.
  await zoomToLevel3(app);

  await node.hover();
  await app.locator('[title="Add child requirement"]').first().click();

  await expect(app).not.toHaveURL(new RegExp(`/requirements/${nodeId}`));
  await expect(app.getByRole('heading', { name: new RegExp(`New child of ${nodeId}`) })).toBeVisible();
});

test('cross-route: from /components, clicking + lands on /requirements with form open', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await waitForCanvas(app);
  await zoomToLevel3(app);

  const node = app.locator('.react-flow__node').first();
  const parentId = await node.getAttribute('data-id');
  expect(parentId).toBeTruthy();

  await node.hover();
  await app.locator('[title="Add child requirement"]').first().click();

  await expect(app).toHaveURL(/\/requirements$/);
  await expect(app.getByRole('heading', { name: new RegExp(`New child of ${parentId}`) })).toBeVisible();
});
