import { test, expect, signIn, DEMO_PROJECT } from './fixtures';
import type { Page } from '@playwright/test';

const P = DEMO_PROJECT;

/** POST through the browser session. The component create endpoint is the only
 *  honest way to get a deliberately over-long name onto a component without
 *  editing the demo seed. */
async function post<T = any>(page: Page, path: string, body: unknown): Promise<T> {
  const cookies = await page.context().cookies();
  const token = cookies.find((c) => c.name === 'csrftoken')?.value || '';
  const res = await page.evaluate(async ([p, b, t]) => {
    const r = await fetch(`/api${p}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t as string },
      body: JSON.stringify(b),
    });
    return { status: r.status, body: await r.json().catch(() => null) };
  }, [path, body, token] as const);
  if (res.status >= 400) throw new Error(`POST ${path} → ${res.status}: ${JSON.stringify(res.body)}`);
  return res.body as T;
}

/**
 * A child link with a long name must be elided, not overflow the pane.
 *
 * The `truncate` class was already on the name span before this task, so
 * asserting the class proves nothing — it was inert. The fix is `min-w-0` on
 * both the row and the name span, which is what lets a flex item shrink below
 * its content and lets `truncate`'s ellipsis actually engage.
 */
test('a long component name is clipped instead of overflowing', async ({ app, server }) => {
  const longName =
    'Flap actuation drive motor with integrated position feedback transducer and torque limiting clutch assembly';

  await signIn(app);
  await post(app, `/projects/${P}/components`, {
    id: 'LONGCHILD',
    name: longName,
    type: 'part',
    parent: 'C172',
  });

  await app.goto(`${server.baseURL}/project/${P}/components/C172`);
  await app.waitForSelector('main');

  const link = app.locator('a', { hasText: longName }).first();
  await expect(link).toBeVisible({ timeout: 15_000 });

  // The name itself must be elided: its content overflows its own box.
  const name = link.locator('span.truncate');
  const nameMetrics = await name.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
  expect(nameMetrics.sw).toBeGreaterThan(nameMetrics.cw);

  // And the link row stays inside its container rather than running off the pane.
  const rowWidth = await link.evaluate((el) => el.scrollWidth);
  const containerWidth = await link.locator('..').evaluate((el) => el.clientWidth);
  expect(rowWidth).toBeLessThanOrEqual(containerWidth);
});
