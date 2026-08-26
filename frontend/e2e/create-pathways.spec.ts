import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

async function openDetail(app: any, server: any, reqId: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/${reqId}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

async function getReq(app: any, reqId: string) {
  return app.evaluate(async ({ p, id }: any) => {
    const r = await fetch(`/api/projects/${p}/requirements/${id}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, { p: P, id: reqId });
}

test('add child from tree row prefills parent and a fresh id', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.locator('[title="Add child requirement"]').first().click();

  await expect(app.getByRole('heading', { name: /New child of/ })).toBeVisible();

  const parentSelect = app.locator('[role="dialog"] select').first();
  const parentValue = await parentSelect.inputValue();
  expect(parentValue).not.toBe('');

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  const existing = await getReq(app, newId);
  expect(existing).toBeNull();
});

test('creating a child from a tree row sets the correct parent', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const rowParent = await app.locator('span.font-mono.text-2xs').first().textContent();
  expect(rowParent).toBeTruthy();

  await app.locator('[title="Add child requirement"]').first().click();
  await expect(app.getByRole('heading', { name: /New child of/ })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: /New child of/ })).toHaveCount(0, { timeout: 15000 });

  const created = await getReq(app, newId);
  expect(created).not.toBeNull();
  expect(created.parent).toBe(rowParent);
});

test('duplicate from tree row copies name, type and priority', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const source = await app.locator('span.font-mono.text-2xs').first().textContent();
  expect(source).toBeTruthy();

  await app.locator('[title="Duplicate requirement"]').first().click();
  await expect(app.getByRole('heading', { name: /Duplicate/ })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();
  expect(newId).not.toBe(source);

  const nameInput = app.locator('[role="dialog"] input[placeholder="Requirement name"]');
  const nameValue = await nameInput.inputValue();
  expect(nameValue).toContain('(copy)');

  const sourceReq = await getReq(app, source!);
  expect(sourceReq).not.toBeNull();

  const cardSelects = app.locator('[role="dialog"] select');
  const typeValue = await cardSelects.nth(1).inputValue();
  expect(typeValue).toBe(sourceReq.type);

  const priorityValue = await cardSelects.nth(2).inputValue();
  expect(priorityValue).toBe(sourceReq.priority);
});

test('duplicated requirement carries no relations', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.locator('[title="Duplicate requirement"]').first().click();
  await expect(app.getByRole('heading', { name: /Duplicate/ })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: /Duplicate/ })).toHaveCount(0, { timeout: 15000 });

  const created = await getReq(app, newId);
  expect(created).not.toBeNull();
  expect(created.relations || []).toEqual([]);
});

test('add child from detail page navigates to the new requirement', async ({ app, server }) => {
  await openDetail(app, server, 'AFRM0001');

  await app.locator('[title="Add child requirement"]').click();
  await expect(app.getByRole('heading', { name: /New child of/ })).toBeVisible();

  const idInput = app.locator('[role="dialog"] input.font-mono');
  const newId = await idInput.inputValue();
  expect(newId).toBeTruthy();

  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: /New child of/ })).toHaveCount(0, { timeout: 15000 });

  await expect(app).toHaveURL(new RegExp(`${newId}$`));
  const created = await getReq(app, newId);
  expect(created).not.toBeNull();
  expect(created.parent).toBe('AFRM0001');
});

test('add child and duplicate buttons invisible in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[title="Add child requirement"]')).toHaveCount(0);
  await expect(app.locator('[title="Duplicate requirement"]')).toHaveCount(0);
});

test('detail page add child and duplicate buttons invisible in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[title="Add child requirement"]')).toHaveCount(0);
  await expect(app.locator('[title="Duplicate requirement"]')).toHaveCount(0);
});

test('cancelling a duplicate does not leak its values into the next blank form', async ({ app, server }) => {
  // The form is only cleared after a *successful* create, so a cancelled
  // duplicate used to leave its name and description sitting in the fields the
  // next time the blank "New Requirement" form was opened.
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.locator('[title="Duplicate requirement"]').first().click({ force: true });
  await expect(app.getByRole('heading', { name: /^Duplicate / })).toBeVisible();
  const dupName = await app.getByPlaceholder('Requirement name').inputValue();
  expect(dupName).toContain('(copy)');
  await app.locator('[title="Close"], button:has-text("Cancel")').first().click();
  await expect(app.getByRole('heading', { name: /^Duplicate / })).toHaveCount(0);

  await app.getByRole('button', { name: 'New Requirement' }).first().click();
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toBeVisible();
  const blankName = await app.getByPlaceholder('Requirement name').inputValue();
  expect(blankName).toBe('');
});
