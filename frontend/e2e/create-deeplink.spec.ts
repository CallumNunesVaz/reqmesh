import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('?new=1 opens blank create form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  // No setEditMode here: the deep link turns edit mode on itself ("following a
  // create link is an explicit intent to edit"). Calling it raced — the helper
  // samples EDITING before the effect fires, which waits for requirements to
  // load, so it decided to click a toggle the dialog backdrop then covered, and
  // waited out the full 60s timeout. That the app enables edit mode is exactly
  // what this test should be proving, so asserting it directly is also truer.
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app.getByPlaceholder('Requirement name')).toHaveValue('');
});

test('?new=1&parent=<id> opens child form with parent selected', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const parentId = await app.locator('span.font-mono.text-2xs').first().textContent();
  expect(parentId).toBeTruthy();

  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1&parent=${parentId}`);
  await app.waitForSelector('main');

  await expect(app.getByRole('heading', { name: new RegExp(parentId!) })).toBeVisible();

  const parentSelect = app.locator('[role="dialog"] select').first();
  await expect(parentSelect).toHaveValue(parentId!);

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();
  expect(newId).not.toBe(parentId);
});

test('bogus parent falls back to blank form', async ({ app, server }) => {
  await signIn(app);
  // Edit mode first: the link opens the modal on load, and its overlay would
  // cover the edit toggle.
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1&parent=INVALID123`);
  await app.waitForSelector('main');

  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app.getByPlaceholder('Requirement name')).toHaveValue('');
});

test('query string is cleared after opening form', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  // See the first test: the deep link enables edit mode, so calling the helper
  // here races the dialog backdrop.
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();

  await expect(app).not.toHaveURL(/new=1/);
});

test('reloading after form opened does not reopen it', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');
  // See the first test: the deep link enables edit mode, so calling the helper
  // here races the dialog backdrop.
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

test('the deep link does nothing for a user who cannot edit', async ({ app, server }) => {
  // Not signed in: a cold load resolves to the guest/viewer role. The gate is
  // the *role*, not the edit-mode toggle — an admin arriving on this link is
  // opting into editing, and having it silently do nothing for them would make
  // the link useless on a cold load, since the toggle defaults off.
  await app.goto(`${server.baseURL}/project/${P}/requirements?new=1`);
  await app.waitForSelector('main');

  // The effect that clears the param bails out until the requirements have
  // loaded, so waiting a fixed 1500ms raced the fetch: on a slow machine the
  // sleep expired first and the param was still there. Poll the URL for the
  // outcome instead of guessing how long the load takes.
  await expect.poll(() => app.url(), { timeout: 15_000 }).not.toContain('new=1');
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0);
});
