import { test, expect, signIn, setEditMode, DEMO_PROJECT, api } from './fixtures';

const P = DEMO_PROJECT;

async function putViaApp(app: any, path: string, body: any) {
  const csrfResp = await app.evaluate(async () => {
    const r = await fetch('/api/auth/whoami', { credentials: 'include' });
    return (await r.json()).csrf_token || '';
  });
  return app.evaluate(async ({ path, body, csrf }: { path: string; body: any; csrf: string }) => {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify(body),
      credentials: 'include',
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }, { path, body, csrf: csrfResp });
}

test('restore restores the name via API and records audit', async ({ app }) => {
  await signIn(app);

  const original = await api(app, `/projects/${P}/requirements/AFRM0001`);
  const originalName = original.name;

  await putViaApp(app, `/api/projects/${P}/requirements/AFRM0001`, { name: 'Restore Test Name' });
  const edited = await api(app, `/projects/${P}/requirements/AFRM0001`);
  expect(edited.name).toBe('Restore Test Name');

  const history = await api(app, `/projects/${P}/history/AFRM0001`);
  const updateEntry = history.find((e: any) => e.action === 'update');
  expect(updateEntry).toBeTruthy();

  const csrf = await app.evaluate(async () => {
    const r = await fetch('/api/auth/whoami', { credentials: 'include' });
    return (await r.json()).csrf_token || '';
  });
  const res = await app.evaluate(async ({ p, eid, csrf }: any) => {
    const r = await fetch(`/api/projects/${p}/requirements/AFRM0001/history/${encodeURIComponent(eid)}/restore`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf },
      credentials: 'include',
    });
    return { status: r.status, body: await r.json().catch(() => r.status) };
  }, { p: P, eid: updateEntry.id, csrf });

  expect(res.status).toBe(200);
  expect(res.body.name).toBe(originalName);

  const updatedHistory = await api(app, `/projects/${P}/history/AFRM0001`);
  expect(updatedHistory.length).toBeGreaterThan(history.length);
  expect(updatedHistory[0].action).toBe('update');
  expect(Object.keys(updatedHistory[0].changes)).toContain('name');
});

test('Restore button visible in edit mode and absent in viewing mode', async ({ app, server }) => {
  await signIn(app);

  await putViaApp(app, `/api/projects/${P}/requirements/AFRM0001`, { name: 'Edit Test' });

  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main', { timeout: 20_000 });

  // Viewing mode: Restore absent.
  await expect(app.getByRole('button', { name: 'VIEWING' })).toBeVisible({ timeout: 10_000 });
  await app.waitForTimeout(1500);
  await expect(app.getByRole('button', { name: 'Restore' })).toHaveCount(0);

  // Edit mode: Restore visible.
  await setEditMode(app);
  await expect(app.getByRole('button', { name: 'EDITING' })).toBeVisible({ timeout: 10_000 });
  await app.waitForTimeout(1000);
  await expect(app.getByRole('button', { name: 'Restore' }).first()).toBeVisible({ timeout: 10_000 });
});
