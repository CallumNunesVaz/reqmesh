import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * The export dialog's component picker must actually narrow the exported
 * document — not just toggle a checkbox. The backend had the wiring for
 * `components=` for ages but the dialog never sent it, so every report
 * contained the whole project.
 *
 * The demo project's "YOKE01" component satisfies exactly FLTC0001, and nothing
 * satisfies ACFT0000 but the C172 root. So a YOKE01-scoped report renders
 * FLTC0001 as a real requirement link and never renders ACFT0000 as one
 * (it may still appear as a "(not in this document)" dangling reference in the
 * Components table, which is why the assertion checks the link, not the id).
 */

test('picking one component narrows the exported document', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
  await app.waitForSelector('main');

  await app.locator('[title="Export document"]').click();
  const dialog = app.getByRole('dialog');

  // Deselect everything, then pick a single component. The picker defaults to
  // "All", which means "no filter" — clicking None then YOKE01 is the explicit
  // one-component selection.
  await dialog.locator('button[title="Select no components"]').click();
  await dialog.getByText('YOKE01', { exact: true }).click();

  const [download] = await Promise.all([
    app.waitForEvent('download'),
    dialog.getByRole('button', { name: /Download/ }).click(),
  ]);

  const stream = await download.createReadStream();
  if (!stream) throw new Error('No readable stream on download');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString('utf-8');

  // The chosen component's requirement is a real entry; the excluded one is not.
  expect(body).toContain('href="#req-FLTC0001"');
  expect(body).not.toContain('href="#req-ACFT0000"');
});
