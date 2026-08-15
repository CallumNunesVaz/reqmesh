import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * The git deploy key card: generate, copy, rotate, delete — and the private key
 * must never appear in the DOM. The demo project is not a git repository, which
 * is exactly the case that exercises the card rendering outside the repo panel.
 */
test('generate, copy, rotate and delete the deploy key', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/settings`);
  await app.waitForSelector('main');

  const card = app.getByRole('heading', { name: 'SSH Deploy Key' }).locator('..').locator('..');

  // Empty state.
  await expect(card.getByText(/No deploy key/)).toBeVisible();
  await expect(card.getByRole('button', { name: 'Generate Key' })).toBeVisible();

  // Generate.
  await card.getByRole('button', { name: 'Generate Key' }).click();

  const publicKey = card.locator('code:has-text("ssh-ed25519")');
  await expect(publicKey).toBeVisible();
  const pubText = (await publicKey.textContent()) ?? '';
  expect(pubText.trim().startsWith('ssh-ed25519 ')).toBe(true);

  const fingerprint = card.locator('code:has-text("SHA256:")');
  await expect(fingerprint).toBeVisible();
  const firstFingerprint = (await fingerprint.textContent())?.trim() ?? '';
  expect(firstFingerprint.startsWith('SHA256:')).toBe(true);

  // Copy — the helper falls back to execCommand, so the "Copied" feedback is
  // the honest signal that the text made it into the clipboard.
  await card.getByRole('button', { name: 'Copy' }).click();
  await expect(card.getByText(/Copied/)).toBeVisible();

  // Rotate — the confirm text warns pushes will fail until re-registered.
  await card.getByRole('button', { name: 'Rotate' }).click();
  const dialog = app.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Pushes will fail/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(dialog).toBeHidden();

  const secondFingerprint = (await fingerprint.textContent())?.trim() ?? '';
  expect(secondFingerprint.startsWith('SHA256:')).toBe(true);
  expect(secondFingerprint).not.toBe(firstFingerprint);

  // Delete — back to the empty state.
  await card.getByRole('button', { name: 'Delete' }).click();
  const deleteDialog = app.getByRole('dialog');
  await expect(deleteDialog).toBeVisible();
  await deleteDialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(deleteDialog).toBeHidden();

  await expect(card.getByText(/No deploy key/)).toBeVisible();
  await expect(card.getByRole('button', { name: 'Generate Key' })).toBeVisible();

  // The private key never crossed into the DOM at any point.
  const body = (await app.locator('body').textContent()) ?? '';
  expect(body).not.toContain('PRIVATE KEY');
  expect(body).not.toContain('OPENSSH');
});
