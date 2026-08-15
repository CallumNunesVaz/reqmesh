import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * FMECA: a risk carries failure mode, effect and cause as three separate rich
 * fields. Create one through the form, see all three on the card, and find it
 * by searching for text that lives only in `cause`.
 */
const P = DEMO_PROJECT;
const RISK_ID = 'RSK-FMECA';
const FAILURE_MODE = 'Aileron control rod snaps';
const EFFECT = 'Loss of roll authority in the turn';
const CAUSE_ONLY = 'hydrogen-embrittlement-fatigue';

test('create a risk with three FMECA fields and find it by cause', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // Open the create form.
  await app.getByRole('button', { name: 'New Risk' }).click();
  const form = app.locator('form').filter({ has: app.locator('input[placeholder="RSK-001"]') });
  await expect(form).toBeVisible({ timeout: 10_000 });

  // ID and title.
  await form.locator('input[placeholder="RSK-001"]').fill(RISK_ID);
  await form.locator('input[placeholder="Risk title"]').fill('FMECA e2e risk');

  // Three rich-text editors in FMECA order: failure mode, effect, cause.
  const editors = form.locator('.ProseMirror');
  await editors.nth(0).click();
  await app.keyboard.type(FAILURE_MODE);
  await editors.nth(1).click();
  await app.keyboard.type(EFFECT);
  await editors.nth(2).click();
  await app.keyboard.type(CAUSE_ONLY);

  await form.getByRole('button', { name: 'Create' }).click();
  await expect(form).not.toBeVisible({ timeout: 10_000 });

  // All three fields render on the card.
  const card = app.locator('.card').filter({ hasText: RISK_ID }).first();
  await expect(card).toBeVisible({ timeout: 10_000 });
  await expect(card).toContainText(FAILURE_MODE);
  await expect(card).toContainText(EFFECT);
  await expect(card).toContainText(CAUSE_ONLY);

  // Search for text that appears only in `cause` — the register's own filter,
  // not the project-wide search — must still surface the risk.
  const search = app.locator('input[placeholder="Search risks…"]');
  await search.fill(CAUSE_ONLY);
  await expect(card).toBeVisible({ timeout: 10_000 });
  // And a query for the failure mode also matches, so the three fields share
  // one haystack rather than hiding behind each other.
  await search.fill(FAILURE_MODE);
  await expect(card).toBeVisible({ timeout: 10_000 });
});
