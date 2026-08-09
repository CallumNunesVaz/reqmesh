import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Drag-to-reparent on the requirements tree.
 *
 * Two things are easy to break and neither shows up in a unit test: a plain
 * click must still navigate (the rows are links, and the drag threshold is the
 * only thing separating the two gestures), and a drop must open the confirm
 * dialog rather than moving straight away — otherwise dragging becomes the one
 * route to a project-wide id rewrite that skips the warning.
 */
const P = DEMO_PROJECT;

/** dnd-kit's PointerSensor needs a 6px activation distance, and it only sees
 *  that through real intermediate moves — a single mouse.move jumps past it
 *  and no drag ever starts. */
async function dragTo(app: any, from: { x: number; y: number }, to: { x: number; y: number }) {
  await app.mouse.move(from.x, from.y);
  await app.mouse.down();
  const steps = 12;
  for (let i = 1; i <= steps; i++) {
    await app.mouse.move(
      from.x + ((to.x - from.x) * i) / steps,
      from.y + ((to.y - from.y) * i) / steps,
    );
  }
  await app.mouse.up();
}

async function open(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

test('a plain click still navigates rather than starting a drag', async ({ app, server }) => {
  await open(app, server);

  const row = app.locator('main .group').first();
  await row.click();

  await expect(app).toHaveURL(/\/requirements\/[A-Za-z0-9-]+$/, { timeout: 10000 });
});

test('dragging a row onto another opens the move confirmation', async ({ app, server }) => {
  await open(app, server);

  const grips = app.locator('[aria-label^="Drag to move"]');
  await expect(grips.first()).toHaveCount(1, { timeout: 10000 }).catch(() => {});

  const source = grips.nth(3);
  await source.scrollIntoViewIfNeeded();
  const from = await source.boundingBox();
  const targetRow = app.locator('main .group').first();
  const to = await targetRow.boundingBox();
  expect(from && to).toBeTruthy();

  await dragTo(app,
    { x: from!.x + from!.width / 2, y: from!.y + from!.height / 2 },
    { x: to!.x + to!.width / 2, y: to!.y + to!.height / 2 });

  // A drop asks; it does not move.
  await expect(app.getByRole('heading', { name: /^Move \d+ item/ })).toBeVisible({ timeout: 10000 });
});

test('cancelling the drop leaves the tree untouched', async ({ app, server }) => {
  await open(app, server);

  const parentsBefore = await app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    const d = await r.json();
    return d.items.map((x: any) => `${x.id}:${x.parent ?? ''}`).sort().join('|');
  }, P);

  const grips = app.locator('[aria-label^="Drag to move"]');
  const source = grips.nth(3);
  await source.scrollIntoViewIfNeeded();
  const from = await source.boundingBox();
  const to = await app.locator('main .group').first().boundingBox();

  await dragTo(app,
    { x: from!.x + from!.width / 2, y: from!.y + from!.height / 2 },
    { x: to!.x + to!.width / 2, y: to!.y + to!.height / 2 });

  await expect(app.getByRole('heading', { name: /^Move \d+ item/ })).toBeVisible({ timeout: 10000 });
  await app.locator('[title="Close"]').click();

  const parentsAfter = await app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    const d = await r.json();
    return d.items.map((x: any) => `${x.id}:${x.parent ?? ''}`).sort().join('|');
  }, P);

  expect(parentsAfter).toBe(parentsBefore);
});

test('no drag handles exist in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[aria-label^="Drag to move"]')).toHaveCount(0);
});
