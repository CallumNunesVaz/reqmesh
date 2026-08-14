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
  await app.goto(`${server.baseURL}/project/${P}/components/FUSE`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  const compIds = new Set(await listIds(app, 'components'));
  const reqIds = new Set(await listIds(app, 'requirements'));
  // FUSE has both a parent and children, so the picker is populated and the
  // self/descendant exclusion is actually exercised.
  const own = await branch(app, 'FUSE');

  const select = parentSelect(app);
  await expect(select).toBeVisible({ timeout: 15_000 });
  const options = (await optionValues(select)).filter((v) => v !== '');

  expect(options.length, 'FUSE has eligible parents other than its own branch').toBeGreaterThan(0);

  for (const value of options) {
    expect(compIds.has(value), `parent option ${value} is a component id`).toBe(true);
    expect(reqIds.has(value), `parent option ${value} is not a requirement id`).toBe(false);
    expect(own.has(value), `parent option ${value} is not FUSE or one of its descendants`).toBe(false);
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
