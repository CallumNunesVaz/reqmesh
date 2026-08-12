import { test, expect, signIn, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Nine of twelve list pages rendered an empty list while fetching, and Risks
 * and Change Requests showed a blank panel when they had nothing to show.
 *
 * These delete the collection first rather than hoping to find it empty. The
 * demo project has risks and change requests, so an assertion guarded by "if
 * the empty card happens to be present" would never run — which is what the
 * first version of this file did. The fixture restores `projects/` from
 * pristine before every test, so mutating it here is free and makes the empty
 * state deterministic.
 */

async function deleteAll(page: any, collection: string, ids: string[]) {
  const csrf = await page.evaluate(async () => {
    const r = await fetch('/api/auth/whoami', { credentials: 'include' });
    return (await r.json()).csrf_token || '';
  });
  await page.evaluate(
    async ({ project, collection, ids, csrf }: any) => {
      for (const id of ids) {
        await fetch(`/api/projects/${project}/${collection}/${encodeURIComponent(id)}?force=true`, {
          method: 'DELETE',
          headers: { 'X-CSRF-Token': csrf },
          credentials: 'include',
        });
      }
    },
    { project: P, collection, ids, csrf },
  );
}

const EMPTY_CARD = '.card.p-12.text-center';

test('the risks page shows a real empty state, not a blank panel', async ({ app, server }) => {
  await signIn(app);

  const risks = await api(app, `/projects/${P}/risks`);
  const ids = (risks.items ?? risks).map((r: any) => r.id);
  expect(ids.length, 'the demo project should start with risks to delete').toBeGreaterThan(0);
  await deleteAll(app, 'risks', ids);

  await app.goto(`${server.baseURL}/project/${P}/risks`);

  const empty = app.locator(EMPTY_CARD);
  await expect(empty).toBeVisible({ timeout: 10_000 });
  await expect(empty).toContainText('No risks yet');
  // An icon and a hint line — what was missing before was any markup at all.
  await expect(empty.locator('svg')).toHaveCount(1);
});

test('the change requests page shows a real empty state', async ({ app, server }) => {
  await signIn(app);

  const crs = await api(app, `/projects/${P}/change-requests`);
  const ids = (crs.items ?? crs).map((c: any) => c.id);
  expect(ids.length).toBeGreaterThan(0);
  await deleteAll(app, 'change-requests', ids);

  await app.goto(`${server.baseURL}/project/${P}/change-requests`);

  const empty = app.locator(EMPTY_CARD);
  await expect(empty).toBeVisible({ timeout: 10_000 });
  await expect(empty.locator('svg')).toHaveCount(1);
});

test('a page that had no loading state now renders one before its data', async ({ app, server }) => {
  await signIn(app);

  // Hold the response open so the loading state is observable rather than a
  // race — Specifications rendered an empty list during this window before.
  await app.route(`**/api/projects/${P}/specifications*`, async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });

  await app.goto(`${server.baseURL}/project/${P}/specifications`, { waitUntil: 'commit' });

  await expect(app.getByText(/loading specifications/i)).toBeVisible({ timeout: 5_000 });

  await app.unroute(`**/api/projects/${P}/specifications*`);
  await expect(app.getByText(/loading specifications/i)).toBeHidden({ timeout: 15_000 });
});
