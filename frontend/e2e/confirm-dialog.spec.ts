import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Deletes used to be split between the browser's own `window.confirm` and the
 * in-app dialog, so half of them showed OS chrome and two showed nothing at
 * all. These assert the surviving path end to end on a page that used the
 * native prompt before: the dialog appears, Cancel is genuinely a no-op, and
 * the confirm button is labelled for the action rather than saying "Confirm".
 *
 * The overlay is matched by its z-index utility class rather than a role,
 * because no modal in the app declares `role="dialog"` yet. When that changes,
 * this selector should become `getByRole('dialog')`.
 */
const OVERLAY = '.fixed.inset-0.z-\\[60\\]';

async function openDecisions(app: any, server: any) {
  await signIn(app);
  // Edit mode after the navigation, not before: a full page load resets it to
  // viewing, and the row actions only render when editing.
  await app.goto(`${server.baseURL}/project/${P}/decisions`);
  await setEditMode(app, true);
}

test('cancelling the delete dialog leaves the record alone', async ({ app, server }) => {
  const before = await api(app, `/projects/${P}/decisions`);
  const target = (before.items ?? before)[0];
  expect(target, 'the demo project needs at least one decision').toBeTruthy();

  await openDecisions(app, server);

  await app.locator(`[title="Delete"]`).first().click();

  const dialog = app.locator(OVERLAY);
  await expect(dialog).toBeVisible();
  // The action button names the action — it said "Confirm" for every dialog.
  await expect(dialog.getByRole('button', { name: 'Delete' })).toBeVisible();

  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();

  const after = await api(app, `/projects/${P}/decisions`);
  const ids = (after.items ?? after).map((d: any) => d.id);
  expect(ids, 'cancel must not delete anything').toContain(target.id);
});

test('confirming the delete dialog removes the record', async ({ app, server }) => {
  const before = await api(app, `/projects/${P}/decisions`);
  const target = (before.items ?? before)[0];
  expect(target).toBeTruthy();

  await openDecisions(app, server);

  await app.locator(`[title="Delete"]`).first().click();

  const dialog = app.locator(OVERLAY);
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Delete' }).click();
  await expect(dialog).toBeHidden();

  await expect
    .poll(async () => {
      const after = await api(app, `/projects/${P}/decisions`);
      return (after.items ?? after).map((d: any) => d.id);
    }, { timeout: 10_000 })
    .not.toContain(target.id);
});
