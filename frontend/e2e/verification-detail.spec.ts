import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * The verification detail page.
 *
 * Verification cases moved from inline-expanded cards to a dense list plus a
 * routed detail page. This pins the migration: the row navigates, the detail
 * page shows the case's name, a field edited here lands on the server, and the
 * back link returns to the list.
 */

test('open a verification case from the list, edit its name, and return to the list', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/verification`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // The row navigates to the detail page.
  await app.locator('#entity-VCAF0001').click();
  await app.waitForSelector('main');

  // The detail page shows the case's name.
  const nameInput = app.getByLabel('Name');
  await expect(nameInput).toBeVisible({ timeout: 10_000 });
  await expect(nameInput).toHaveValue('Structural Static Test');

  // Edit the name and save on blur.
  const MARKER = 'Structural Static Test (revised)';
  await nameInput.fill(MARKER);
  await nameInput.blur();

  // Wait for the write to land rather than racing the navigation.
  await expect(async () => {
    const vc = await api<any>(app, `/projects/${P}/verification/VCAF0001`);
    expect(vc.name).toBe(MARKER);
  }).toPass({ timeout: 10_000 });

  // The back link returns to the list.
  await app.getByRole('button', { name: 'Back to verification cases' }).click();
  await app.waitForSelector('main');
  await expect(app).toHaveURL(/\/verification$/);
  await expect(app.locator('#entity-VCAF0001')).toBeVisible({ timeout: 10_000 });
});

test('an old-style ?focus= URL still lands on that case in the list', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/verification?focus=VCAF0001`);
  await app.waitForSelector('main');

  const row = app.locator('#entity-VCAF0001');
  await expect(row).toBeVisible({ timeout: 10_000 });
  await expect(row).toHaveClass(/ring/);
});
