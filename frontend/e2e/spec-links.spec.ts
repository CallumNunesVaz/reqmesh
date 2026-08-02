import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test.describe.serial('specification links', () => {
  test('creating a spec with a URL shows a Source link with the right href and rel', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/specifications`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    // Open the create form
    await app.getByRole('button', { name: 'New Specification' }).click();
    const form = app.locator('form').filter({ has: app.locator('input[placeholder="SRS-001"]') });
    await expect(form).toBeVisible({ timeout: 10_000 });
    await app.waitForTimeout(500);

    // Fill in the form
    await form.locator('input[placeholder="SRS-001"]').fill('SRS-E2E');
    await form.locator('input[placeholder="Specification name"]').fill('E2E Test Spec');
    await form.locator('input[placeholder="https://…"]').fill('https://example.com/spec.pdf');

    // Submit
    await form.getByRole('button', { name: 'Create' }).click();
    await app.waitForTimeout(1000);

    // The new spec should appear in the list
    const card = app.locator('.card').filter({ hasText: 'SRS-E2E' }).first();
    await expect(card).toBeVisible({ timeout: 10_000 });

    // The Source link should be present
    const link = card.locator('a[href="https://example.com/spec.pdf"]');
    await expect(link).toBeVisible({ timeout: 5000 });
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveText('Source');
  });

  test('editing a spec URL to javascript: makes the link disappear', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/specifications`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    // Find the card from the previous test and hover to reveal the edit button
    const card = app.locator('.card').filter({ hasText: 'SRS-E2E' }).first();
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Hover to show the edit button, then click it
    await card.hover();
    await card.locator('button[title="Edit"]').click();
    await app.waitForTimeout(500);

    // The form should be open in edit mode
    const form = app.locator('form').filter({ has: app.locator('input[placeholder="SRS-001"]') });
    await expect(form).toBeVisible({ timeout: 10_000 });

    // Change the URL to a javascript: value
    const urlInput = form.locator('input[placeholder="https://…"]');
    await urlInput.fill('javascript:alert(1)');

    // Save
    await form.getByRole('button', { name: 'Save' }).click();
    await app.waitForTimeout(1000);

    // No anchor should be rendered for the unsafe URL
    await expect(card.locator('a[href]')).toHaveCount(0, { timeout: 5000 });
  });
});
