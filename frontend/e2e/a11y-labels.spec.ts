import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Every form field must be programmatically labelled. `getByLabel` only matches
 * a control whose accessible name comes from a *properly associated* label
 * (wrapping `<label>` or `htmlFor`/`id`), so these assertions fail against the
 * old sibling-label markup and pass once `label-has-associated-control` is at
 * zero. One representative field per page, across three different pages.
 */
const P = DEMO_PROJECT;

test('create requirement dialog labels its name field', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.keyboard.press('n');
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  const name = app.locator('[role="dialog"]').getByLabel('Name');
  await expect(name).toBeVisible();
  await name.fill('A11y labelled requirement');
  await expect(name).toHaveValue('A11y labelled requirement');
});

test('requirement detail name field is labelled', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const name = app.getByLabel('Name');
  await expect(name).toBeVisible();
  await name.fill('A11y labelled requirement detail');
  await expect(name).toHaveValue('A11y labelled requirement detail');
});

test('project settings git author field is labelled', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/settings`);
  await app.waitForSelector('main');

  await expect(app.getByLabel('Author Name')).toBeVisible();
});
