import { test, expect, signIn, DEMO_PROJECT } from './fixtures';
import { REQUIREMENT_TYPES, REQUIREMENT_TYPE_META } from '../src/lib/requirementTypes';

/**
 * Every type dropdown offers the same set.
 *
 * The allocation matrix used to hand-write five options and label
 * `non_functional_performance` as plain "Non-Functional", so filtering there
 * silently excluded the other seven non-functional variants. These pages each
 * kept their own copy of the list; the point of the assertion is that they no
 * longer can.
 */
const P = DEMO_PROJECT;
const EXPECTED = REQUIREMENT_TYPES.map((t) => REQUIREMENT_TYPE_META[t].label);

async function typeOptions(page: import('@playwright/test').Page, selectLocator: any) {
  return (await selectLocator.locator('option').allTextContents())
    .map((t: string) => t.trim())
    // "All types" is the filter's empty option; an "(unrecognised)" entry is a
    // stored value the enum no longer has, kept so a save cannot drop it.
    .filter((t: string) => !/^all types$/i.test(t) && !t.includes('unrecognised'));
}

test('the allocation matrix filter offers every requirement type', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  const select = app.locator('main select').filter({ has: app.locator('option[value=""]') }).first();
  await expect(select).toBeVisible({ timeout: 20_000 });
  expect(await typeOptions(app, select)).toEqual(EXPECTED);
});

test('the requirements list filter offers the same set, in the same order', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  const select = app.locator('select').filter({ has: app.locator('option[value="functional"]') }).first();
  await expect(select).toBeVisible({ timeout: 20_000 });
  expect(await typeOptions(app, select)).toEqual(EXPECTED);
});

test('the requirement detail editor offers the same set', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main');
  const select = app.locator('select').filter({ has: app.locator('option[value="functional"]') }).first();
  await expect(select).toBeVisible({ timeout: 20_000 });
  expect(await typeOptions(app, select)).toEqual(EXPECTED);
});
