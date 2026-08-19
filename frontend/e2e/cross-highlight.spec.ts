import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Cross-highlighting: hovering a node on the canvas lights the matching row in
 * the requirements list (open beside it), and vice-versa. A hover is not a
 * click — it must not scroll the list, select anything, or navigate.
 */
async function waitForCanvas(app: any) {
  await expect(app.locator('.react-flow').first()).toBeVisible({ timeout: 20_000 });
  await expect.poll(async () => {
    const box = await app.locator('.react-flow').first().locator('.react-flow__node').first().boundingBox();
    return box;
  }, { timeout: 15_000 }).not.toBeNull();
  await expect(app.locator('.rm-splash')).toHaveCount(0, { timeout: 20_000 });
}

test('hovering a canvas node highlights the matching requirements row without scrolling or selecting', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await waitForCanvas(app);

  // The list shows every requirement, the canvas only the visible ones.
  await expect(app.locator('[role="treeitem"]').first()).toBeVisible({ timeout: 15_000 });

  // Scroll the list so the row under test is out of view — a highlight must
  // not yank it back into shot.
  await app.evaluate(() => { const m = document.querySelector('main'); if (m) m.scrollTop = 500; });
  const scrollBefore = await app.evaluate(() => document.querySelector('main')?.scrollTop ?? 0);
  const urlBefore = app.url();

  const node = app.locator('.react-flow__node').first();
  const nodeId = await node.getAttribute('data-id');
  expect(nodeId).toBeTruthy();

  const row = app.locator(`[id="entity-${nodeId}"]`);
  await expect(row).toHaveCount(1);
  await expect(row).not.toHaveClass(/rt-cross-hover/);

  await node.hover();

  await expect.poll(() =>
    row.evaluate((el) => el.classList.contains('rt-cross-hover')),
    { timeout: 5_000 }).toBe(true);

  // A hover is not a click: no navigation, no selection, no scrolling.
  expect(app.url()).toBe(urlBefore);
  const scrollAfter = await app.evaluate(() => document.querySelector('main')?.scrollTop ?? 0);
  expect(scrollAfter).toBe(scrollBefore);

  // Leaving the node clears the highlight.
  await app.locator('.react-flow__controls').first().hover();
  await expect.poll(() =>
    row.evaluate((el) => el.classList.contains('rt-cross-hover')),
    { timeout: 5_000 }).toBe(false);
});

test('hovering a requirements row highlights the corresponding canvas node', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await waitForCanvas(app);

  // Pick a row whose requirement is currently visible on the canvas.
  const node = app.locator('.react-flow__node').first();
  const nodeId = await node.getAttribute('data-id');
  expect(nodeId).toBeTruthy();

  const row = app.locator(`[id="entity-${nodeId}"]`);
  await row.scrollIntoViewIfNeeded();

  // The node carries a data-cross-highlight marker while the shared hover
  // points at it (rendered by BlockNode/CircularNode).
  const highlighted = node.locator('[data-cross-highlight]');
  await expect(highlighted).toHaveCount(0);

  await row.hover();
  await expect(highlighted).toHaveCount(1, { timeout: 5_000 });

  // Leaving the row clears the node highlight.
  await app.locator('.react-flow__controls').first().hover();
  await expect(highlighted).toHaveCount(0, { timeout: 5_000 });
});
