import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * FMECA: a risk carries failure mode, effect and cause as three separate rich
 * fields. Create one through the form, see all three on its detail page, and
 * find it on the list by searching for text that lives only in `cause`.
 */
const P = DEMO_PROJECT;
// Conforms to the project's naming standard for risks (RSK + numeric
// suffix). Enforcement is on by default, so a readable-but-wrong-shaped id
// like 'RSK-FMECA' is now refused at create.
const RISK_ID = 'RSK99001';
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

  // The list now renders one dense row per risk; the FMECA fields live on the
  // detail page, so open it from the row to see all three.
  await app.locator(`#entity-${RISK_ID}`).click();
  await app.waitForSelector('main');
  await expect(app.locator('main')).toContainText(FAILURE_MODE, { timeout: 10_000 });
  await expect(app.locator('main')).toContainText(EFFECT);
  await expect(app.locator('main')).toContainText(CAUSE_ONLY);

  // Back to the list: search for text that appears only in `cause` — the
  // register's own filter, not the project-wide search — must still surface it.
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  const search = app.locator('input[placeholder="Search risks…"]');
  await search.fill(CAUSE_ONLY);
  await expect(app.locator(`#entity-${RISK_ID}`)).toBeVisible({ timeout: 10_000 });
  // And a query for the failure mode also matches, so the three fields share
  // one haystack rather than hiding behind each other.
  await search.fill(FAILURE_MODE);
  await expect(app.locator(`#entity-${RISK_ID}`)).toBeVisible({ timeout: 10_000 });
});
