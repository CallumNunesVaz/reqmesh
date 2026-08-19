import { test, expect, signIn } from './fixtures';

/**
 * The report logo can be set from a URL or an uploaded PNG. Once a PNG had
 * been uploaded the URL field disappeared entirely — the only way back to a
 * URL was the small remove X. The URL field must always be reachable, and the
 * upload path (size check included) must keep working.
 */

const PNG_1x1 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

test('a data: logo still offers a URL field that switches back to a URL', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/settings`);
  await app.waitForSelector('main');

  // Establish the embedded-image state by uploading a PNG.
  await app.setInputFiles('input[type=file]', {
    name: 'logo.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_1x1, 'base64'),
  });
  await expect(app.getByText('Embedded image', { exact: false })).toBeVisible();

  // The URL field is still present, ready to switch away from the PNG.
  const urlField = app.getByPlaceholder('Paste a URL to switch');
  await expect(urlField).toBeVisible();

  await urlField.fill('https://example.com/logo.png');
  await app.getByRole('button', { name: 'Use URL' }).click();

  await expect(app.getByText('Embedded image', { exact: false })).toHaveCount(0);
  await expect(app.getByPlaceholder('https://… or paste a data: URI')).toHaveValue('https://example.com/logo.png');
});

test('uploading a PNG produces a preview', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/settings`);
  await app.waitForSelector('main');

  await app.setInputFiles('input[type=file]', {
    name: 'logo.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_1x1, 'base64'),
  });

  await expect(app.locator('img[alt="Logo preview"]')).toBeVisible();
  await expect(app.getByText('Embedded image', { exact: false })).toBeVisible();
});

test('an oversized file reports the error and keeps the previous value', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/settings`);
  await app.waitForSelector('main');

  // Set a small logo first.
  await app.setInputFiles('input[type=file]', {
    name: 'logo.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_1x1, 'base64'),
  });
  await expect(app.locator('img[alt="Logo preview"]')).toBeVisible();

  // A > 1 MB file is rejected, leaving the previous logo intact.
  await app.setInputFiles('input[type=file]', {
    name: 'big.png',
    mimeType: 'image/png',
    buffer: Buffer.alloc(1_100_000, 1),
  });

  await expect(app.getByText('Image is too large', { exact: false })).toBeVisible();
  await expect(app.locator('img[alt="Logo preview"]')).toBeVisible();
  await expect(app.getByText('Embedded image', { exact: false })).toBeVisible();
});
