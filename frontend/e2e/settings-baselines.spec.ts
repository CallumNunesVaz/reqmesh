import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The project settings page no longer shows baseline sections, and a
 * settings save does NOT wipe existing baselines (the regression guard for
 * the `baselines: []` payload bug).
 */
const P = DEMO_PROJECT;

test('project settings shows no baseline headings', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/settings`);
  await app.waitForSelector('main');

  await expect(app.getByRole('heading', { name: 'Baseline Definitions' })).toHaveCount(0);
  await expect(app.getByRole('heading', { name: 'Baselines' })).toHaveCount(0);
});

test('baselines survive a settings save', async ({ app, server }) => {
  await signIn(app);

  // Read the csrftoken cookie via the Playwright context — the cookie has
  // path=/api so document.cookie inside the page JS cannot see it, but
  // the browser context's cookie jar is accessible here.
  const cookies = await app.context().cookies();
  const csrfToken = cookies.find((c) => c.name === 'csrftoken')?.value || '';

  const baselineName = 'E2E-SURVIVE';

  // Define the baseline in metadata first so it appears in list_baselines.
  // Freezing no longer sweeps every requirement into a baseline — it captures
  // only what is ticked, so a baseline with no members (or no metadata
  // definition) would otherwise not appear in the listing.
  await app.evaluate(async ({ project, name, token }: {
    project: string; name: string; token: string;
  }) => {
    const r = await fetch(`/api/projects/${project}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ baselines: [{ name, symbol: 'E', description: 'E2E survivor' }] }),
    });
    return r.status;
  }, { project: P, name: baselineName, token: csrfToken });

  // Freeze a baseline via POST.  Include the CSRF token header so the
  // global CSRF middleware accepts the request.
  const freezeStatus = await app.evaluate(async ({ project, name, token }: {
    project: string; name: string; token: string;
  }) => {
    const r = await fetch(`/api/projects/${project}/baselines/${name}/freeze`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': token },
    });
    return r.status;
  }, { project: P, name: baselineName, token: csrfToken });
  expect(freezeStatus).toBe(200);

  // Confirm it appears in the list.
  const before = await app.evaluate(async ({ project, name }: {
    project: string; name: string;
  }) => {
    const r = await fetch(`/api/projects/${project}/baselines`, { credentials: 'include' });
    const list: any[] = await r.json();
    return list.find((b: any) => b.name === name) != null;
  }, { project: P, name: baselineName });
  expect(before).toBe(true);

  // Open project settings, change the project name, and save.
  await app.goto(`${server.baseURL}/project/${P}/settings`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  const nameInput = app.locator('.input.text-lg');
  // The demo project's name.
  await nameInput.fill('Cessna-172-E2E');
  await app.getByRole('button', { name: /^Save/ }).first().click();
  // Poll the API until the save lands — no fixed sleep.
  await expect(async () => {
    const result = await app.evaluate(async ({ project, name }: {
      project: string; name: string;
    }) => {
      const r = await fetch(`/api/projects/${project}/baselines`, { credentials: 'include' });
      const list: any[] = await r.json();
      return list.find((b: any) => b.name === name) != null;
    }, { project: P, name: baselineName });
    expect(result).toBe(true);
  }).toPass({ timeout: 10_000 });

  // The baseline must still exist — the settings save must NOT have posted
  // `baselines: []` and wiped it.
  const after = await app.evaluate(async ({ project, name }: {
    project: string; name: string;
  }) => {
    const r = await fetch(`/api/projects/${project}/baselines`, { credentials: 'include' });
    const list: any[] = await r.json();
    return list.find((b: any) => b.name === name) != null;
  }, { project: P, name: baselineName });
  expect(after).toBe(true);

  // Restore the original name so this test is idempotent.
  await nameInput.fill('Cessna 172 Navigation and Avionics');
  await app.getByRole('button', { name: /^Save/ }).first().click();
  await app.waitForTimeout(1000);
});
