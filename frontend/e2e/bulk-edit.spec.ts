import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Bulk edit is the deliverable, not a bonus: selecting rows and setting fields
 * must actually change those rows — and a change the server refuses must be
 * shown, not swallowed.
 *
 * The two fields exercised here are the ones that used to be free text: system
 * states (typed as a comma list, so a typo produced a state nobody could find)
 * and stakeholder priorities (typed as `name: score`, so `safety: 10` — which
 * the modal's own placeholder suggested — 422ed the whole batch).
 */

/** Sign in, land on the requirements list, and turn edit mode on. */
async function openRequirements(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`, { waitUntil: 'commit' });
  await setEditMode(app);
}

/** Tick a row's checkbox. */
async function check(app: any, id: string) {
  await app.locator(`#entity-${id} svg.lucide-square`).first().click();
}

/** Open the bulk-edit modal. */
async function openBulkEdit(app: any) {
  await app.getByRole('button', { name: 'Bulk Edit' }).click();
  await expect(app.getByRole('dialog').filter({ hasText: 'Bulk Edit Requirements' })).toBeVisible();
}

test('bulk editing system states and a stakeholder score applies to every selected requirement', async ({ app, server }) => {
  await openRequirements(app, server);

  await check(app, 'AFRM0001');
  await check(app, 'AFRM0004');
  await expect(app.getByText('2 selected')).toBeVisible();

  await openBulkEdit(app);
  const dialog = app.getByRole('dialog').filter({ hasText: 'Bulk Edit Requirements' });

  // System states are toggle buttons now, not a comma-separated input.
  await dialog.getByRole('button', { name: 'Cruise', exact: true }).click();
  await dialog.getByRole('button', { name: 'Landing', exact: true }).click();

  // Stakeholder priorities are one 0–5 control per defined stakeholder.
  await dialog.locator('select[aria-label="safety priority"]').selectOption('5');

  await dialog.getByRole('button', { name: 'Update 2 requirement(s)' }).click();
  await expect(dialog).toBeHidden();

  // Reload and confirm the values landed on *both* requirements.
  await app.reload();
  await app.waitForSelector('#entity-AFRM0001', { timeout: 20_000 });

  for (const id of ['AFRM0001', 'AFRM0004']) {
    const r = await api(app, `/projects/${P}/requirements/${id}`);
    expect(r.system_states, `${id} system_states`).toEqual(['Cruise', 'Landing']);
    expect(r.priorities?.safety, `${id} priorities.safety`).toBe(5);
  }
});

test('a bulk edit the server rejects shows a readable message and keeps the modal open', async ({ app, server }) => {
  await openRequirements(app, server);

  // ACFT0000 is seeded "verified"; the demo workflow only lets it go to
  // "deprecated", so "approved" is a transition the server refuses.
  await check(app, 'ACFT0000');
  await expect(app.getByText('1 selected')).toBeVisible();

  await openBulkEdit(app);
  const dialog = app.getByRole('dialog').filter({ hasText: 'Bulk Edit Requirements' });

  await dialog.getByRole('combobox', { name: 'Status' }).selectOption('approved');
  await dialog.getByRole('button', { name: 'Update 1 requirement(s)' }).click();

  // The 409 message is a plain string; it must render as text, not "[object Object]".
  await expect(
    dialog.getByText(/Transition from 'verified' to 'approved' is not allowed/),
  ).toBeVisible({ timeout: 10_000 });

  // The modal stays open so the user can fix the edit.
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Update 1 requirement(s)' })).toBeVisible();
});
