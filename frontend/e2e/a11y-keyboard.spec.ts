import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * The second tooth of the a11y ratchet: elements that used to be click-only
 * must now answer to the keyboard. These drive four converted controls across
 * four pages and assert the *behaviour* — navigation, expansion — that makes
 * them worth being a real control, not merely that they are one.
 *
 * The requirement row answers Enter through its own key handler; the card
 * headers are native buttons driven by Space. (Enter on a list-page button is
 * consumed by the global j/k/Enter list-navigation shortcut, a pre-existing
 * behaviour this task does not touch.)
 */
const P = DEMO_PROJECT;

test('requirement row opens its detail page on Enter', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');

  const row = app.getByRole('treeitem').first();
  await expect(row).toBeVisible();
  await row.focus();
  await app.keyboard.press('Enter');

  await expect(app).toHaveURL(/\/requirements\/[A-Z0-9]+$/);
});

test('analysis case header expands on Space', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/analysis`);
  await app.waitForSelector('main');

  const header = app.locator('main').getByRole('button', { name: /Avionics upgrade/ }).first();
  await expect(header).toBeVisible();
  await header.focus();
  await app.keyboard.press('Space');

  await expect(header).toHaveAttribute('aria-expanded', 'true');
  await expect(app.getByText('Explore the empty-weight budget with a heavier avionics fit.')).toBeVisible();
});

test('verification row opens its detail page on Space', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/verification`);
  await app.waitForSelector('main');

  const row = app.locator('main').getByRole('button', { name: 'Structural Static Test', exact: true });
  await expect(row).toBeVisible();
  await row.focus();
  await app.keyboard.press('Space');

  await expect(app).toHaveURL(/\/verification\/VCAF0001$/);
});

test('decision header expands on Space', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/decisions`);
  await app.waitForSelector('main');

  const header = app.locator('main').getByRole('button', { name: /Avionics Platform Selection/ }).first();
  await expect(header).toBeVisible();
  await header.focus();
  await app.keyboard.press('Space');

  await expect(header).toHaveAttribute('aria-expanded', 'true');
  await expect(app.getByRole('heading', { name: 'Context' }).first()).toBeVisible();
});
