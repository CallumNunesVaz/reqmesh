import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';

/**
 * Risk metrics on the Metrics page.
 *
 * The property worth pinning end-to-end is the one the whole risk feature is
 * built on: the rating is derived from the project's matrix, never stored. So
 * re-banding a cell in Settings has to move the numbers on Metrics, with no
 * write to any risk in between.
 */
const P = DEMO_PROJECT;

test('the risk profile summarises the register through the project matrix', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/metrics`);
  await app.waitForSelector('main');

  const panel = app.locator('.card').filter({ hasText: 'Risk Profile' }).first();
  await expect(panel).toBeVisible({ timeout: 20_000 });

  const metrics = await api<any>(app, `/projects/${P}/metrics`);
  const risks = metrics.risks;

  // The header states the same open/total the API reports.
  await expect(panel).toContainText(`${risks.open} open of ${risks.total}`);

  // Every band in the matrix has a legend entry, so a band nobody has hit is
  // still visible as a zero rather than silently missing.
  for (const band of risks.bands) {
    await expect(panel).toContainText(band.label);
  }

  // The severe-open headline card agrees with the panel.
  const card = app.locator('.card').filter({ hasText: 'Severe Open Risks' }).first();
  await expect(card).toContainText(String(risks.severe_open));
});

test('re-banding a matrix cell moves the metrics without touching any risk', async ({ app, server }) => {
  await signIn(app);

  const before = (await api<any>(app, `/projects/${P}/metrics`)).risks;

  // Pick a cell that actually rates something: use a real risk's own inputs.
  const risk = (await api<{ items: any[] }>(app, `/projects/${P}/risks`)).items.find((r) => r.rating?.band);
  expect(risk, 'the demo project should contain at least one rateable risk').toBeTruthy();

  const matrix = await api<any>(app, `/projects/${P}/risk-matrix`);
  const si = matrix.severities.indexOf(risk.rating.severity);
  const li = matrix.likelihoods.indexOf(risk.rating.likelihood);
  const current = matrix.cells[si][li];
  const other = matrix.bands.map((b: any) => b.key).find((k: string) => k !== current);

  await app.goto(`${server.baseURL}/project/${P}/settings`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  const grid = app.locator('.card').filter({ has: app.getByRole('heading', { name: 'Risk Matrix' }) });
  // Rows render most-severe first, so the row index is mirrored. Only the
  // coloured band buttons — the first cell of each row holds a remove button,
  // which would shift every index by one.
  const row = grid.locator('tbody tr').nth(matrix.severities.length - 1 - si);
  const cell = row.locator('td button[style*="background"]').nth(li);
  await cell.scrollIntoViewIfNeeded();
  // Cycling the cell lands on some other band; assert what it became rather
  // than assuming one click reaches `other`.
  await cell.click();
  await app.getByRole('button', { name: /^Save$/ }).first().click();
  // Poll the API until the save lands — no fixed sleep.
  await expect(async () => {
    const stored = await api<any>(app, `/projects/${P}/risk-matrix`);
    expect(stored.cells[si][li], 'the click did not change the cell').not.toBe(current);
  }).toPass({ timeout: 10_000 });

  expect(other).toBeTruthy();

  const after = (await api<any>(app, `/projects/${P}/metrics`)).risks;
  expect(after.by_band).not.toEqual(before.by_band);
  expect(after.total).toBe(before.total);

  // And the page renders the new numbers, not a cached summary.
  await app.goto(`${server.baseURL}/project/${P}/metrics`);
  await app.waitForSelector('main');
  const panel = app.locator('.card').filter({ hasText: 'Risk Profile' }).first();
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel).toContainText(`${after.open} open of ${after.total}`);
});
