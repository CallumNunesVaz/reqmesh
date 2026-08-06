import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * The truncation warning actually reaches the screen.
 *
 * The unit tests cover detection — `items.length < total`, including that
 * exactly 2000 of 2000 is *not* truncated. They cannot cover rendering, and
 * "the component exists but never appears" is a failure this repository has
 * shipped before: `HistoryPanel` went a whole release fetching nothing,
 * because loading and empty rendered identical text and every gate was green.
 *
 * The demo is far below the 2000 cap, so the server response is intercepted
 * rather than seeded — seeding 2000 requirements to test a banner would cost
 * minutes on every run for no extra confidence.
 */
const P = DEMO_PROJECT;

/** Rewrite the list response's `total` so the client believes it is truncated. */
async function fakeTotal(app: import('@playwright/test').Page, total: number) {
  await app.route(
    (url) => /\/api\/projects\/[^/]+\/requirements\?/.test(url.toString()),
    async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      await route.fulfill({
        response: res,
        contentType: 'application/json',
        body: JSON.stringify({ ...body, total }),
      });
    },
  );
}

test('the banner appears, and says how many are hidden', async ({ app, server }) => {
  await signIn(app);
  await fakeTotal(app, 2431);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main', { timeout: 20_000 });

  const banner = app.getByText(/Showing .* of 2,431/);
  await expect(banner).toBeVisible({ timeout: 15_000 });
  // Informational, not an error: nothing has failed, so it must not be dressed
  // as a failure.
  await expect(app.locator('[role=alert]')).toHaveCount(0);
});

test('no banner when the list is complete', async ({ app, server }) => {
  // The other half, and the one that matters most: a permanently-visible
  // warning on every project would be worse than none at all.
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await expect(app.getByText(/Search or filter to narrow the list/)).toHaveCount(0);
});
