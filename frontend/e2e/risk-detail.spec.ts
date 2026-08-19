import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

/**
 * The risk detail page and the group filters.
 *
 * Risks moved from inline-edited cards to a dense list plus a routed detail
 * page. These pin the behaviours that migration has to preserve: editing on
 * the detail page is visible back on the list, links written here agree with
 * the other side (the requirement's own page), the group filters match a whole
 * subtree rather than a node, and the old `?focus=` deep link still resolves.
 */

test('open a risk from the list, edit its failure mode, see the change back on the list', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // The row navigates to the detail page.
  await app.locator('#entity-RSK00001').click();
  await app.waitForSelector('main');
  await expect(app.locator('.ProseMirror').first()).toBeVisible({ timeout: 10_000 });

  const MARKER = 'tail-rotor-shaft-wear-marker';
  const editor = app.locator('.ProseMirror').first();
  await editor.click();
  await app.keyboard.press('Control+a');
  await app.keyboard.type(MARKER);

  // Save on blur.
  await app.getByLabel('Title').click();

  // Wait for the write to land rather than racing the navigation.
  await expect(async () => {
    const risk = await api<any>(app, `/projects/${P}/risks/RSK00001`);
    expect(risk.failure_mode).toContain(MARKER);
  }).toPass({ timeout: 10_000 });

  // Back on the list the change is discoverable through search (which spans
  // failure_mode), since the dense row itself does not render the FMECA prose.
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  await app.locator('input[placeholder="Search risks…"]').fill(MARKER);
  await expect(app.locator('#entity-RSK00001')).toBeVisible({ timeout: 10_000 });
});

test('a requirement linked from the risk detail page appears on that requirement page', async ({ app, server }) => {
  await signIn(app);

  const risk = await api<any>(app, `/projects/${P}/risks/RSK00001`);
  const reqsPage = await api<any>(app, `/projects/${P}/requirements`);
  const requirements = reqsPage.items ?? reqsPage;
  const req = requirements.find((r: any) => !risk.linked_requirements.includes(r.id));
  expect(req).toBeTruthy();

  await app.goto(`${server.baseURL}/project/${P}/risks/RSK00001`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  await app.locator('[data-link-editor="Threatens"] select').selectOption(`${req.id} — ${req.name}`);

  await expect(async () => {
    const updated = await api<any>(app, `/projects/${P}/risks/RSK00001`);
    expect(updated.linked_requirements).toContain(req.id);
  }).toPass({ timeout: 10_000 });

  // The requirement's own page lists this risk under "Threatened by".
  await app.goto(`${server.baseURL}/project/${P}/requirements/${encodeURIComponent(req.id)}`);
  await app.waitForSelector('main');
  await expect(app.locator('main').getByText('RSK00001', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
});

test('filtering by a component group includes risks linked only to its children', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');

  // WING01 has children (SPAR01, ASPAR01, TANK01, STRT01) and TANK01 a child
  // (FQSND01). RSK00002 is linked to TANK01 and FQSND01 — descendants of
  // WING01 — but not to WING01 itself, so a node-only match would exclude it.
  await app.locator('[data-group-picker="Component group"]').getByRole('button').first().click();
  await app.locator('[data-group-picker="Component group"] input').fill('WING01');
  await app.locator('[data-group-picker="Component group"]').getByRole('button', { name: /WING01/ }).click();

  await expect(app.locator('#entity-RSK00002')).toBeVisible({ timeout: 10_000 });
  // A risk that touches none of WING01's subtree (RSK00001 links ENG01) is gone.
  await expect(app.locator('#entity-RSK00001')).toHaveCount(0);
});

test('an old-style ?focus= URL still resolves to that risk', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks?focus=RSK00001`);
  await app.waitForSelector('main');

  // The list keeps the focus behaviour: the row is present and ringed.
  const row = app.locator('#entity-RSK00001');
  await expect(row).toBeVisible({ timeout: 10_000 });
  await expect(row).toHaveClass(/ring/);
});
