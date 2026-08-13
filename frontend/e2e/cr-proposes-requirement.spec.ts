import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';
import type { Page } from '@playwright/test';

const P = DEMO_PROJECT;

let seq = 0;
/** Unique per test — the fixture restores the seeded projects between tests, so
 *  only a collision *inside* one test would be indistinguishable from a stale
 *  write. */
function ids() {
  seq += 1;
  return { crId: `CR-UINEW-${seq}`, reqId: `UINEW-${seq}` };
}

/** Open the CR create form and fill the shared scaffolding (CR id + title). */
async function openCreateForm(app: Page, crId: string) {
  await app.getByRole('button', { name: 'New Change Request' }).click();
  await app.getByPlaceholder('CR-001').fill(crId);
  await app.getByPlaceholder('Change request title').fill('Propose a new requirement');
}

test('author a CR that proposes a new requirement and execute it', async ({ app, server }) => {
  const { crId, reqId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await openCreateForm(app, crId);
  await app.getByPlaceholder('REQ0001').fill(reqId);
  await app.getByPlaceholder('Proposed requirement name').fill('Proposed by CR');
  await app.getByPlaceholder('What the requirement says').fill('Raised in the change request');
  await app.getByRole('button', { name: 'Create', exact: true }).click();

  // The form closes and the list reloads with the new CR.
  const row = app.locator('.group', { hasText: crId }).first();
  await expect(row).toBeVisible();
  await row.hover();
  await row.locator('[title="Execute"]').click();

  // The gate names the creation, so this is a creation not an edit.
  await expect(app.getByText(new RegExp(`creates 1 new requirement: ${reqId}`))).toBeVisible();
  await app.getByRole('button', { name: 'Confirm' }).click();

  // Executing lands on the new requirement, the same place a hand-created one
  // would leave you.
  await expect(app).toHaveURL(new RegExp(`/project/${P}/requirements/${reqId}$`), { timeout: 15_000 });

  // Ground truth, not the DOM: it really exists, with the fields that were
  // entered in the form.
  const created = await api(app, `/projects/${P}/requirements/${reqId}`);
  expect(created.id).toBe(reqId);
  expect(created.name).toBe('Proposed by CR');
  expect(created.description).toBe('Raised in the change request');

  // Same defaults as a hand-created requirement.
  expect(created.type).toBe('functional');
  expect(created.priority).toBe('medium');
  expect(created.status).toBe('proposed');
});

test('a proposed id that already exists is refused at authoring time', async ({ app, server }) => {
  const { crId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await openCreateForm(app, crId);
  await app.getByPlaceholder('REQ0001').fill('AFRM0001');
  await app.getByPlaceholder('Proposed requirement name').fill('Collision');
  await app.getByRole('button', { name: 'Create', exact: true }).click();

  await expect(app.getByText("Proposed requirement 'AFRM0001' already exists")).toBeVisible();

  // Nothing was written: the request was refused, not created.
  const crs = await api(app, `/projects/${P}/change-requests`);
  expect(crs.items.some((c: { id: string }) => c.id === crId)).toBe(false);
});

test('a proposed id that violates the naming scheme is refused at authoring time', async ({ app, server }) => {
  const { crId } = ids();
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/change-requests`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await openCreateForm(app, crId);
  await app.getByPlaceholder('REQ0001').fill('NEWREQ-NOPE');
  await app.getByPlaceholder('Proposed requirement name').fill('Bad scheme');
  await app.getByRole('button', { name: 'Create', exact: true }).click();

  await expect(app.getByText("Proposed requirement 'NEWREQ-NOPE' must end in a number")).toBeVisible();

  const crs = await api(app, `/projects/${P}/change-requests`);
  expect(crs.items.some((c: { id: string }) => c.id === crId)).toBe(false);
});
