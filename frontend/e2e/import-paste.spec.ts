import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Dialog-content assertions are scoped with `dlg(app)`.
 *
 * The import dialog announces its summary through the app-wide live region
 * (components/LiveRegion.tsx) — a real, non-hidden node carrying the same
 * numbers as the visible panel — so a bare `getByText(/2 to create/)` matches
 * twice and trips Playwright strict mode. Scoping is the fix, not loosening the
 * assertion: it still requires the text to be in the dialog the user is looking
 * at. Any future `useAnnounce` adoption needs the same care.
 */
const dlg = (app: any) => app.locator('[role="dialog"]');

const P = DEMO_PROJECT;

const CSV = [
  '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baselines"',
  '"PST0001","functional","Pasted one","d","proposed","medium","test","","","","","","",""',
  '"PST0002","functional","Pasted two","d","proposed","medium","test","","","","","","",""',
].join('\n');

async function reqCount(app: any, project: string): Promise<number> {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    return (await r.json()).total as number;
  }, project);
}

async function openPasteImport(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.locator('[title="Import ReqIF / SysML / spreadsheet"]').click();
  await expect(app.getByRole('heading', { name: 'Import Requirements' })).toBeVisible();

  await app.getByRole('button', { name: 'Paste data' }).click();
  await app.getByRole('button', { name: 'CSV', exact: true }).click();
}

test('pasting CSV rows with dry run shows the preview and leaves the count unchanged', async ({ app, server }) => {
  await openPasteImport(app, server);
  const before = await reqCount(app, P);

  const textarea = app.locator('textarea');
  await textarea.fill(CSV);

  await app.getByRole('checkbox').check();
  await app.getByRole('button', { name: 'Preview' }).click();

  await expect(dlg(app).getByText('Nothing has been changed yet.')).toBeVisible();
  await expect(dlg(app).getByText(/2\s*to create/)).toBeVisible();

  expect(await reqCount(app, P)).toBe(before);
});

test('committing pasted rows then changes the count', async ({ app, server }) => {
  await openPasteImport(app, server);
  const before = await reqCount(app, P);

  const textarea = app.locator('textarea');
  await textarea.fill(CSV);

  await app.getByRole('checkbox').check();
  await app.getByRole('button', { name: 'Preview' }).click();
  await expect(dlg(app).getByText('Nothing has been changed yet.')).toBeVisible();

  await app.getByRole('button', { name: 'Import for real' }).click();
  await expect(dlg(app).getByText(/Imported/)).toBeVisible();

  expect(await reqCount(app, P)).toBe(before + 2);
});

test('the submit button is disabled with an empty textarea', async ({ app, server }) => {
  await openPasteImport(app, server);

  const button = app.getByRole('button', { name: 'Import' }).last();
  await expect(button).toBeDisabled();

  const textarea = app.locator('textarea');
  await textarea.fill('   ');
  await expect(button).toBeDisabled();

  await textarea.fill(CSV);
  await expect(button).toBeEnabled();
});
