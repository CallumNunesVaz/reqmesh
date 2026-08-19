import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';
import type { Page } from '@playwright/test';

/**
 * Drag-to-reorder on the system states page, mirroring the baselines page.
 *
 * The drag is driven through the real `@dnd-kit` PointerSensor: it needs a 6px
 * activation distance that only shows up through real intermediate mouse moves,
 * so a single jump never starts a drag.
 */
const P = DEMO_PROJECT;

interface StatesResponse {
  states: { name: string; order: number }[];
  orphans: string[];
}

async function renderedOrder(app: Page): Promise<string[]> {
  return app.evaluate(() =>
    Array.from(document.querySelectorAll('main [id^="entity-"]'))
      .map((el) => el.querySelector('h3.font-mono')?.textContent?.trim() ?? '')
      .filter(Boolean),
  );
}

async function center(app: Page, locator: any): Promise<{ x: number; y: number }> {
  const box = await locator.boundingBox();
  if (!box) throw new Error('no bounding box');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function dragTo(app: Page, from: { x: number; y: number }, to: { x: number; y: number }) {
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

test('dragging a system state above another persists after reload', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/system-states`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const initial = await api<StatesResponse>(app, `/projects/${P}/system-states`);
  const before = initial.states.map((s) => s.name);
  expect(before.length).toBeGreaterThan(1);

  // Wait until the DOM has settled on the same order the API reports, so the
  // framer-motion entrance animation has finished before we grab a handle.
  await expect.poll(async () => renderedOrder(app), { timeout: 10_000 }).toEqual(before);

  const handles = app.locator('button[title="Drag to reorder"]');
  await expect(handles.first()).toBeVisible({ timeout: 10_000 });

  // Drag the second state above the first.
  const source = handles.nth(1);
  const target = app.locator('main [id^="entity-"]').nth(0);
  await source.scrollIntoViewIfNeeded();
  await dragTo(app, await center(app, source), await center(app, target));

  const expected = [before[1], before[0], ...before.slice(2)];

  // Poll the API until the reorder lands — no fixed sleep.
  await expect
    .poll(async () => {
      const live = await api<StatesResponse>(app, `/projects/${P}/system-states`);
      return live.states.map((s) => s.name);
    }, { timeout: 10_000 })
    .toEqual(expected);

  // Reload and assert the new order persisted.
  await app.reload();
  await app.waitForSelector('main');
  await expect.poll(async () => renderedOrder(app), { timeout: 10_000 }).toEqual(expected);
});
