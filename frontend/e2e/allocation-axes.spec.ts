import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';

/**
 * Requirements against components, verification cases and risks.
 *
 * One page, three axes — all views of a link the backend's registry already
 * declares with `requirements` as its target. The tests below check the page
 * actually switches relationship rather than relabelling the same grid, since
 * that is the failure a shared implementation invites.
 */
const P = DEMO_PROJECT;

const AXES = [
  { tab: 'Components', verb: 'is satisfied by', label: 'Components' },
  { tab: 'Verification', verb: 'is verified by', label: 'Verification Cases' },
  { tab: 'Risks', verb: 'is threatened by', label: 'Risks' },
];

async function openMatrix(app: any, server: any) {
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await expect(app.getByRole('tab', { name: 'Components' })).toBeVisible({ timeout: 20_000 });
}

for (const axis of AXES) {
  test(`the ${axis.tab} matrix shows its own relationship`, async ({ app, server }) => {
    await signIn(app);
    await openMatrix(app, server);
    await app.getByRole('tab', { name: axis.tab }).click();
    await app.waitForTimeout(1200);

    await expect(app.locator('main')).toContainText(`Requirements × ${axis.label}`);
    await expect(app.locator('main')).toContainText(axis.verb);

    // The columns are the axis's own entities, not the previous axis's.
    const data = await api<any>(app, `/projects/${P}/allocation-matrix?axis=${
      axis.tab === 'Verification' ? 'verification' : axis.tab.toLowerCase()}`);
    expect(data.columns.length).toBeGreaterThan(0);
    const header = app.locator('thead');
    await expect(header).toContainText(data.columns[0].id);
  });
}

test('the three axes report different coverage on the seeded project', async ({ app }) => {
  await signIn(app);
  const [components, verification, risks] = await Promise.all([
    api<any>(app, `/projects/${P}/allocation-matrix?axis=components`),
    api<any>(app, `/projects/${P}/allocation-matrix?axis=verification`),
    api<any>(app, `/projects/${P}/allocation-matrix?axis=risks`),
  ]);
  // Same rows, genuinely different relationships — if the axis were ignored
  // these would be identical.
  expect(components.total_requirements).toBe(risks.total_requirements);
  const pcts = [components.allocation_pct, verification.allocation_pct, risks.allocation_pct];
  expect(new Set(pcts).size).toBe(3);
  expect(components.columns[0].id).not.toBe(risks.columns[0].id);
});

test('a cell on the risks matrix writes the risk, and survives a reload', async ({ app, server }) => {
  await signIn(app);
  await openMatrix(app, server);
  await setEditMode(app, true);
  await app.getByRole('tab', { name: 'Risks' }).click();
  await app.waitForTimeout(1200);

  const before = await api<any>(app, `/projects/${P}/allocation-matrix?axis=risks`);
  const riskId = before.columns[0].id;
  const reqId = before.rows.find((r: any) => !r.cells[riskId]).req_id;

  const row = app.locator('tbody tr').filter({ hasText: reqId }).first();
  const colIndex = before.columns.findIndex((c: any) => c.id === riskId);
  await row.locator('td').nth(colIndex + 1).click();
  await app.waitForTimeout(1500);

  // Written to the risk itself — the field the rest of the app reads.
  const risk = (await api<any[]>(app, `/projects/${P}/risks`)).find((r) => r.id === riskId);
  expect(risk.linked_requirements).toContain(reqId);

  await app.reload();
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Risks' }).click();
  await app.waitForTimeout(1500);
  const after = await api<any>(app, `/projects/${P}/allocation-matrix?axis=risks`);
  expect(after.rows.find((r: any) => r.req_id === reqId).cells[riskId]).toBe(true);
});

// ---------------------------------------------------------------------------
// Baselines matrix tab
// ---------------------------------------------------------------------------

/** Post a JSON body to the API, returning { status, body }. */
async function postApi(app: any, path: string, body: any, method = 'POST') {
  const cookies = await app.context().cookies();
  const token = cookies.find((c: any) => c.name === 'csrftoken')?.value || '';
  return app.evaluate(async ({ path, body, method, token }: any) => {
    const r = await fetch(`/api${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify(body),
      credentials: 'include',
    });
    const text = await r.text();
    let json: any;
    try { json = JSON.parse(text); } catch { json = { detail: text }; }
    return { status: r.status, body: json };
  }, { path, body, method, token });
}

/** Seed three baselines with due dates and symbols, in SRR → PDR → CDR order
 *  (alphabetically CDR < PDR < SRR, so rendering in sequence order is visible). */
async function seedBaselines(app: any) {
  await postApi(app, `/projects/${P}/baselines`, { name: 'SRR', symbol: 'S', due_date: '2026-01-01' });
  await postApi(app, `/projects/${P}/baselines`, { name: 'PDR', symbol: 'P', due_date: '2026-06-01' });
  await postApi(app, `/projects/${P}/baselines`, { name: 'CDR', symbol: 'C', due_date: '2026-12-01' });
}

test('the Baselines tab appears and switches the matrix', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await expect(app.getByRole('tab', { name: 'Components' })).toBeVisible({ timeout: 20_000 });

  await seedBaselines(app);

  // Navigate away and back to pick up the new baseline definitions
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');

  // The Baselines tab must be visible
  const tab = app.getByRole('tab', { name: 'Baselines' });
  await expect(tab).toBeVisible({ timeout: 10_000 });

  await tab.click();
  await app.waitForTimeout(1200);

  // The matrix must be for baselines
  await expect(app.locator('main')).toContainText('Requirements × Baselines');
});

test('baseline columns render in sequence order, not alphabetically', async ({ app, server }) => {
  await signIn(app);
  await seedBaselines(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  // Read the column header texts — they must be SRR, PDR, CDR (sequence order)
  const headers = app.locator('thead th').filter({ hasText: /^S/ }).locator('span').first();
  // Wait for at least one column header with text
  await expect(app.locator('thead')).toContainText('SRR');
  await expect(app.locator('thead')).toContainText('PDR');
  await expect(app.locator('thead')).toContainText('CDR');

  // Get the actual text order of the header th elements
  const headerTexts = await app.locator('thead th').allTextContents();
  // Filter out empty/irrelevant headers, keeping only the baseline name entries
  const baselineHeaders = headerTexts.filter((t: string) =>
    ['SRR', 'PDR', 'CDR'].some((n) => t.includes(n)),
  );
  // The columns must appear in sequence order: SRR, PDR, CDR
  const srrIdx = baselineHeaders.findIndex((t: string) => t.includes('SRR'));
  const pdrIdx = baselineHeaders.findIndex((t: string) => t.includes('PDR'));
  const cdrIdx = baselineHeaders.findIndex((t: string) => t.includes('CDR'));
  expect(srrIdx).toBeLessThan(pdrIdx);
  expect(pdrIdx).toBeLessThan(cdrIdx);
});

test('a due date appears in the column header', async ({ app, server }) => {
  await signIn(app);
  await seedBaselines(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  // SRR has due_date 2026-01-01 — it must appear in the header
  await expect(app.locator('thead')).toContainText('2026-01-01');
  await expect(app.locator('thead')).toContainText('2026-06-01');
  await expect(app.locator('thead')).toContainText('2026-12-01');
});

test('toggling a baseline cell persists across a reload', async ({ app, server }) => {
  await signIn(app);
  await seedBaselines(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await setEditMode(app, true);
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  // Fetch the matrix data to pick a cell to toggle
  const data = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  expect(data.columns.length).toBeGreaterThan(0);

  const colId = data.columns[0].id; // SRR
  // Find a requirement that is NOT currently allocated to this baseline
  const row = data.rows.find((r: any) => !r.cells[colId]);
  expect(row).toBeTruthy();
  const reqId = row.req_id;

  // Click the cell
  const rowLocator = app.locator('tbody tr').filter({ hasText: reqId }).first();
  const colIndex = data.columns.findIndex((c: any) => c.id === colId);
  await rowLocator.locator('td').nth(colIndex + 1).click();
  await app.waitForTimeout(1500);

  // Reload and verify
  await app.reload();
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1500);

  const after = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  const updatedRow = after.rows.find((r: any) => r.req_id === reqId);
  expect(updatedRow.cells[colId]).toBe(true);
});

test('toggling one baseline does not tick other cells in that row', async ({ app, server }) => {
  await signIn(app);
  await seedBaselines(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await setEditMode(app, true);
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  const data = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  expect(data.columns.length).toBeGreaterThanOrEqual(2);

  const colId = data.columns[0].id;
  // Find a row with no cells ticked at all
  const row = data.rows.find((r: any) =>
    Object.values(r.cells).every((v) => !v),
  );
  expect(row).toBeTruthy();

  // Toggle the first column's cell
  const rowLocator = app.locator('tbody tr').filter({ hasText: row.req_id }).first();
  const colIndex = data.columns.findIndex((c: any) => c.id === colId);
  await rowLocator.locator('td').nth(colIndex + 1).click();
  await app.waitForTimeout(1500);

  // Reload and verify only the selected cell is ticked
  await app.reload();
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1500);

  const after = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  const updatedRow = after.rows.find((r: any) => r.req_id === row.req_id);
  expect(updatedRow.cells[colId]).toBe(true);
  // No other column in that row should be true
  for (const [key, val] of Object.entries(updatedRow.cells)) {
    if (key !== colId) expect(val).toBe(false);
  }
});

test('moving a baseline down reorders columns on the matrix', async ({ app, server }) => {
  await signIn(app);
  // Names of its own, deliberately not the demo's. The seeded project defines
  // SRR/PDR/CDR/TRR *with* due dates, and creating over them keeps those dates —
  // so a reorder here would be refused by the monotonic check and the test would
  // be asserting against a rejected write rather than a reorder.
  await postApi(app, `/projects/${P}/baselines`, { name: 'ZZA', symbol: 'A' });
  await postApi(app, `/projects/${P}/baselines`, { name: 'ZZB', symbol: 'B' });
  await postApi(app, `/projects/${P}/baselines`, { name: 'ZZC', symbol: 'C' });
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  // Confirm initial order: SRR, PDR, CDR
  const ours = (d: any) => d.columns.map((c: any) => c.id).filter((i: string) => i.startsWith('ZZ'));
  const beforeData = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  expect(ours(beforeData)).toEqual(['ZZA', 'ZZB', 'ZZC']);

  // Go to baselines page and move PDR down
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await setEditMode(app, true);
  await app.waitForTimeout(1000);

  // Click "Move down" on PDR — find its card and click the button inside it
  const pdrCard = app.locator('.card').filter({ hasText: 'ZZB' }).first();
  await pdrCard.locator('button[title="Move down"]').click();
  await app.waitForTimeout(2000);

  // Go back to matrix and check the new order: SRR, CDR, PDR
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await app.getByRole('tab', { name: 'Baselines' }).click();
  await app.waitForTimeout(1200);

  const afterData = await api<any>(app, `/projects/${P}/allocation-matrix?axis=baselines`);
  expect(ours(afterData)).toEqual(['ZZA', 'ZZC', 'ZZB']);
});

test('a backwards due date shows the server error message', async ({ app, server }) => {
  await signIn(app);
  // Entirely its own baselines. The seeded project already defines SRR/PDR/CDR/TRR
  // with ascending due dates, so borrowing those names meant creating over
  // existing rows (409) and comparing against dates this test never set.
  await postApi(app, `/projects/${P}/baselines`, { name: 'YYA', due_date: '2027-01-01' });
  await postApi(app, `/projects/${P}/baselines`, { name: 'YYB', due_date: '2027-02-01' });
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await setEditMode(app, true);
  await app.waitForTimeout(1000);

  // Pull YYB back before YYA, which the server must refuse.
  const card = app.locator('.card').filter({ hasText: 'YYB' }).first();
  await card.locator('button[title="Edit baseline"]').click();
  await app.waitForTimeout(500);
  await app.locator('input[type="date"]').fill('2026-01-01');
  await app.waitForTimeout(300);
  await app.getByRole('button', { name: 'Save' }).click();
  await app.waitForTimeout(1500);

  // The error surfaces as a toast, which Layout renders outside `main`.
  await expect(app.locator('body')).toContainText('Due dates must not go backwards');
});

