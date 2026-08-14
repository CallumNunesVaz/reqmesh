import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Column alignment, add-child and inherited quantity on the component tree.
 *
 * The eye toggle used to sit at the far right on a row carrying "satisfies N"
 * and next to the title on a row without one, because `ml-auto` lived on the
 * optional badge. The trailing controls now occupy a fixed column regardless,
 * and the name span takes the free space.
 */

async function getJson(app: any, path: string) {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api${p}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, path);
}

async function eyeX(app: any, id: string): Promise<number | undefined> {
  const box = await app.locator(`#entity-${id} [title="Shown in graph"]`).boundingBox();
  return box?.x;
}

async function open(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

async function createComponent(app: any, { id, name, parent }: { id: string; name: string; parent?: string }) {
  await app.getByRole('button', { name: 'New Component' }).click();
  await expect(app.getByRole('textbox', { name: 'ID' })).toBeVisible();
  await app.getByRole('textbox', { name: 'ID' }).fill(id);
  await app.getByRole('textbox', { name: 'Name' }).fill(name);
  if (parent) await app.getByRole('combobox', { name: 'Parent' }).selectOption(parent);
  await app.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(app.locator(`#entity-${id}`)).toBeVisible({ timeout: 15_000 });
}

test('the eye toggle keeps the same column with and without a "satisfies" badge', async ({ app, server }) => {
  await open(app, server);

  // Every demo component satisfies something, so add a top-level row with no
  // badge to compare against. It lands at the same depth as C172 (root).
  await createComponent(app, { id: 'ALIGN-0', name: 'Align probe' });

  const withBadge = await eyeX(app, 'C172');
  const withoutBadge = await eyeX(app, 'ALIGN-0');
  expect(withBadge).toBeTruthy();
  expect(withoutBadge).toBeTruthy();
  expect(Math.abs(withBadge! - withoutBadge!)).toBeLessThan(1);
});

test('the control column does not move when a row is hovered', async ({ app, server }) => {
  await open(app, server);

  const before = await eyeX(app, 'C172');
  expect(before).toBeTruthy();

  await app.locator('#entity-C172').hover();
  // The hover-revealed controls (grip, duplicate, add-child) reserve their
  // space via opacity, so the eye column must not shift.
  const after = await eyeX(app, 'C172');
  expect(after).toBeTruthy();
  expect(Math.abs(after! - before!)).toBeLessThan(1);
});

test('add-child opens the create form pre-set to that parent and the child lands under it', async ({ app, server }) => {
  await open(app, server);

  await app.locator('#entity-C172 [title="Add child component"]').click();

  await expect(app.getByRole('combobox', { name: 'Parent' })).toHaveValue('C172');

  await app.getByRole('textbox', { name: 'ID' }).fill('ALIGNCHILD');
  await app.getByRole('textbox', { name: 'Name' }).fill('Align child');
  await app.getByRole('button', { name: 'Create', exact: true }).click();

  await expect(app.locator('#entity-ALIGNCHILD')).toBeVisible({ timeout: 15_000 });

  const created = await getJson(app, `/projects/${P}/components/ALIGNCHILD`);
  expect(created).not.toBeNull();
  expect(created.parent).toBe('C172');
});

test('a nested component displays its rolled-up quantity', async ({ app, server }) => {
  await open(app, server);

  // FQSND is 2× under TANK (2×) under WING (1×): 4× in the build.
  const row = app.locator('#entity-FQSND');
  await expect(row).toContainText('×2 (4×)');

  // A single-instance row under a single-instance parent stays quiet.
  await expect(app.locator('#entity-C172')).not.toContainText(/\(.*×\)/);
});
