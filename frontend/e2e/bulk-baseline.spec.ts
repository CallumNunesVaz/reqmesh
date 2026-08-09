import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Bulk baseline assignment is additive.
 *
 * The bulk bar used to send `{ baselines: [name] }`, which replaces the list —
 * so selecting rows and picking one baseline silently dropped every other
 * baseline those rows carried, and pushed no undo entry to get them back.
 */
const P = DEMO_PROJECT;
const REQ = 'AFRM0001';

const ADD = 'select[title^="Adds this baseline"]';
const REMOVE = 'select[title^="Removes only"]';

async function csrf(app: any): Promise<string> {
  const cookies = await app.context().cookies();
  return cookies.find((c: any) => c.name === 'csrftoken')?.value || '';
}

/** Project meta takes PATCH, requirements take PUT. If-Match is opt-in, so it
 *  is omitted here. */
async function write(app: any, path: string, body: unknown, method: 'PUT' | 'PATCH') {
  const token = await csrf(app);
  const status = await app.evaluate(async ({ p, b, t, m }: any) => {
    const r = await fetch(p, {
      method: m,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t },
      body: JSON.stringify(b),
    });
    return r.status;
  }, { p: path, b: body, t: token, m: method });
  expect(status, `${method} ${path}`).toBeLessThan(300);
}

async function baselinesOf(app: any): Promise<string[]> {
  return app.evaluate(async ({ project, id }: any) => {
    const r = await fetch(`/api/projects/${project}/requirements/${id}`, { credentials: 'include' });
    return (await r.json()).baselines ?? [];
  }, { project: P, id: REQ });
}

/** Define the baselines in _meta, put `existing` on the requirement, and land
 *  on the requirements page in edit mode with every row selected. */
async function setup(app: any, server: any, defined: string[], existing: string[]) {
  await signIn(app);
  await write(app, `/api/projects/${P}`, { baselines: defined.map((n) => ({ name: n })) }, 'PATCH');
  await write(app, `/api/projects/${P}/requirements/${REQ}`, { baselines: existing }, 'PUT');

  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);
  await app.getByText('Select all').first().click();
  await expect(app.getByText(/\d+ selected/)).toBeVisible();
}

test('adding a baseline in bulk keeps the ones already there', async ({ app, server }) => {
  await setup(app, server, ['SRR', 'PDR', 'CDR'], ['SRR', 'CDR']);

  await app.locator(ADD).selectOption('PDR');
  await expect(app.getByText(/\d+ selected/)).toHaveCount(0, { timeout: 15000 });

  // The regression: SRR and CDR must survive alongside the new PDR.
  expect(new Set(await baselinesOf(app))).toEqual(new Set(['SRR', 'CDR', 'PDR']));
});

test('removing a baseline in bulk takes only that one', async ({ app, server }) => {
  await setup(app, server, ['SRR', 'PDR'], ['SRR', 'PDR']);

  await app.locator(REMOVE).selectOption('PDR');
  await expect(app.getByText(/\d+ selected/)).toHaveCount(0, { timeout: 15000 });

  expect(await baselinesOf(app)).toEqual(['SRR']);
});

test('the bulk baseline change is undoable', async ({ app, server }) => {
  await setup(app, server, ['SRR', 'PDR'], ['SRR']);

  await app.locator(ADD).selectOption('PDR');
  await expect(app.getByText(/\d+ selected/)).toHaveCount(0, { timeout: 15000 });
  expect(new Set(await baselinesOf(app))).toEqual(new Set(['SRR', 'PDR']));

  await app.keyboard.press('Control+z');
  await expect
    .poll(async () => (await baselinesOf(app)).join(','), { timeout: 15000 })
    .toBe('SRR');
});
