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
