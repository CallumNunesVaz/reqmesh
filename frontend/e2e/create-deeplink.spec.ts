import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('?new=1 opens blank create form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app.getByPlaceholder('Requirement name')).toHaveValue('');
});

test('?new=1&parent=<id> opens child form with parent selected', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const parentId = await app.locator('span.font-mono.text-\\[11px\\]').first().textContent();
  expect(parentId).toBeTruthy();

  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1&parent=${parentId}`);
  await app.waitForSelector('main');

  await expect(app.getByRole('heading', { name: new RegExp(parentId!) })).toBeVisible();

  const parentSelect = app.locator('form.card select').first();
  await expect(parentSelect).toHaveValue(parentId!);

  const idInput = app.locator('form.card input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();
  expect(newId).not.toBe(parentId);
});

test('bogus parent falls back to blank form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1&parent=INVALID123`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app.getByPlaceholder('Requirement name')).toHaveValue('');
});

test('query string is cleared after opening form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app).not.toHaveURL(/new=1/);
});

test('reloading after form opened does not reopen it', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await app.getByRole('button', { name: 'Cancel' }).click();
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0);

  await app.reload();
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0);
});

test('pressing n opens the form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.keyboard.press('n');
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();
});

test('pressing n while focus is in the search box does not open the form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const searchBox = app.getByPlaceholder('Search requirements…');
  await searchBox.focus();
  await app.keyboard.press('n');

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0);

  const searchValue = await searchBox.inputValue();
  expect(searchValue).toContain('n');
});

test('palette action opens the form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.keyboard.press('Control+k');
  await expect(app.getByPlaceholder('Jump to a requirement, verification, component…')).toBeVisible();

  await expect(app.getByRole('button', { name: 'New requirement Action' })).toBeVisible();

  await app.getByRole('button', { name: 'New requirement Action' }).click();

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();
});

test('n does nothing in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await app.keyboard.press('n');

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0);
});
