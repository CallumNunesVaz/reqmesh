import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('navigating directly with a query shows results without typing', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/search?q=airframe`);
  await app.waitForSelector('main');

  await expect(app.getByText('Searching…')).toHaveCount(0, { timeout: 15_000 });
  const resultCount = await app.locator('.card .flex.items-center').count();
  expect(resultCount).toBeGreaterThan(0);
});

test('clicking a result navigates to that entity', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/search?q=AFRM0001`);
  await app.waitForSelector('main');

  await expect(app.getByText('Searching…')).toHaveCount(0, { timeout: 15_000 });

  const link = app.locator('a').filter({ hasText: 'AFRM0001' }).first();
  await expect(link).toBeVisible({ timeout: 10_000 });
  await link.click();

  await app.waitForURL(/\/requirements\/AFRM0001/);
  await app.waitForSelector('main');
});

test('the kind filter narrows the results', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/search?q=airframe`);
  await app.waitForSelector('main');

  await expect(app.getByText('Searching…')).toHaveCount(0, { timeout: 15_000 });
  const allCount = await app.locator('.card .flex.items-center').count();

  await app.locator('select').selectOption('risk');
  await app.waitForTimeout(500);

  const filteredCount = await app.locator('.card .flex.items-center').count();
  expect(filteredCount).toBeLessThanOrEqual(allCount);
});

test('a query matching nothing shows the empty state', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/search?q=zzzz_nonexistent_zzzz`);
  await app.waitForSelector('main');

  await expect(app.getByText('Searching…')).toHaveCount(0, { timeout: 15_000 });
  await expect(app.getByText(/No results for/)).toBeVisible();
});

test('the palette "See all results" row lands on the page with the query intact', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');

  // Open the command palette via keyboard shortcut
  await app.keyboard.press('Control+K');

  // Wait for the palette to appear
  const paletteInput = app.locator('[class*="fixed"]').locator('input');
  await paletteInput.waitFor({ state: 'visible', timeout: 5_000 });

  // Type a query
  await paletteInput.fill('airframe');
  await app.waitForTimeout(500);

  // Click the "See all results" row
  const seeAll = app.locator('button').filter({ hasText: /See all results for/ });
  await expect(seeAll).toBeVisible({ timeout: 5_000 });
  await seeAll.click();

  // Should land on the search page with the query
  await app.waitForURL(/\/search\?q=airframe/);
  await app.waitForSelector('main');
});

test('the search page works in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/search?q=airframe`);
  await app.waitForSelector('main');

  // The page should render without errors in viewing mode
  await expect(app.getByText('Something went wrong')).toHaveCount(0);
  await expect(app.locator('main')).toBeVisible();

  // The VIEWING badge should be present (not in edit mode)
  await expect(app.getByRole('button', { name: 'VIEWING' })).toBeVisible({ timeout: 10_000 });

  // Search results should still be visible
  await expect(app.getByText('Searching…')).toHaveCount(0, { timeout: 15_000 });
  const resultCount = await app.locator('.card .flex.items-center').count();
  expect(resultCount).toBeGreaterThan(0);
});

test('the kind filter offers exactly the kinds the search endpoint branches on', async ({ app, server }) => {
  // `services/search.py` branches on ten kinds. The page listed nine — it was
  // derived from ENTITY_META, which has no entry for `comment`, so comments
  // were searchable but not filterable. This asserts the two vocabularies
  // match, which is the thing that drifts.
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/search?q=system`);
  await app.waitForSelector('main');

  const values = await app.locator('main select').first()
    .locator('option').evaluateAll((els: HTMLOptionElement[]) => els.map((e) => e.value));

  expect(values.filter((v) => v !== '').sort()).toEqual([
    'analysis', 'change_request', 'comment', 'component', 'decision',
    'definition', 'requirement', 'risk', 'specification', 'verification',
  ]);
});
