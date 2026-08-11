import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

test('clicking Export BOM downloads a CSV with the header row', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/components`);
  await app.waitForSelector('main', { timeout: 20_000 });

  const btn = app.locator('button', { hasText: 'Export BOM' });
  await btn.waitFor({ timeout: 10_000 });

  const [download] = await Promise.all([
    app.waitForEvent('download'),
    btn.click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/-bom\.csv$/);

  const stream = await download.createReadStream();
  if (!stream) throw new Error('No readable stream on download');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString('utf-8');
  expect(body.split('\n')[0].trim()).toBe('ID,Name,Type,Part Number,Quantity,Parent');
});

test('Export BOM button is present in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/components`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app, false);

  await expect(app.locator('button', { hasText: 'Export BOM' })).toBeVisible();
});
