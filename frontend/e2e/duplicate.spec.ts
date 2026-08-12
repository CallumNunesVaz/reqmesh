import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

async function getJson(app: any, path: string) {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api${p}`, { credentials: 'include' });
    return r.ok ? await r.json() : null;
  }, path);
}

test('duplicate a component: copy exists with a fresh id and carries no links', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/components`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const before = await getJson(app, `/projects/${P}/components/C172`);
  expect(before).not.toBeNull();
  expect(before.satisfies).not.toEqual([]);

  await app.locator('#entity-C172 [title="Duplicate component"]').click();

  await expect(app.getByText('Component C172-copy created')).toBeVisible({ timeout: 15000 });

  const copy = await getJson(app, `/projects/${P}/components/C172-copy`);
  expect(copy).not.toBeNull();
  expect(copy.id).toBe('C172-copy');
  expect(copy.satisfies).toEqual([]);
  expect(copy.verification_cases).toEqual([]);
  expect(copy.baselines).toEqual([]);

  // Original unchanged.
  const after = await getJson(app, `/projects/${P}/components/C172`);
  expect(after.satisfies).toEqual(before.satisfies);
});

test('duplicate a specification: copy exists with a fresh id and the original is unchanged', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/specifications`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const before = await getJson(app, `/projects/${P}/specifications/SPEC-SYS`);
  expect(before).not.toBeNull();
  expect(before.requirements).not.toEqual([]);

  await app.locator('#entity-SPEC-SYS [title="Duplicate specification"]').click();

  await expect(app.getByText('Specification SPEC-SYS-copy created')).toBeVisible({ timeout: 15000 });

  const copy = await getJson(app, `/projects/${P}/specifications/SPEC-SYS-copy`);
  expect(copy).not.toBeNull();
  expect(copy.id).toBe('SPEC-SYS-copy');
  expect(copy.requirements).toEqual([]);
  expect(copy.components ?? []).toEqual([]);

  const after = await getJson(app, `/projects/${P}/specifications/SPEC-SYS`);
  expect(after.requirements).toEqual(before.requirements);
});
