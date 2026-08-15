import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';
import type { Page } from '@playwright/test';

/**
 * The drop target is the row under the pointer.
 *
 * `useTreeDrag` used to resolve collisions with `closestCenter`, which compares
 * the *dragged grip's* translated centre against each droppable's centre. The
 * grip is the small handle at the row's left edge, so that centre sits above
 * the cursor by half a row or more, and a drag released over row N resolved to
 * row N-1. Now the resolution is `pointerWithin` (the cursor itself) with a
 * `closestCenter` fallback for the gap outside every droppable, so what is
 * highlighted mid-drag is what receives the drop.
 */

const P = DEMO_PROJECT;

type TreeKind = 'requirements' | 'components';

async function openTree(app: Page, server: { baseURL: string }, kind: TreeKind) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/${kind}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

/** Ids in the same order the tree renders them (the id span is the only
 *  `span.font-mono` in a row). */
async function sampleIds(app: Page): Promise<string[]> {
  return app.evaluate(() =>
    Array.from(document.querySelectorAll('main [role="treeitem"]')).map(
      (row) => row.querySelector('span.font-mono')?.textContent?.trim() ?? '',
    ),
  );
}

/**
 * The rendered ids, once the tree has actually finished rendering them.
 *
 * The tree fetches its data after the page settles, so reading the DOM straight
 * after `openTree` returns an empty or partial list — which is how this spec
 * passed locally and failed on CI, where the runner is slow enough for the gap
 * to matter. `pickPair` then found nothing to drag and the top-level test's
 * `findIndex` returned -1.
 *
 * Polling for a *stable* count rather than a fixed one, because the two trees
 * have different sizes and a hardcoded expectation would rot the moment the
 * demo project changes. Two consecutive equal samples above one row means the
 * render has settled; a fixed `waitForTimeout` would be the same bet this
 * suite has already lost several times.
 */
async function domIds(app: Page): Promise<string[]> {
  let previous = -1;
  await expect
    .poll(async () => {
      const count = (await sampleIds(app)).length;
      const settled = count > 1 && count === previous;
      previous = count;
      return settled;
    }, { timeout: 20_000, intervals: [200] })
    .toBe(true);
  return sampleIds(app);
}

/** Read the current parent of every node, keyed by id. */
async function parents(app: Page, kind: TreeKind): Promise<Map<string, string | null>> {
  const data = await api(app, `/projects/${P}/${kind}?limit=2000`);
  const items = (data.items ?? []) as { id: string; parent: string | null }[];
  return new Map(items.map((i) => [i.id, i.parent ?? null]));
}

function inSubtree(root: string, id: string, parent: Map<string, string | null>): boolean {
  let cursor: string | null = id;
  const seen = new Set<string>();
  while (cursor && cursor !== root && !seen.has(cursor)) {
    seen.add(cursor);
    cursor = parent.get(cursor) ?? null;
  }
  return cursor === root;
}

/** A (source, target) pair that is a legal drop and both near the top of the
 *  tree, so no scrolling is needed. Prefers a leaf source. */
function pickPair(
  ids: string[],
  parent: Map<string, string | null>,
  limit = 8,
): { sourceIdx: number; targetIdx: number } {
  // Leafness is judged against the whole project, not the rendered rows: a node
  // whose children happen to sit outside `limit` is still a parent, and picking
  // it as a drag source would move a subtree when the test means to move a node.
  const isLeaf = (id: string) =>
    ![...parent.values()].some((p) => p === id);
  for (let s = 1; s < Math.min(limit, ids.length); s++) {
    const src = ids[s];
    if (!isLeaf(src)) continue;
    for (let t = 0; t < Math.min(limit, ids.length); t++) {
      if (t === s) continue;
      const tgt = ids[t];
      if (tgt === src || parent.get(src) === tgt) continue;
      if (inSubtree(src, tgt, parent)) continue;
      return { sourceIdx: s, targetIdx: t };
    }
  }
  throw new Error(`no valid drag pair found in first ${limit} rows`);
}

/** dnd-kit's PointerSensor needs a 6px activation distance, and it only sees
 *  that through real intermediate moves — a single jump does not start a drag. */
async function moveSteps(
  app: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
  steps = 12,
) {
  for (let i = 1; i <= steps; i++) {
    await app.mouse.move(
      from.x + ((to.x - from.x) * i) / steps,
      from.y + ((to.y - from.y) * i) / steps,
    );
  }
}

async function center(app: Page, locator: any): Promise<{ x: number; y: number }> {
  const box = await locator.boundingBox();
  if (!box) throw new Error('no bounding box');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

const TREES: TreeKind[] = ['requirements', 'components'];

for (const kind of TREES) {
  test.describe(`${kind} tree`, () => {
    test('dropping over a row seeds the confirm dialog with that row', async ({ app, server }) => {
      await openTree(app, server, kind);

      const parent = await parents(app, kind);
      const ids = await domIds(app);
      const { sourceIdx, targetIdx } = pickPair(ids, parent);
      const target = ids[targetIdx];

      const grip = app.locator('[aria-label^="Drag to move"]').nth(sourceIdx);
      const targetRow = app.locator('main [role="treeitem"]').nth(targetIdx);
      await grip.scrollIntoViewIfNeeded();

      const from = await center(app, grip);
      const to = await center(app, targetRow);

      await app.mouse.move(from.x, from.y);
      await app.mouse.down();
      await moveSteps(app, from, to);
      await app.mouse.up();

      const dialog = app.locator('[role="dialog"]');
      await expect(dialog.getByRole('heading', { name: /^Move \d+ item/ })).toBeVisible({ timeout: 10000 });
      await expect(dialog.locator('span.font-mono')).toContainText(target);
    });

    test('mid-drag, the highlighted row is the one under the pointer', async ({ app, server }) => {
      await openTree(app, server, kind);

      const parent = await parents(app, kind);
      const ids = await domIds(app);
      const { sourceIdx, targetIdx } = pickPair(ids, parent);

      const grip = app.locator('[aria-label^="Drag to move"]').nth(sourceIdx);
      const targetRow = app.locator('main [role="treeitem"]').nth(targetIdx);
      await grip.scrollIntoViewIfNeeded();

      const from = await center(app, grip);
      const to = await center(app, targetRow);

      await app.mouse.move(from.x, from.y);
      await app.mouse.down();
      await moveSteps(app, from, to);

      const wrapper = targetRow.locator('xpath=..');
      await expect(wrapper).toHaveClass(/ring-primary/);

      await app.mouse.up();
    });

    test('dropping onto the top-level strip resolves to top level', async ({ app, server }) => {
      await openTree(app, server, kind);

      const parent = await parents(app, kind);
      const ids = await domIds(app);
      // A node that is not already top-level, so the move is meaningful.
      const sourceIdx = ids.findIndex((id) => (parent.get(id) ?? null) !== null);
      expect(sourceIdx).toBeGreaterThanOrEqual(0);

      const grip = app.locator('[aria-label^="Drag to move"]').nth(sourceIdx);
      await grip.scrollIntoViewIfNeeded();
      const from = await center(app, grip);

      await app.mouse.move(from.x, from.y);
      await app.mouse.down();
      // Nudge past the activation distance so the drag starts and the strip mounts.
      await moveSteps(app, from, { x: from.x, y: from.y + 30 }, 4);

      const strip = app.getByText('Drop here to make top level');
      await expect(strip).toBeVisible({ timeout: 10000 });
      const to = await center(app, strip);
      await moveSteps(app, { x: from.x, y: from.y + 30 }, to);
      await app.mouse.up();

      const dialog = app.locator('[role="dialog"]');
      await expect(dialog.getByRole('heading', { name: /^Move \d+ item/ })).toBeVisible({ timeout: 10000 });
      await expect(dialog.locator('span.font-mono')).toContainText('the top level');
    });

    test('a drop released over no droppable cancels and mutates nothing', async ({ app, server }) => {
      await openTree(app, server, kind);

      const before = (await parents(app, kind));
      const ids = await domIds(app);
      const sourceIdx = ids.findIndex((id) => (before.get(id) ?? null) !== null);
      expect(sourceIdx).toBeGreaterThanOrEqual(0);

      const grip = app.locator('[aria-label^="Drag to move"]').nth(sourceIdx);
      await grip.scrollIntoViewIfNeeded();
      const from = await center(app, grip);

      await app.mouse.move(from.x, from.y);
      await app.mouse.down();
      await moveSteps(app, from, { x: from.x, y: from.y - from.y + 24 }, 8);
      await app.mouse.up();

      await expect(app.locator('[role="dialog"]')).toHaveCount(0, { timeout: 3000 });

      const after = await parents(app, kind);
      expect([...after.entries()].sort().join('|')).toBe([...before.entries()].sort().join('|'));
    });
  });
}
