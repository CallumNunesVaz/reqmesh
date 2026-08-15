import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';
import type { Locator, Page } from '@playwright/test';

/**
 * A component's Parent field must offer components, never requirement groups.
 *
 * The report was that a component's Parent dropdown listed requirement groups.
 * Every parent selector in the source reads from the component list, so the
 * honest finding is a naming collision: the demo project's components are named
 * after subsystems ("Wing Assembly", "Empennage", "Landing Gear"), and the
 * requirement tree's top-level branches carry the same names. These tests pin
 * the real contract — the *ids* are component ids, disjoint from requirement
 * ids, and a component is never offered itself or its own descendants.
 */
const P = DEMO_PROJECT;

interface PagedItem { id: string; parent?: string | null }
interface Paged { items: PagedItem[]; total: number }

async function listIds(app: Page, collection: 'components' | 'requirements'): Promise<string[]> {
  const page = await api<Paged>(app, `/projects/${P}/${collection}?limit=2000`);
  return page.items.map((i) => i.id);
}

/** A root's id plus every id beneath it (mirrors lib/hierarchy.ts branchIds). */
async function branch(app: Page, rootId: string): Promise<Set<string>> {
  const items = await api<Paged>(app, `/projects/${P}/components?limit=2000`);
  const ids = new Set<string>([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of items.items) {
      if (c.parent && ids.has(c.parent) && !ids.has(c.id)) {
        ids.add(c.id);
        grew = true;
      }
    }
  }
  return ids;
}

async function optionValues(select: Locator): Promise<string[]> {
  return select.locator('option').evaluateAll((opts) =>
    opts.map((o) => (o as HTMLOptionElement).value));
}

/** The Parent select: the only labelled "Parent" on either page. */
function parentSelect(app: Page): Locator {
  return app.locator('label', { hasText: 'Parent' }).locator('select');
}

test('component detail parent select offers only other components', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components/FUSE01`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  const compIds = new Set(await listIds(app, 'components'));
  const reqIds = new Set(await listIds(app, 'requirements'));
  // FUSE01 has both a parent and children, so the picker is populated and the
  // self/descendant exclusion is actually exercised.
  const own = await branch(app, 'FUSE01');

  const select = parentSelect(app);
  await expect(select).toBeVisible({ timeout: 15_000 });
  const options = (await optionValues(select)).filter((v) => v !== '');

  expect(options.length, 'FUSE01 has eligible parents other than its own branch').toBeGreaterThan(0);

  for (const value of options) {
    expect(compIds.has(value), `parent option ${value} is a component id`).toBe(true);
    expect(reqIds.has(value), `parent option ${value} is not a requirement id`).toBe(false);
    expect(own.has(value), `parent option ${value} is not FUSE01 or one of its descendants`).toBe(false);
  }
});

test('component create form parent select offers only components', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  await app.getByRole('button', { name: 'New Component' }).click();

  const compIds = new Set(await listIds(app, 'components'));
  const reqIds = new Set(await listIds(app, 'requirements'));

  const select = parentSelect(app);
  await expect(select).toBeVisible({ timeout: 15_000 });
  const options = (await optionValues(select)).filter((v) => v !== '');

  expect(options.length, 'create form offers at least one component parent').toBeGreaterThan(0);

  for (const value of options) {
    expect(compIds.has(value), `parent option ${value} is a component id`).toBe(true);
    expect(reqIds.has(value), `parent option ${value} is not a requirement id`).toBe(false);
  }
});

/**
 * A stored parent that resolves to nothing must be *shown*, not swallowed.
 *
 * Assigning a `<select>` a value no `<option>` carries sets selectedIndex to
 * -1, so the field renders completely blank — indistinguishable from an unset
 * parent, while the YAML holds a requirement id. The next full-form save then
 * fails with "Parent component not found: <id>" against a box that appears
 * empty, which is the confusing symptom this pins.
 *
 * The bad value is injected over the wire because the API now refuses to store
 * one — which is the point of the guard, and means the only way to reach this
 * state is data written before it existed.
 */
test('a parent that is not a component is reported, not rendered blank', async ({ app, server }) => {
  await signIn(app);

  const reqIds = await listIds(app, 'requirements');
  const orphanParent = reqIds[0];

  await app.route(`**/api/projects/${P}/components/FUSE01`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({
      response: res,
      body: JSON.stringify({ ...body, parent: orphanParent }),
    });
  });

  await app.goto(`${server.baseURL}/project/${P}/components/FUSE01`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  const select = parentSelect(app);
  await expect(select).toBeVisible({ timeout: 15_000 });

  // The select resolves to the offending value rather than falling blank.
  await expect(select).toHaveValue(orphanParent);
  await expect(select.locator(`option[value="${orphanParent}"]`))
    .toContainText('not a component');

  // And it says so in prose, so the user has something to report.
  await expect(app.getByText(/is not a component/i).first()).toBeVisible();
});

test('parent options name their component type, so a name cannot read as a requirement group', async ({ app, server }) => {
  // The demo project has a component and a requirement both called "Wing
  // Assembly"; without the type the dropdown is genuinely ambiguous.
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components/FUSE01`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  const select = parentSelect(app);
  await expect(select).toBeVisible({ timeout: 15_000 });

  const labels = await select.locator('option').evaluateAll((opts) =>
    opts.map((o) => o.textContent || '').filter((t) => !t.includes('top level')));

  expect(labels.length).toBeGreaterThan(0);
  for (const label of labels) {
    expect(label, `option "${label}" names its component type`).toMatch(/\((system|subsystem|assembly|part|software|interface)\)$/);
  }
});
