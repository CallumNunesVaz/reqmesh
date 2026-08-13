import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The no-autofocus sweep removed `autoFocus` from the inline create/edit forms
 * that sit in the page (not in a modal). A modal traps focus and must move it
 * somewhere; an inline form does not, so autofocus there yanked focus from
 * wherever the user was. Each assertion pins that the reveal no longer steals
 * focus: the field stays unfocused, leaving focus on the trigger the user
 * clicked.
 *
 * The modal dialogs that *do* focus their primary field keep their `autoFocus`
 * (see the `oxlint-disable` comments at those sites); they are covered by
 * modal-focus-trap.spec.ts rather than here.
 */
const P = DEMO_PROJECT;

async function openProjectPage(app: any, server: any, path: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}${path}`);
  await app.waitForSelector('main');
  await setEditMode(app);
}

test('change request form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/change-requests');
  await app.getByRole('button', { name: 'New Change Request' }).click();
  await expect(app.getByPlaceholder('CR-001')).not.toBeFocused();
});

test('component form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/components');
  await app.getByRole('button', { name: 'New Component' }).click();
  await expect(app.getByPlaceholder('C-001')).not.toBeFocused();
});

test('decision form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/decisions');
  await app.getByRole('button', { name: 'New Decision' }).click();
  await expect(app.getByPlaceholder('ADR-001')).not.toBeFocused();
});

test('project form does not steal focus onto its id', async ({ app, server }) => {
  await signIn(app);
  await app.goto(server.baseURL);
  await app.waitForSelector('main');
  await app.getByRole('button', { name: 'New Project' }).first().click();
  await expect(app.getByPlaceholder('my-aircraft-system')).not.toBeFocused();
});

test('risk form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/risks');
  await app.getByRole('button', { name: 'New Risk' }).click();
  await expect(app.getByPlaceholder('RSK-001')).not.toBeFocused();
});

test('specification form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/specifications');
  await app.getByRole('button', { name: 'New Specification' }).click();
  await expect(app.getByPlaceholder('SRS-001')).not.toBeFocused();
});

test('analysis case form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/analysis');
  await app.getByRole('button', { name: 'New Analysis Case' }).click();
  await expect(app.getByPlaceholder('heavy-config')).not.toBeFocused();
});

test('definition form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/definitions');
  await app.getByRole('button', { name: 'New Definition' }).click();
  await expect(app.getByPlaceholder('MassBudget')).not.toBeFocused();
});

test('verification case form does not steal focus onto its id', async ({ app, server }) => {
  await openProjectPage(app, server, '/verification');
  await app.getByRole('button', { name: 'New Verification Case' }).click();
  await expect(app.getByPlaceholder('VC-001')).not.toBeFocused();
});

test('profile edit and new-user forms do not steal focus', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/users`);
  await app.waitForSelector('main');

  // Self profile edit.
  await app.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(app.getByPlaceholder('Your name')).not.toBeFocused();

  // New user create form.
  await app.getByRole('button', { name: 'New User' }).click();
  await expect(app.getByPlaceholder('jdoe')).not.toBeFocused();
});

test('in-place name edit does not steal focus', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/users`);
  await app.waitForSelector('main');

  await app.locator('[title="Edit name & email"]').first().click();
  await expect(app.locator('tbody input.input').first()).not.toBeFocused();
});

test('the invite result link is not auto-focused', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/users`);
  await app.waitForSelector('main');

  await app.getByRole('button', { name: 'Invite', exact: true }).click();
  const dialog = app.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder('jdoe').fill('autofocus-invitee');
  await dialog.getByRole('button', { name: 'Send invite' }).click();

  const linkInput = dialog.locator('input[readonly]');
  await expect(linkInput).toBeVisible({ timeout: 10_000 });
  await expect(linkInput).not.toBeFocused();
});
