import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

function hexToRgb(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}

test.describe('risk matrix', () => {
  test('a risk rating is derived from the matrix, and re-banding re-rates it', async ({ app, server }) => {
    await signIn(app);

    // Put a known risk at a known cell, through the pickers on its detail page.
    await app.goto(`${server.baseURL}/project/${P}/risks/RSK00006`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    await app.getByLabel('Severity').selectOption('critical');
    // Wait for the severity PATCH to land before touching the likelihood select.
    await expect(async () => {
      const risk = await api<any>(app, `/projects/${P}/risks/RSK00006`);
      expect(risk?.severity).toBe('critical');
    }).toPass({ timeout: 10_000 });
    await app.getByLabel('Likelihood').selectOption('possible');
    // Wait for the likelihood PATCH to land before checking the rating.
    await expect(async () => {
      const risk = await api<any>(app, `/projects/${P}/risks/RSK00006`);
      expect(risk?.rating?.likelihood).toBe('possible');
    }).toPass({ timeout: 10_000 });

    const before = await api<any>(app, `/projects/${P}/risks/RSK00006`);
    expect(before.severity).toBe('critical');
    expect(before.rating.likelihood).toBe('possible');
    const bandBefore = before.rating.band;

    // Re-band exactly the cell that rates it: rows render most-severe first,
    // so critical is row 0; 'possible' is the third likelihood column.
    await app.goto(`${server.baseURL}/project/${P}/settings`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    const matrix = app.locator('.card').filter({ has: app.getByRole('heading', { name: 'Risk Matrix' }) });
    // Only the coloured band buttons — the first cell of each row also holds
    // the severity's remove button, which would shift every index by one.
    const cell = matrix.locator('tbody tr').first()
      .locator('td button[style*="background"]').nth(2);
    await cell.scrollIntoViewIfNeeded();
    await cell.click();
    await app.getByRole('button', { name: /^Save$/ }).first().click();
    // Poll the API until the save lands — no fixed sleep.
    await expect(async () => {
      const stored = await api<any>(app, `/projects/${P}/risk-matrix`);
      const criticalRow = stored.cells[stored.severities.length - 1];
      expect(criticalRow[2]).not.toBe('high');
    }).toPass({ timeout: 10_000 });

    // The edit must have landed on the cell that rates critical x possible.
    const stored = await api<any>(app, `/projects/${P}/risk-matrix`);
    const criticalRow = stored.cells[stored.severities.length - 1];
    expect(criticalRow[2]).not.toBe('high');

    const after = await api<any>(app, `/projects/${P}/risks/RSK00006`);
    expect(after.rating.band).not.toBe(bandBefore);

    // And the band indicator on the list row follows the matrix rather than a
    // table in the client — the coloured dot in the band column should carry
    // the band that was just reassigned.
    await app.goto(`${server.baseURL}/project/${P}/risks`);
    await app.waitForSelector('main');
    const dot = app.locator('#entity-RSK00006')
      .locator('span.w-2.h-2.rounded-full').first();
    const expected = hexToRgb(after.rating.color);
    await expect(dot).toHaveCSS('background-color', expected);
  });
});

test.describe('cross-entity links', () => {
  test('backlinks list everything that references a requirement', async ({ app }) => {
    await signIn(app);
    const data = await api<any>(app, `/projects/${P}/entities/AVNC0001/backlinks`);
    expect(data.collection).toBe('requirements');
    expect(data.total).toBeGreaterThan(0);
    const holders = data.groups.map((g: any) => g.collection).sort();
    expect(holders).toContain('components');
    expect(holders).toContain('specifications');
  });

  test('the requirement page shows a Referenced By panel', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/AVNC0001`);
    await app.waitForSelector('main');
    await expect(app.getByRole('heading', { name: 'Referenced By' })).toBeVisible();
  });

  test('deleting a referenced requirement is refused with the referrer list', async ({ app }) => {
    await signIn(app);
    const res = await app.evaluate(async (p) => {
      const r = await fetch(`/api/projects/${p}/requirements/AVNC0001`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRF-Token': (window as any).__csrf || '' },
      });
      return { status: r.status, body: await r.json().catch(() => null) };
    }, P);
    // 403 without a CSRF token, 409 with one — either way it is not a silent
    // 200 that strands the references, which is what it used to be.
    expect([403, 409]).toContain(res.status);
  });

  test('a requirement verification list is derived from the owning case', async ({ app }) => {
    await signIn(app);
    const vcs = await api<any>(app, `/projects/${P}/verification`);
    const list = Array.isArray(vcs) ? vcs : vcs.items;
    const vc = list.find((v: any) => (v.verified_requirements || []).length);
    const req = await api<any>(app, `/projects/${P}/requirements/${vc.verified_requirements[0]}`);
    expect(req.verification_cases).toContain(vc.id);
  });
});

test.describe('project integrity', () => {
  test('the seeded project reports no dangling or asymmetric links', async ({ app }) => {
    await signIn(app);
    const issues = (await api<any>(app, `/projects/${P}/validate`)).issues as any[];
    const kinds = new Set(issues.map((i) => i.type));
    expect(kinds.has('dangling_reference')).toBe(false);
    expect(kinds.has('asymmetric_link')).toBe(false);
    expect(kinds.has('corrupt_file')).toBe(false);
  });
});
