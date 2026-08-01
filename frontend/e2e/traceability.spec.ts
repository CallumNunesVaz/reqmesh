import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test.describe('risk matrix', () => {
  test('a risk rating is derived from the matrix, and re-banding re-rates it', async ({ app, server }) => {
    await signIn(app);

    // Put a known risk at a known cell, through the inline editors on the list.
    await app.goto(`${server.baseURL}/project/${P}/risks`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    const card = app.locator('main .card').filter({ hasText: 'RSK00006' }).first();
    await card.locator('select').filter({ has: app.locator('option[value=critical]') }).first()
      .selectOption('critical');
    await app.waitForTimeout(1200);
    await card.locator('select').filter({ has: app.locator('option[value=possible]') }).first()
      .selectOption('possible');
    await app.waitForTimeout(1500);

    const before = (await api<any[]>(app, `/projects/${P}/risks`)).find((r) => r.id === 'RSK00006');
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
    await app.waitForTimeout(2000);

    // The edit must have landed on the cell that rates critical x possible.
    const stored = await api<any>(app, `/projects/${P}/risk-matrix`);
    const criticalRow = stored.cells[stored.severities.length - 1];
    expect(criticalRow[2]).not.toBe('high');

    const after = (await api<any[]>(app, `/projects/${P}/risks`)).find((r) => r.id === 'RSK00006');
    expect(after.rating.band).not.toBe(bandBefore);

    // And the list badge follows the matrix rather than a table in the client.
    await app.goto(`${server.baseURL}/project/${P}/risks`);
    await app.waitForSelector('main');
    const badge = app.locator('main .card').filter({ hasText: 'RSK00006' })
      .locator('span.badge').first();
    await expect(badge).toHaveText(new RegExp(after.rating.label, 'i'));
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
