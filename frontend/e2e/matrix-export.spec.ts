import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('allocation matrix Download CSV button is visible in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  const btn = app.locator('button[title="Download this matrix as CSV"]');
  await expect(btn).toBeVisible({ timeout: 20_000 });
});

test('allocation matrix Download CSV downloads a file with the expected name and header', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main');

  const btn = app.locator('button[title="Download this matrix as CSV"]');
  await btn.waitFor({ timeout: 20_000 });

  const [download] = await Promise.all([
    app.waitForEvent('download'),
    btn.click(),
  ]);

  // The default axis is components, and the filename says which axis it is —
  // the four axes share one URL, so a fixed name would collide.
  expect(download.suggestedFilename()).toBe(`${P}-allocation-components.csv`);

  const stream = await download.createReadStream();
  if (!stream) throw new Error('No readable stream on download');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString('utf-8');
  expect(body.split('\n')[0].trim()).toMatch(/^Requirement,/);
});

test('trace matrix Download CSV button is visible in viewing mode', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/traces`);
  await app.waitForSelector('main');
  await setEditMode(app, false);

  const btn = app.locator('button[title="Download this matrix as CSV"]');
  await expect(btn).toBeVisible({ timeout: 20_000 });
});

test('trace matrix Download CSV downloads a file with the expected name and header', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/traces`);
  await app.waitForSelector('main');

  const btn = app.locator('button[title="Download this matrix as CSV"]');
  await btn.waitFor({ timeout: 20_000 });

  const [download] = await Promise.all([
    app.waitForEvent('download'),
    btn.click(),
  ]);

  expect(download.suggestedFilename()).toBe(`${P}-trace-matrix.csv`);

  const stream = await download.createReadStream();
  if (!stream) throw new Error('No readable stream on download');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString('utf-8');
  expect(body.split('\n')[0].trim()).toMatch(/^Source,/);
});
