import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Successful mutations used to be silent: creating or deleting a decision gave
 * no confirmation at all. This drives a create and a delete through the UI and
 * asserts the toast *text*, not merely that some alert appeared — the point is
 * that the message names what happened.
 */

async function openDecisions(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/decisions`);
  await setEditMode(app, true);
}

test('creating and deleting a decision each raise a success toast', async ({ app, server }) => {
  const id = `ADR-E2E-${Date.now()}`;

  await openDecisions(app, server);

  // Create.
  await app.getByRole('button', { name: 'New Decision' }).click();
  await app.getByPlaceholder('ADR-001').fill(id);
  await app.getByRole('button', { name: 'Create' }).click();

  await expect(
    app.locator('[role="alert"]').filter({ hasText: `Decision ${id} created` }),
  ).toBeVisible({ timeout: 10_000 });

  // Delete the same record, then confirm the delete toast.
  const row = app.locator(`#entity-${id}`);
  await expect(row).toBeVisible();
  await row.hover();
  await row.locator('[title="Delete"]').click();

  const dialog = app.locator('.fixed.inset-0.z-\\[60\\]');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Delete' }).click();
  await expect(dialog).toBeHidden();

  await expect(
    app.locator('[role="alert"]').filter({ hasText: `Decision ${id} deleted` }),
  ).toBeVisible({ timeout: 10_000 });
});
