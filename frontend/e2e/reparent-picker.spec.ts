import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Moving a requirement goes through a picker, not a free-text box.
 *
 * The box accepted any string: a descendant (a cycle the single-item PUT would
 * have refused), or a typo (an orphan). Worse, the client always sent
 * re_prefix=true, so an ordinary move could rewrite a whole subtree's ids
 * across the project — irreversibly, since there is no rename endpoint.
 */
const P = DEMO_PROJECT;

async function reqCount(app: any): Promise<number> {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    return (await r.json()).total as number;
  }, P);
}

/** Open the per-row move dialog for whichever row is first in the tree. */
async function openMove(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await app.locator('[title="Move to parent"]').first().click({ force: true });
  await expect(app.getByRole('heading', { name: /^Move 1 item/ })).toBeVisible();
}

test('the picker always offers top level and filters by search', async ({ app, server }) => {
  await openMove(app, server);

  await expect(app.getByText('Top level')).toBeVisible();

  await app.getByPlaceholder('Search by id or name...').fill('zzz-no-such-id');
  await expect(app.getByText('No eligible parent matches that search.')).toBeVisible();
});

test('re-prefixing is off by default and warns that it cannot be undone', async ({ app, server }) => {
  await openMove(app, server);

  // "Top level" never renames, so pick a real destination — the first
  // eligible row the picker offers.
  const candidate = app.locator('.max-h-72 button:has(span.font-mono)').first();
  await expect(candidate).toBeVisible();
  await candidate.click();

  const box = app.getByRole('checkbox');
  await expect(box).toBeVisible();
  // The behaviour change: this used to be hard-coded on, with no dialog at all.
  await expect(box).not.toBeChecked();

  await box.check();
  // Target the rename warning specifically. "cannot be undone" also appears in
  // the checkbox's own help text, which is present the moment the checkbox is —
  // so matching on that phrase passed without the preview ever arriving, and
  // started failing as a strict-mode violation once both rendered in time.
  await expect(app.getByText(/\d+ ids? will be renamed/)).toBeVisible({ timeout: 15000 });
});

test('choosing top level reports that no ids change', async ({ app, server }) => {
  await openMove(app, server);

  await app.getByText('Top level').click();
  await expect(app.getByText('No ids change. Only the parent is updated.')).toBeVisible({ timeout: 15000 });
});

test('cancelling the dialog changes nothing', async ({ app, server }) => {
  await openMove(app, server);
  const before = await reqCount(app);

  // Cancel only exists once a destination is chosen; at the picker step the
  // way out is the close control.
  await app.locator('[title="Close"]').click();
  await expect(app.getByRole('heading', { name: /^Move 1 item/ })).toHaveCount(0);

  expect(await reqCount(app)).toBe(before);
});
