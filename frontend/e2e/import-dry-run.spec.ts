import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The import dialog can preview a spreadsheet import without writing.
 *
 * Two things are load-bearing here and neither is visible from a unit test:
 * a preview must leave the project untouched, and replace mode must say what
 * it would *add* as well as what it would delete — the service used to return
 * early in replace mode and report only `would_delete`, so the preview said
 * nothing about the incoming file.
 */
const P = DEMO_PROJECT;

/** One id that already exists in the demo, two that do not. */
const CSV = [
  '"id","type","name","description","status","priority","verification_method","parent","relations","verification_cases","rationale","source","allocated_to","baselines"',
  '"DRY0001","functional","Dry run one","d","proposed","medium","test","","","","","","",""',
  '"DRY0002","functional","Dry run two","d","proposed","medium","test","","","","","","",""',
  '"AFRM0001","functional","Touched by import","d","proposed","medium","test","","","","","","",""',
].join('\n');

async function reqCount(app: any, project: string): Promise<number> {
  return app.evaluate(async (p: string) => {
    const r = await fetch(`/api/projects/${p}/requirements?limit=2000`, { credentials: 'include' });
    return (await r.json()).total as number;
  }, project);
}

async function openImportWithCsv(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.locator('[title="Import ReqIF / SysML / spreadsheet"]').click();
  await expect(app.getByRole('heading', { name: 'Import Requirements' })).toBeVisible();

  await app.getByRole('button', { name: 'CSV', exact: true }).click();
  await app.locator('input[type=file]').setInputFiles({
    name: 'preview.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV),
  });
}

test('a merge dry run reports counts and changes nothing', async ({ app, server }) => {
  await openImportWithCsv(app, server);
  const before = await reqCount(app, P);

  await app.getByRole('checkbox').check();
  await app.getByRole('button', { name: 'Preview' }).click();

  await expect(app.getByText('Nothing has been changed yet.')).toBeVisible();
  // Two new ids, one that already exists.
  await expect(app.getByText(/2\s*to create/)).toBeVisible();
  await expect(app.getByText(/1\s*to update/)).toBeVisible();

  expect(await reqCount(app, P)).toBe(before);
});

test('replace mode previews the creates as well as the deletions', async ({ app, server }) => {
  await openImportWithCsv(app, server);
  const before = await reqCount(app, P);

  await app.getByRole('button', { name: /^Replace/ }).click();
  await app.getByRole('checkbox').check();
  await app.getByRole('button', { name: 'Preview' }).click();

  await expect(app.getByText('Nothing has been changed yet.')).toBeVisible();
  // Everything is wiped first, so every id'd row is a create — including the
  // one whose id already exists.
  await expect(app.getByText(/3\s*to create/)).toBeVisible();
  await expect(app.getByText(new RegExp(`${before} existing requirements will be deleted first`))).toBeVisible();

  // Above all: the preview did not perform the deletion it described.
  expect(await reqCount(app, P)).toBe(before);
});

test('"Import for real" commits the previewed change', async ({ app, server }) => {
  await openImportWithCsv(app, server);
  const before = await reqCount(app, P);

  await app.getByRole('checkbox').check();
  await app.getByRole('button', { name: 'Preview' }).click();
  await expect(app.getByText('Nothing has been changed yet.')).toBeVisible();

  await app.getByRole('button', { name: 'Import for real' }).click();
  await expect(app.getByText(/Imported/)).toBeVisible();

  expect(await reqCount(app, P)).toBe(before + 2);
});

test('dry run is unavailable for formats that cannot preview', async ({ app, server }) => {
  await openImportWithCsv(app, server);

  const box = app.getByRole('checkbox');
  await box.check();
  await expect(box).toBeChecked();

  // Switching to a parser with no dry-run path must clear the tick as well as
  // disable it — a disabled-but-ticked box would submit a request the route
  // rejects with a 400.
  await app.getByRole('button', { name: 'SysML v2' }).click();
  await expect(box).toBeDisabled();
  await expect(box).not.toBeChecked();
});
