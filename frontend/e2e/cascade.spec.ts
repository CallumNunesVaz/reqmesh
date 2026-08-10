import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Cascade, end to end from the detail page.
 *
 * A cascade is not a copy-and-forget: the master's name, description, priority,
 * status and type overwrite every copy on each later edit. The UI has to say so
 * before it happens, and offer a way out — otherwise the only signal a user gets
 * is their text silently changing back.
 */
const P = DEMO_PROJECT;

async function open(app: any, server: any, reqId: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/${reqId}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

/** Wait until the project contains a copy cascaded from `master`. Toasts
 *  auto-dismiss, so polling the real state is both sturdier and closer to what
 *  the test is really asserting. */
async function waitForCopy(app: any, master: string) {
  await expect
    .poll(async () => (await reqs(app)).filter((r: any) => r.cascade_from === master).length,
          { timeout: 20000 })
    .toBeGreaterThan(0);
  return (await reqs(app)).find((r: any) => r.cascade_from === master);
}

async function reqs(app: any) {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    return (await r.json()).items;
  }, P);
}

test('cascading creates copies whose ids follow the project scheme', async ({ app, server }) => {
  // AFRM0000 (Airframe) has several child groups in the demo.
  await open(app, server, 'AFRM0000');

  const before = await reqs(app);
  const cascadeBtn = app.locator('[title^="Cascade a copy into"]');
  await expect(cascadeBtn).toHaveCount(1);
  await cascadeBtn.click();

  // The confirm must state that later edits overwrite the copies.
  await expect(app.getByText(/editing this one will overwrite them/)).toBeVisible();
  await app.getByRole('button', { name: /^(OK|Confirm|Yes)/ }).click();

  await waitForCopy(app, 'AFRM0000');

  const after = await reqs(app);
  const added = after.filter((a: any) => !before.some((b: any) => b.id === a.id));
  expect(added.length).toBeGreaterThan(0);
  for (const a of added) {
    expect(a.cascade_from).toBe('AFRM0000');
    // The old synthetic `{source}-C-{hex}` shape is gone.
    expect(a.id).not.toContain('-C-');
  }
});

test('a cascaded copy says so, and can be detached', async ({ app, server }) => {
  await open(app, server, 'AFRM0000');
  await app.locator('[title^="Cascade a copy into"]').click();
  await app.getByRole('button', { name: /^(OK|Confirm|Yes)/ }).click();
  const copy = await waitForCopy(app, 'AFRM0000');
  expect(copy).toBeTruthy();

  await app.goto(`${server.baseURL}/project/${P}/requirements/${copy.id}`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByText(/Cascaded copy of/)).toBeVisible();
  await expect(app.getByText(/overwrite this one whenever it changes/)).toBeVisible();

  await app.getByRole('button', { name: 'Break cascade' }).click();
  await app.getByRole('button', { name: /^(OK|Confirm|Yes)/ }).click();
  await expect
    .poll(async () => (await reqs(app)).find((r: any) => r.id === copy.id)?.cascade_from ?? null,
          { timeout: 20000 })
    .toBeNull();
});

test('the cascade action is hidden on a requirement that is itself a copy', async ({ app, server }) => {
  await open(app, server, 'AFRM0000');
  await app.locator('[title^="Cascade a copy into"]').click();
  await app.getByRole('button', { name: /^(OK|Confirm|Yes)/ }).click();
  const copy = await waitForCopy(app, 'AFRM0000');
  await app.goto(`${server.baseURL}/project/${P}/requirements/${copy.id}`);
  await app.waitForSelector('main');
  await setEditMode(app);

  // Cascading from a copy would chain masters; the action is not offered.
  await expect(app.locator('[title^="Cascade a copy into"]')).toHaveCount(0);
});

test('no cascade controls in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0000`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  await expect(app.locator('[title^="Cascade a copy into"]')).toHaveCount(0);
});
