import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * The four card pages that gained selection must behave like their equipped
 * siblings: checkbox select, Shift-range select, and a bulk delete through the
 * shared bar that removes exactly the ticked records and leaves the rest alone.
 *
 * Each test selects the first row, then Shift-clicks the third, so a range of
 * three is swept. The post-delete assertion is the "others remain" half — an
 * off-by-one in the range would leave one of the three behind or take one of
 * the rest with it.
 */

async function ids(page: any, path: string, kind: 'items' | 'states'): Promise<string[]> {
  const body = await api(page, `/projects/${P}${path}`);
  const list = kind === 'states' ? body.states : (body.items ?? body);
  return list.map((x: any) => x[kind === 'states' ? 'name' : 'id']);
}

/** Click a row's checkbox; `shift` sweeps a range from the last anchor. */
async function check(page: any, id: string, shift = false) {
  const box = page.locator(`#entity-${id} svg.lucide-square`).first();
  await box.click(shift ? { modifiers: ['Shift'] } : {});
}

/** Confirm the bulk bar shows and drive its Delete through the dialog. */
async function bulkDelete(page: any) {
  const bar = page.locator('div.sticky.bottom-6');
  await expect(bar).toBeVisible();
  await bar.getByRole('button', { name: 'Delete' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(dialog).toBeHidden();
}

async function selectFirstThree(page: any, ordered: string[]) {
  expect(ordered.length, 'need at least five rows to prove the rest survive').toBeGreaterThanOrEqual(5);
  await check(page, ordered[0]);
  await check(page, ordered[2], true);
  await expect(page.getByText('3 selected')).toBeVisible();
}

async function assertDeletedExactly(
  page: any,
  path: string,
  kind: 'items' | 'states',
  ordered: string[],
) {
  const kept = ordered.slice(3);
  await expect
    .poll(async () => ids(page, path, kind), { timeout: 10_000 })
    .toEqual(kept);
}

async function open(page: any, server: any, route: string) {
  await signIn(page);
  await page.goto(`${server.baseURL}/project/${P}/${route}`, { waitUntil: 'commit' });
  await setEditMode(page, true);
}

test('decisions: select, shift-range, bulk delete', async ({ app, server }) => {
  const ordered = await ids(app, '/decisions', 'items');
  await open(app, server, 'decisions');
  await selectFirstThree(app, ordered);
  await bulkDelete(app);
  await assertDeletedExactly(app, '/decisions', 'items', ordered);
});

test('analysis cases: select, shift-range, bulk delete', async ({ app, server }) => {
  const ordered = await ids(app, '/analysis', 'items');
  await open(app, server, 'analysis');
  await selectFirstThree(app, ordered);
  await bulkDelete(app);
  await assertDeletedExactly(app, '/analysis', 'items', ordered);
});

test('definitions: select, shift-range, bulk delete', async ({ app, server }) => {
  const ordered = await ids(app, '/definitions', 'items');
  await open(app, server, 'definitions');
  await selectFirstThree(app, ordered);
  await bulkDelete(app);
  await assertDeletedExactly(app, '/definitions', 'items', ordered);
});

test('system states: select, shift-range, bulk delete', async ({ app, server }) => {
  const ordered = await ids(app, '/system-states', 'states');
  await open(app, server, 'system-states');
  await selectFirstThree(app, ordered);
  await bulkDelete(app);
  await assertDeletedExactly(app, '/system-states', 'states', ordered);
});
