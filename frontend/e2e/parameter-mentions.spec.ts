import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';
import type { Page } from '@playwright/test';

/**
 * A parameter mentioned in a description resolves to its value + unit, and the
 * reference stays live: change the parameter and the prose follows without the
 * description being touched.
 *
 * The parameter is added and its value changed through the API (the seed must
 * stay pristine for every other spec); the `@` mention and the read-mode
 * assertions run through the real UI and the real save path.
 */

const P = DEMO_PROJECT;
const REQ = 'ACFT0000';
const PARAM = 'temp_max';

type Param = { name: string; value: number | null; unit?: string; expr?: string | null };

async function getJson<T = unknown>(page: Page, path: string): Promise<T> {
  return page.evaluate(async (p) => {
    const r = await fetch(`/api${p}`, { credentials: 'include' });
    if (!r.ok) throw new Error(`GET ${p} → ${r.status}`);
    return r.json();
  }, path);
}

async function putJson(page: Page, path: string, body: unknown): Promise<void> {
  const cookies = await page.context().cookies();
  const token = cookies.find((c) => c.name === 'csrftoken')?.value || '';
  const res = await page.evaluate(async ([p, b, t]) => {
    const r = await fetch(`/api${p}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t as string },
      body: JSON.stringify(b),
    });
    return { status: r.status, body: await r.json().catch(() => null) };
  }, [path, body, token] as const);
  if (res.status >= 400) throw new Error(`PUT ${path} → ${res.status}: ${JSON.stringify(res.body)}`);
}

async function waitFor(page: Page, fn: () => Promise<boolean>, timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await fn()) return;
    await page.waitForTimeout(200);
  }
  throw new Error('condition not met within timeout');
}

test('a parameter mention resolves to value+unit and follows value changes', async ({ app, server }) => {
  await signIn(app);

  // Add a parameter to the requirement before the page fetches the index.
  const before = await getJson<{ parameters: Param[] }>(app, `/projects/${P}/requirements/${REQ}`);
  await putJson(app, `/projects/${P}/requirements/${REQ}`, {
    parameters: [...(before.parameters ?? []), { name: PARAM, value: 30, unit: '°C', expr: null }],
  });

  await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app, true);

  // Replace the description with prose that mentions the parameter via `@`.
  const descCard = app.locator('.card').filter({ hasText: 'Description' }).first();
  const editor = descCard.locator('.ProseMirror').first();
  await editor.click();
  await app.keyboard.press('Control+a');
  await app.keyboard.type(`The limit is @${PARAM}`);

  const option = app.locator('[role=option]').filter({ hasText: PARAM }).first();
  await expect(option).toBeVisible({ timeout: 10_000 });
  await option.click();

  await app.waitForTimeout(300);
  await app.keyboard.press('Control+s');

  // The save round-trips: the server persists the [[ID.param]] bracket token.
  await waitFor(app, async () => {
    const r = await getJson<{ description: string }>(app, `/projects/${P}/requirements/${REQ}`);
    return r.description.includes(`[[${REQ}.${PARAM}]]`);
  });

  // Reload to read the stored HTML (not the in-editor state).
  await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await expect(descCard).toContainText('30 °C', { timeout: 10_000 });
  await expect(descCard).not.toContainText(`[[${REQ}.${PARAM}]]`);

  // Change the parameter's value without touching the description.
  const current = await getJson<{ parameters: Param[] }>(app, `/projects/${P}/requirements/${REQ}`);
  const changed = current.parameters.map((p) => (p.name === PARAM ? { ...p, value: 42 } : p));
  await putJson(app, `/projects/${P}/requirements/${REQ}`, { parameters: changed });

  await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await expect(descCard).toContainText('42 °C', { timeout: 10_000 });
});
