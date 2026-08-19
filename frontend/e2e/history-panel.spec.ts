import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The history panel actually renders entries.
 *
 * This exists because the first implementation never fetched at all: it guarded
 * the effect with a ref initialised to the current itemId, so the very first
 * render compared equal and returned before calling the API. Typecheck, build,
 * the unit suites and the whole e2e run were all green, because nothing
 * asserted that the panel had content — and the "loading" and "empty" states
 * rendered the same sentence, so it looked deliberate.
 */
const P = DEMO_PROJECT;

test('a requirement edit shows up in its history panel', async ({ app, server }) => {
  await signIn(app);
  await setEditMode(app);

  // The request itself is the assertion. Checking rendered text is not enough:
  // the broken version rendered the same "No recorded changes" that a genuinely
  // empty history shows, so only "did it ask the server" separates them.
  const historyCall = app.waitForResponse(
    (r) => r.url().includes(`/projects/${P}/history/`) && r.status() === 200,
    { timeout: 15000 },
  );

  // Straight to a detail page, where the panel is defaultOpen. Rows on the list
  // page are buttons that call navigate(), not anchors, so there is no href to
  // click.
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await historyCall;

  const panel = app.getByText('Change History').locator('..');
  await expect(panel).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText('Loading history…')).toHaveCount(0, { timeout: 15000 });
});

test('a change-request card can reveal its history without loading it up front', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');

  // Collapsed by default: the list pages mount one panel per card, and eager
  // loading meant one history request per record just to render the page.
  const toggles = app.getByRole('button', { name: 'Show change history' });
  // Wait rather than count immediately: the list is fetched after mount,
  // so `main` being present says nothing about the cards existing yet.
  await expect(toggles.first()).toBeVisible({ timeout: 15000 });

  const historyCall = app.waitForResponse(
    (r) => r.url().includes(`/projects/${P}/history/`) && r.status() === 200,
    { timeout: 15000 },
  );
  await toggles.first().click();
  await historyCall;
  await expect(app.getByText('Loading history…')).toHaveCount(0, { timeout: 15000 });
});

async function putViaApp(app: any, path: string, body: any) {
  const csrfResp = await app.evaluate(async () => {
    const r = await fetch('/api/auth/whoami', { credentials: 'include' });
    return (await r.json()).csrf_token || '';
  });
  return app.evaluate(async ({ path, body, csrf }: { path: string; body: any; csrf: string }) => {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify(body),
      credentials: 'include',
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }, { path, body, csrf: csrfResp });
}

test('a default-open panel can collapse and reopen without refetching', async ({ app, server }) => {
  await signIn(app);

  // Count the actual requests; the whole point is that reopening must not issue
  // a second one, which the rendered text alone cannot prove.
  let historyCalls = 0;
  await app.route(`**/api/projects/${P}/history/**`, async (route) => {
    historyCalls += 1;
    await route.continue();
  });

  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');

  const collapse = app.getByRole('button', { name: 'Collapse change history' });
  await expect(collapse).toBeVisible({ timeout: 15_000 });
  // Wait for the initial (defaultOpen) fetch to settle before clicking.
  await expect(app.getByText('Loading history…')).toHaveCount(0, { timeout: 15_000 });

  await collapse.click();
  const show = app.getByRole('button', { name: 'Show change history' });
  await expect(show).toBeVisible({ timeout: 10_000 });

  await show.click();
  await expect(collapse).toBeVisible({ timeout: 10_000 });

  expect(historyCalls).toBe(1);
});

test('long before/after values are clipped and recoverable via title', async ({ app, server }) => {
  await signIn(app);

  const longBefore =
    'Original fuselage shell assembly with corrosion-resistant alclad skin and semi-monocoque aluminum construction';
  const longAfter =
    'Revised fuselage shell assembly with enhanced corrosion-resistant alclad skin and reinforced semi-monocoque aluminum construction';

  // Two sequential name updates so the latest entry has a long `before` *and*
  // a long `after`, not just one side.
  await putViaApp(app, `/api/projects/${P}/requirements/AFRM0001`, { name: longBefore });
  await putViaApp(app, `/api/projects/${P}/requirements/AFRM0001`, { name: longAfter });

  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');
  await expect(app.getByText('Loading history…')).toHaveCount(0, { timeout: 15_000 });

  const before = app.locator('span.line-through', { hasText: longBefore });
  await expect(before).toBeVisible({ timeout: 15_000 });
  const beforeMetrics = await before.evaluate((el) => ({
    sw: el.scrollWidth,
    cw: el.clientWidth,
    title: el.getAttribute('title'),
  }));
  expect(beforeMetrics.sw).toBeGreaterThan(beforeMetrics.cw);
  expect(beforeMetrics.title).toBe(longBefore);

  const after = app.locator('span.text-emerald-400', { hasText: longAfter });
  await expect(after).toBeVisible({ timeout: 15_000 });
  const afterMetrics = await after.evaluate((el) => ({
    sw: el.scrollWidth,
    cw: el.clientWidth,
    title: el.getAttribute('title'),
  }));
  expect(afterMetrics.sw).toBeGreaterThan(afterMetrics.cw);
  expect(afterMetrics.title).toBe(longAfter);
});
