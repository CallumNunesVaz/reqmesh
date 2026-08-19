import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Live quality feedback and dirty-on-keystroke.
 *
 * The save control must appear on the first keystroke — not on blur — for both
 * the rich-text description and a plain input, and the Quality card must sit
 * directly beneath the Description card.
 */

const P = DEMO_PROJECT;
const REQ = 'ELEC0000';

async function openRequirement(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await expect(app.getByRole('heading', { name: REQ, exact: true })).toBeVisible({ timeout: 20_000 });
}

test('typing one character into the description shows the save control immediately', async ({ app, server }) => {
  await openRequirement(app, server);
  await setEditMode(app, true);

  const descCard = app.locator('.card').filter({ has: app.locator('label', { hasText: 'Description' }) }).first();
  const editor = descCard.locator('.ProseMirror').first();
  await editor.click();
  await app.keyboard.type('x');

  // The save control appears without leaving the field (no blur).
  await expect(app.getByRole('button', { name: 'Save changes' })).toBeVisible({ timeout: 10_000 });
  await expect(app.getByRole('button', { name: 'Discard changes' })).toBeVisible();
});

test('typing one character into a plain input shows the save control immediately', async ({ app, server }) => {
  await openRequirement(app, server);
  await setEditMode(app, true);

  const name = app.getByLabel('Name');
  await name.click();
  await name.press('End');
  await name.type('x');

  await expect(app.getByRole('button', { name: 'Save changes' })).toBeVisible({ timeout: 10_000 });
});

test('the Quality card renders directly after the Description card', async ({ app, server }) => {
  await openRequirement(app, server);

  const descCard = app.locator('.card').filter({ has: app.locator('label', { hasText: 'Description' }) }).first();
  const qualityCard = app.locator('.card').filter({ has: app.getByRole('heading', { name: 'Quality', exact: true }) }).first();

  await expect(descCard).toBeVisible({ timeout: 10_000 });
  await expect(qualityCard).toBeVisible({ timeout: 10_000 });

  // The Quality card is the element immediately following the Description card.
  await expect(descCard.locator('xpath=following-sibling::*[1]')).toContainText('Quality');
});
