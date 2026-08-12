import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * The help dialog documents j/k list navigation and Alt+B, but neither worked
 * on the newly-covered list pages (Decisions, Analysis, Definitions, Baselines,
 * System States) — the handler's `isList` never matched those routes, and the
 * pages never passed the `onList*` handlers. These two prove both halves.
 */

test('j and k move the selection on the Definitions list page', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/definitions`, { waitUntil: 'commit' });

  // The demo seeds five definitions; wait for data, not just the heading.
  await expect(app.locator('#entity-MassBudget')).toBeVisible({ timeout: 10_000 });

  const selected = app.locator('[id^="entity-"][class*="ring-primary/50"]');
  await expect(selected).toHaveCount(0);

  await app.keyboard.press('j');
  await expect(selected).toHaveCount(1);
  const first = await selected.getAttribute('id');
  expect(first).toBeTruthy();

  await app.keyboard.press('j');
  await expect(selected).toHaveCount(1);
  const second = await selected.getAttribute('id');
  expect(second).toBeTruthy();
  expect(second).not.toBe(first);

  await app.keyboard.press('k');
  await expect(selected).toHaveCount(1);
  expect(await selected.getAttribute('id')).toBe(first);
});

test('Alt+B reaches Baselines', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/definitions`, { waitUntil: 'commit' });
  await expect(app.locator('#entity-MassBudget')).toBeVisible({ timeout: 10_000 });

  await app.keyboard.press('Alt+b');

  await expect(app).toHaveURL(/\/project\/cessna-172\/baselines$/);
  await expect(app.getByRole('heading', { name: 'Baselines' })).toBeVisible({ timeout: 10_000 });
});
