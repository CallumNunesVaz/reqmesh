import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';
import type { Page } from '@playwright/test';

const P = DEMO_PROJECT;

/** POST through the browser's session — CR authoring is API-only today, so a
 *  proposal for a *new* requirement cannot be built through the UI.
 *
 *  Writes are CSRF-checked whenever the session cookie is present, so the token
 *  has to be echoed back in a header. The cookie is scoped to path=/api, which
 *  `document.cookie` inside the page cannot see — read it from the context's
 *  jar, as settings-baselines.spec.ts does. */
async function post<T = any>(page: Page, path: string, body: unknown): Promise<T> {
  const cookies = await page.context().cookies();
  const token = cookies.find((c) => c.name === 'csrftoken')?.value || '';
  const res = await page.evaluate(
    async ([p, b, t]) => {
      const r = await fetch(`/api${p}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t as string },
        body: JSON.stringify(b),
      });
      return { status: r.status, body: await r.json() };
    },
    [path, body, token] as const,
  );
  if (res.status >= 400) throw new Error(`POST ${path} → ${res.status}: ${JSON.stringify(res.body)}`);
  return res.body as T;
}

let seq = 0;
/** Unique per test: the fixture restores project data between tests, but a
 *  collision inside one test would be indistinguishable from a stale write. */
function ids() {
  seq += 1;
  return { crId: `CR-NEWREQ-${seq}`, reqId: `NEWREQ-${seq}` };
}

async function raiseCreatingCR(page: Page, crId: string, reqId: string) {
  await post(page, `/projects/${P}/change-requests`, {
    id: crId,
    title: 'Propose a new requirement',
    status: 'submitted',
    changes: { [reqId]: { name: 'Proposed by CR', description: 'Raised in the change request' } },
    creates: [reqId],
    affected_requirements: [reqId],
  });
}

test('the execute gate names the requirements it will create', async ({ app, server }) => {
  const { crId, reqId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');
  await raiseCreatingCR(app, crId, reqId);
  await app.reload();
  await setEditMode(app);

  const row = app.locator('.group', { hasText: crId }).first();
  await row.hover();
  await row.locator('[title="Execute"]').click();

  // The gate is what makes this a creation rather than an edit: it says so, and
  // it names the id, before anything is written.
  await expect(app.getByText(new RegExp(`creates 1 new requirement: ${reqId}`))).toBeVisible();
  await expect(app.getByText('Create & apply')).toBeVisible();

  // Cancelling the gate writes nothing.
  await app.getByRole('button', { name: 'Cancel' }).click();
  const after = await api(app, `/projects/${P}/requirements/${reqId}`);
  expect(after.detail).toBeTruthy();
});

test('confirming creates the requirement and lands on it', async ({ app, server }) => {
  const { crId, reqId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');
  await raiseCreatingCR(app, crId, reqId);
  await app.reload();
  await setEditMode(app);

  const row = app.locator('.group', { hasText: crId }).first();
  await row.hover();
  await row.locator('[title="Execute"]').click();
  await app.getByRole('button', { name: 'Confirm' }).click();

  // The inspector focuses the new requirement — same place a hand-created one
  // would leave you.
  await expect(app).toHaveURL(new RegExp(`/project/${P}/requirements/${reqId}$`), { timeout: 15_000 });

  // Ground truth, not the DOM: it really exists, with the CR's data.
  const created = await api(app, `/projects/${P}/requirements/${reqId}`);
  expect(created.id).toBe(reqId);
  expect(created.name).toBe('Proposed by CR');

  // Same defaults as a hand-created requirement: a bare proposal used to be
  // written straight through, leaving a record the detail page crashed on.
  expect(created.type).toBe('functional');
  expect(created.priority).toBe('medium');
  expect(created.status).toBe('proposed');

  // And the canvas selects it, so the two panes agree on what is in focus.
  const node = app.locator(`.react-flow__node[data-id="${reqId}"]`).first();
  await expect(node).toHaveCount(1, { timeout: 15_000 });
});

test('an edit-only change request does not navigate away', async ({ app, server }) => {
  const { crId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');

  const page = await api(app, `/projects/${P}/requirements`);
  const target = page.items[0];
  const fp = await api(app, `/projects/${P}/requirements/${target.id}/fingerprint`);
  await post(app, `/projects/${P}/change-requests`, {
    id: crId,
    title: 'Edit only',
    status: 'submitted',
    changes: { [target.id]: { name: `${target.name} (edited)` } },
    base_fingerprints: { [target.id]: fp.fingerprint },
    affected_requirements: [target.id],
  });
  await app.reload();
  await setEditMode(app);

  const row = app.locator('.group', { hasText: crId }).first();
  await row.hover();
  await row.locator('[title="Execute"]').click();
  // No creation, so no creation clause and no redirect.
  await expect(app.getByText(/creates \d+ new requirement/)).toHaveCount(0);
  await app.getByRole('button', { name: 'Confirm' }).click();

  await expect(app.locator(`#entity-${crId}`)).toBeVisible();
  await expect(app).toHaveURL(new RegExp('/change-requests$'));
});
