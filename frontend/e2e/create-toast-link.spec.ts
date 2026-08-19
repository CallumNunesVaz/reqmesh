import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Creating a requirement used to leave the operator hunting for the new row
 * after the list reloaded. The success toast now carries the new id as a link
 * to the requirement's detail page — the Jira "issue created" pattern.
 */

test('creating a requirement raises a toast linking to its detail page', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.getByRole('button', { name: 'New Requirement' }).first().click();
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  await app.getByPlaceholder('Requirement name').fill('Toast link target');
  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0, { timeout: 15_000 });

  const toast = app.locator('[role="alert"]').filter({ hasText: `Created ${newId}` });
  await expect(toast).toBeVisible({ timeout: 10_000 });

  await toast.getByRole('link', { name: newId }).click();

  await expect(app).toHaveURL(new RegExp(`${newId}$`));
  await expect(app.getByRole('heading', { name: newId, exact: true })).toBeVisible();
});
