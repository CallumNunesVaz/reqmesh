import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Parametrics editing and the inline reference helper.
 *
 *  1. Editing an existing parameter's value and unit round-trips through the
 *     save path and survives a reload.
 *  2. The inline helper offers a cross-requirement reference while typing a
 *     constraint expression, and the saved constraint evaluates to a verdict
 *     rather than an error.
 */

const P = DEMO_PROJECT;
const REQ = 'ACFT0000';

test.describe('parameter editing', () => {
  test('editing a parameter value and unit persists across reload', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
    await app.waitForSelector('main', { timeout: 20_000 });
    await setEditMode(app, true);

    // `mtow` is a literal parameter in the demo seed (1157 kg).
    const row = app.locator('[data-param="mtow"]');
    await expect(row).toBeVisible();
    await row.hover();
    await row.getByTitle('Edit parameter').click();

    const editRow = app.locator('[data-param-edit="mtow"]');
    await editRow.locator('input[placeholder="value"]').fill('1200');
    await editRow.locator('input[placeholder="unit"]').fill('lb');
    await editRow.getByTitle('Save parameter').click();

    // The edit is staged until "Save changes" commits it to the backend.
    await app.getByTitle('Save changes').click();
    await expect(app.getByText('Saved')).toBeVisible({ timeout: 10_000 });

    // Reload and confirm the value and unit persisted.
    await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
    await app.waitForSelector('main', { timeout: 20_000 });
    const persisted = app.locator('[data-param="mtow"]');
    await expect(persisted).toBeVisible({ timeout: 10_000 });
    await expect(persisted).toContainText('1200');
    await expect(persisted).toContainText('lb');
  });
});

test.describe('inline reference helper', () => {
  test('inserts a cross-requirement reference and the constraint evaluates', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
    await app.waitForSelector('main', { timeout: 20_000 });
    await setEditMode(app, true);

    // Type a fragment that should surface another requirement's parameter.
    const expr = app.getByPlaceholder(/expr: gross/);
    await expr.fill('empty');

    const option = app.locator('[role="option"]', { hasText: 'AFRM0000.empty_mass' }).first();
    await expect(option).toBeVisible({ timeout: 5000 });
    await option.click();

    // The helper inserted the qualified reference at the caret.
    await expect(expr).toHaveValue('AFRM0000.empty_mass');

    // Complete the expression and submit.
    await expr.fill('AFRM0000.empty_mass >= 0');
    await expr.press('Enter');

    await app.getByTitle('Save changes').click();
    await expect(app.getByText('Saved')).toBeVisible({ timeout: 10_000 });

    // The saved constraint renders a verdict (pass), not an error.
    const constraint = app.getByText('AFRM0000.empty_mass >= 0', { exact: true });
    await expect(constraint).toBeVisible({ timeout: 10_000 });
    const row = constraint.locator('xpath=../..');
    await expect(row).toContainText('pass');
    await expect(row).not.toContainText('error');
  });
});
