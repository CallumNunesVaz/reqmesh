import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The naming standard must actually govern creation: every create form prefills
 * a conforming id from the project's configured scheme, and after a create the
 * next open offers the *next* id rather than a duplicate.
 *
 * The components create form is wired up in a follow-up (tasks 111/116 own the
 * components pages), so it is deliberately absent here.
 */
const P = DEMO_PROJECT;

async function openPage(app: any, server: any, path: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}${path}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

async function readId(input: any): Promise<string> {
  await expect(input).not.toHaveValue('');
  return (await input.inputValue()).trim();
}

test('risk form prefills a conforming id and increments after create', async ({ app, server }) => {
  await openPage(app, server, '/risks');

  await app.getByRole('button', { name: 'New Risk' }).click();
  const idInput = app.getByPlaceholder('RSK-001');
  const first = await readId(idInput);
  expect(first).toMatch(/^RSK\d+$/);

  await app.getByPlaceholder('Risk title').fill('Naming standard risk');
  await app.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(idInput).toHaveCount(0, { timeout: 15000 });

  await app.getByRole('button', { name: 'New Risk' }).click();
  const second = await readId(idInput);
  expect(second).not.toBe(first);
  expect(second).toMatch(/^RSK\d+$/);
});

test('verification form prefills a conforming id and increments after create', async ({ app, server }) => {
  await openPage(app, server, '/verification');

  await app.getByRole('button', { name: 'New Verification Case' }).click();
  const idInput = app.getByPlaceholder('VC-001');
  const first = await readId(idInput);
  expect(first).toMatch(/^VC\d+$/);

  await app.getByPlaceholder('Verification case name').fill('Naming standard case');
  await app.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(idInput).toHaveCount(0, { timeout: 15000 });

  await app.getByRole('button', { name: 'New Verification Case' }).click();
  const second = await readId(idInput);
  expect(second).not.toBe(first);
  expect(second).toMatch(/^VC\d+$/);
});

test('change request form prefills a conforming id and increments after create', async ({ app, server }) => {
  await openPage(app, server, '/change-requests');

  await app.getByRole('button', { name: 'New Change Request' }).click();
  const idInput = app.getByPlaceholder('CR-001');
  const first = await readId(idInput);
  expect(first).toMatch(/^CR\d+$/);

  await app.getByPlaceholder('Change request title').fill('Naming standard CR');
  await app.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(idInput).toHaveCount(0, { timeout: 15000 });

  await app.getByRole('button', { name: 'New Change Request' }).click();
  const second = await readId(idInput);
  expect(second).not.toBe(first);
  expect(second).toMatch(/^CR\d+$/);
});

test('specification form prefills a conforming id and increments after create', async ({ app, server }) => {
  await openPage(app, server, '/specifications');

  await app.getByRole('button', { name: 'New Specification' }).click();
  const idInput = app.getByPlaceholder('SRS-001');
  const first = await readId(idInput);
  expect(first).toMatch(/^SPEC-[a-z0-9]+$/);

  await app.getByPlaceholder('Specification name').fill('Naming standard spec');
  await app.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(idInput).toHaveCount(0, { timeout: 15000 });

  await app.getByRole('button', { name: 'New Specification' }).click();
  const second = await readId(idInput);
  expect(second).not.toBe(first);
  expect(second).toMatch(/^SPEC-[a-z0-9]+$/);
});

test('requirement modal keeps prefilling a conforming id after create', async ({ app, server }) => {
  await openPage(app, server, '/requirements');

  await app.getByRole('button', { name: 'New Requirement' }).first().click();
  const idInput = app.locator('[role="dialog"] input.font-mono');
  const first = await readId(idInput);

  await app.getByPlaceholder('Requirement name').fill('Naming standard requirement');
  await app.getByRole('button', { name: 'Create requirement' }).click();
  await expect(app.getByRole('heading', { name: 'New Requirement' })).toHaveCount(0, { timeout: 15000 });

  await app.getByRole('button', { name: 'New Requirement' }).first().click();
  const second = await readId(idInput);
  expect(second).not.toBe(first);
});
