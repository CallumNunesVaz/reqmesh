import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('a comment posted on a definition survives a reload', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/definitions`);
  await app.waitForSelector('main');
  await setEditMode(app);

  // The seeded MassBudget definition is written via write_item (no timestamps,
  // no history), so history is empty — but comments attach by entity id and must
  // work. Expand the card to reach the comment thread.
  await app.getByText('MassBudget', { exact: true }).first().click();

  const input = app.getByPlaceholder('Write a comment...');
  await input.waitFor({ state: 'visible', timeout: 15000 });
  await input.fill('e2e definition comment');
  await app.getByRole('button', { name: 'Send' }).click();

  await expect(app.getByText('e2e definition comment')).toBeVisible({ timeout: 15000 });

  await app.reload();
  await app.waitForSelector('main');
  await setEditMode(app);
  await app.getByText('MassBudget', { exact: true }).first().click();

  await expect(app.getByText('e2e definition comment')).toBeVisible({ timeout: 15000 });
});
