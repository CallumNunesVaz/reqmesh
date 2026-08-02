import { test, expect, signIn, setEditMode, DEMO_PROJECT, type Server } from './fixtures';
import type { Page } from '@playwright/test';

const P = DEMO_PROJECT;

/**
 * Create a specification with the given id and URL, and return its card.
 *
 * Each test builds its own: the seeded project is restored before every test,
 * so a spec created by one is gone by the time the next runs. These used to
 * share one via `describe.serial`, which is the coupling that made the suite's
 * failures depend on execution order.
 */
async function createSpec(app: Page, server: Server, id: string, url: string) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/specifications`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  await app.getByRole('button', { name: 'New Specification' }).click();
  const form = app.locator('form').filter({ has: app.locator('input[placeholder="SRS-001"]') });
  await expect(form).toBeVisible({ timeout: 10_000 });

  await form.locator('input[placeholder="SRS-001"]').fill(id);
  await form.locator('input[placeholder="Specification name"]').fill(`${id} fixture`);
  await form.locator('input[placeholder="https://…"]').fill(url);
  await form.getByRole('button', { name: 'Create' }).click();

  const card = app.locator('.card').filter({ hasText: id }).first();
  await expect(card).toBeVisible({ timeout: 10_000 });
  return card;
}

test('a safe URL renders a Source link with the right rel and target', async ({ app, server }) => {
  const card = await createSpec(app, server, 'SRS-E2E-OK', 'https://example.com/spec.pdf');

  const link = card.locator('a[href="https://example.com/spec.pdf"]');
  await expect(link).toBeVisible({ timeout: 5000 });
  // Without noopener the opened page gets a handle on window.opener.
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(link).toHaveAttribute('target', '_blank');
  await expect(link).toHaveText('Source');
});

test('a javascript: URL renders no anchor at all', async ({ app, server }) => {
  // Set at creation rather than by editing a spec another test made: the
  // invariant is "an unsafe URL never reaches an href", and how it got stored
  // is irrelevant to it.
  const card = await createSpec(app, server, 'SRS-E2E-XSS', 'javascript:alert(1)');
  await expect(card.locator('a[href]')).toHaveCount(0, { timeout: 5000 });
});

test('editing a safe URL to a javascript: one removes the link', async ({ app, server }) => {
  const card = await createSpec(app, server, 'SRS-E2E-EDIT', 'https://example.com/ok.pdf');
  await expect(card.locator('a[href]')).toHaveCount(1, { timeout: 5000 });

  await card.hover();
  await card.locator('button[title="Edit"]').click();
  const form = app.locator('form').filter({ has: app.locator('input[placeholder="SRS-001"]') });
  await expect(form).toBeVisible({ timeout: 10_000 });

  await form.locator('input[placeholder="https://…"]').fill('javascript:alert(1)');
  await form.getByRole('button', { name: 'Save' }).click();

  await expect(card.locator('a[href]')).toHaveCount(0, { timeout: 5000 });
});
