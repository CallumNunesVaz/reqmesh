import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Renaming a requirement from its detail page.
 *
 * An id is the YAML filename, every child's parent pointer, and every relation
 * target in the project, so the interesting assertions are about what else
 * moved — not just that the record answers to a new name.
 */
const P = DEMO_PROJECT;

async function openDetail(app: any, server: any, reqId: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/${reqId}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

async function get(app: any, reqId: string) {
  return app.evaluate(async ({ p, id }: any) => {
    const r = await fetch(`/api/projects/${p}/requirements/${id}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, { p: P, id: reqId });
}

test('the dialog prefills an id following the project scheme', async ({ app, server }) => {
  await openDetail(app, server, 'AFRM0001');

  await app.locator('[title="Rename (change the id)"]').click();
  await expect(app.getByRole('heading', { name: 'Rename requirement' })).toBeVisible();

  const field = app.getByLabel('New id');
  // Suggested from the parent's prefix plus the next free slot — same scheme
  // the create dialog uses.
  await expect(field).toHaveValue(/^[A-Z]+\d+$/, { timeout: 10000 });
  await expect(field).not.toHaveValue('AFRM0001');
});

test('renaming moves the record and follows it to the new url', async ({ app, server }) => {
  await openDetail(app, server, 'AFRM0009');

  await app.locator('[title="Rename (change the id)"]').click();
  const field = app.getByLabel('New id');
  await expect(field).not.toHaveValue('', { timeout: 10000 });
  await field.fill('AFRM7777');
  await app.getByRole('button', { name: 'Rename', exact: true }).click();

  await expect(app.getByText(/is now/)).toBeVisible({ timeout: 15000 });
  await app.getByRole('button', { name: 'Done' }).click();

  expect(await get(app, 'AFRM7777')).not.toBeNull();
  expect(await get(app, 'AFRM0009')).toBeNull();
  await expect(app).toHaveURL(/AFRM7777$/);
});

test('a duplicate id is refused and nothing moves', async ({ app, server }) => {
  await openDetail(app, server, 'AFRM0001');

  await app.locator('[title="Rename (change the id)"]').click();
  const field = app.getByLabel('New id');
  await expect(field).not.toHaveValue('', { timeout: 10000 });
  await field.fill('AFRM0002');
  await app.getByRole('button', { name: 'Rename', exact: true }).click();

  await expect(app.getByText(/already exists/)).toBeVisible({ timeout: 15000 });
  expect(await get(app, 'AFRM0001')).not.toBeNull();
});

test('renaming a parent repoints its children', async ({ app, server }) => {
  // AFRM0000 is the airframe root in the demo, with several children.
  await openDetail(app, server, 'AFRM0000');

  const childrenBefore = await app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    return (await r.json()).items.filter((x: any) => x.parent === 'AFRM0000').map((x: any) => x.id);
  }, P);
  expect(childrenBefore.length).toBeGreaterThan(0);

  await app.locator('[title="Rename (change the id)"]').click();
  const field = app.getByLabel('New id');
  await expect(field).not.toHaveValue('', { timeout: 10000 });
  await field.fill('AFRM9000');
  await app.getByRole('button', { name: 'Rename', exact: true }).click();
  await expect(app.getByText(/is now/)).toBeVisible({ timeout: 15000 });

  const stillOrphaned = await app.evaluate(async ({ p, kids }: any) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    const items = (await r.json()).items;
    return items.filter((x: any) => kids.includes(x.id) && x.parent !== 'AFRM9000').map((x: any) => x.id);
  }, { p: P, kids: childrenBefore });

  expect(stillOrphaned).toEqual([]);
});

test('no rename control in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[title="Rename (change the id)"]')).toHaveCount(0);
});
