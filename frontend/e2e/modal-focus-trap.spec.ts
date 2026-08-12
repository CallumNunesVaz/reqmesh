import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The one behavioural change `Modal` makes: it traps focus and declares a
 * role, where every dialog before it let Tab walk straight into the page
 * behind. These prove the trap, the escape-close, and that the migrated bulk
 * bar still drives a real mutation.
 */
const P = DEMO_PROJECT;
const REQ = 'AFRM0001';

const focusedInDialog = (app: any) =>
  app.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null);

async function openDecisions(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/decisions`);
  await setEditMode(app, true);
}

test('a dialog traps focus and does not reach the page behind', async ({ app, server }) => {
  await openDecisions(app, server);

  await app.locator('[title="Delete"]').first().click();
  const dialog = app.getByRole('dialog');
  await expect(dialog).toBeVisible();

  // Focus lands inside the dialog on open.
  await expect.poll(() => focusedInDialog(app), { timeout: 10_000 }).toBe(true);

  // Tab and Shift+Tab cycle within the dialog; they never escape to the page.
  for (let i = 0; i < 6; i++) {
    await app.keyboard.press('Tab');
    expect(await focusedInDialog(app), `focus escaped after Tab #${i + 1}`).toBe(true);
  }
  for (let i = 0; i < 6; i++) {
    await app.keyboard.press('Shift+Tab');
    expect(await focusedInDialog(app), `focus escaped after Shift+Tab #${i + 1}`).toBe(true);
  }
});

test('Escape closes the shortcut help dialog', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');

  await app.keyboard.press('Control+/');
  const dialog = app.getByRole('dialog');
  await expect(dialog).toBeVisible();

  await app.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

test('the bulk bar still applies an action', async ({ app, server }) => {
  await signIn(app);

  // Define a baseline and put it on the requirement, then drive the bulk bar.
  const token = (await app.context().cookies()).find((c: any) => c.name === 'csrftoken')?.value || '';
  const put = (path: string, body: unknown, method: 'PUT' | 'PATCH') =>
    app.evaluate(async ({ p, b, t, m }: any) => {
      const r = await fetch(p, {
        method: m,
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t },
        body: JSON.stringify(b),
      });
      return r.status;
    }, { p: path, b: body, t: token, m: method });
  const baselinesOf = () =>
    app.evaluate(async ({ project, id }: any) => {
      const r = await fetch(`/api/projects/${project}/requirements/${id}`, { credentials: 'include' });
      return (await r.json()).baselines ?? [];
    }, { project: P, id: REQ });

  await put(`/api/projects/${P}`, { baselines: [{ name: 'E2E' }] }, 'PATCH');
  await put(`/api/projects/${P}/requirements/${REQ}`, { baselines: [] }, 'PUT');

  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.getByText('Select all').first().click();
  await expect(app.getByText(/\d+ selected/)).toBeVisible();

  await app.locator('select[title^="Adds this baseline"]').selectOption('E2E');
  await expect(app.getByText(/\d+ selected/)).toHaveCount(0, { timeout: 15_000 });

  expect(await baselinesOf()).toEqual(['E2E']);
});
