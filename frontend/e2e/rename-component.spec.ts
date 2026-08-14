import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Renaming a component from its detail page.
 *
 * A component's id is the YAML filename, every child's parent pointer, and every
 * inbound reference project-wide, so the interesting assertions are about what
 * else moved — not just that the record answers to a new name.
 */
const P = DEMO_PROJECT;

async function openDetail(app: any, server: any, componentId: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components/${componentId}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

async function get(app: any, componentId: string) {
  return app.evaluate(async ({ p, id }: any) => {
    const r = await fetch(`/api/projects/${p}/components/${id}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, { p: P, id: componentId });
}

test('renaming moves the record and follows it to the new url', async ({ app, server }) => {
  await openDetail(app, server, 'FUSE');

  await app.locator('[title="Rename (change the id)"]').click();
  await expect(app.getByRole('heading', { name: 'Rename component' })).toBeVisible();

  const field = app.getByLabel('New id');
  await expect(field).not.toHaveValue('', { timeout: 10000 });
  await field.fill('FUSE-9000');
  await app.getByRole('button', { name: 'Rename', exact: true }).click();

  await expect(app.getByText(/is now/)).toBeVisible({ timeout: 15000 });
  await app.getByRole('button', { name: 'Done' }).click();

  expect(await get(app, 'FUSE-9000')).not.toBeNull();
  expect(await get(app, 'FUSE')).toBeNull();
  await expect(app).toHaveURL(/FUSE-9000$/);
  // The renamed component is the record now on screen — its new id in the tree.
  await expect(app.locator('h1').filter({ hasText: 'FUSE-9000' })).toBeVisible();
});

test('renaming a parent repoints its children', async ({ app, server }) => {
  // FUSE is the fuselage assembly in the demo, with several child components.
  await openDetail(app, server, 'FUSE');

  const childrenBefore = await app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/components?limit=2000`, { credentials: 'include' });
    return (await r.json()).items.filter((x: any) => x.parent === 'FUSE').map((x: any) => x.id);
  }, P);
  expect(childrenBefore.length).toBeGreaterThan(0);

  await app.locator('[title="Rename (change the id)"]').click();
  const field = app.getByLabel('New id');
  await expect(field).not.toHaveValue('', { timeout: 10000 });
  await field.fill('FUSE-9001');
  await app.getByRole('button', { name: 'Rename', exact: true }).click();
  await expect(app.getByText(/is now/)).toBeVisible({ timeout: 15000 });
  await app.getByRole('button', { name: 'Done' }).click();

  await expect(app).toHaveURL(/FUSE-9001$/);

  const stillOrphaned = await app.evaluate(async ({ p, kids }: any) => {
    const r = await fetch(`/api/projects/${p}/components?limit=2000`, { credentials: 'include' });
    const items = (await r.json()).items;
    return items.filter((x: any) => kids.includes(x.id) && x.parent !== 'FUSE-9001').map((x: any) => x.id);
  }, { p: P, kids: childrenBefore });

  expect(stillOrphaned).toEqual([]);
});

test('no rename control in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components/FUSE`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[title="Rename (change the id)"]')).toHaveCount(0);
});
