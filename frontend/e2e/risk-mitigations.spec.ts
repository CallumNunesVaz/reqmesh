import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Adding a requirement to "Mitigated By" on a risk persists independently
 * from "Threatens" — the two lists must not write over each other on save.
 */
const P = DEMO_PROJECT;

test('mitigated-by persists and does not overwrite threatens', async ({ app, server }) => {
  await signIn(app);

  // Get the list of risks and requirements to pick IDs.
  // list_requirements returns {items, total, offset, limit} (offset=0, limit=500
  // are defaults), while list_risks returns a plain array when no offset/limit
  // are passed.
  const risks: any[] = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
    return r.json();
  }, P);

  const reqsPage: any = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/requirements`, { credentials: 'include' });
    return r.json();
  }, P);
  const requirements: any[] = reqsPage.items || reqsPage;

  const risk = risks[0];
  expect(risk).toBeTruthy();

  // Pick two distinct requirements, one for each list.
  const threatenedReq = requirements.find((r: any) => !risk.linked_requirements.includes(r.id));
  const mitigatingReq = requirements.find(
    (r: any) => r.id !== threatenedReq?.id && !risk.linked_requirements.includes(r.id),
  );
  expect(threatenedReq).toBeTruthy();
  expect(mitigatingReq).toBeTruthy();

  // Navigate to risks page and enter edit mode.
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // Add a requirement to "Threatens" on the first risk.
  const riskCard = app.locator('.card').filter({ hasText: risk.id }).first();
  await expect(riskCard).toBeVisible();

  // Select the "Threatens" dropdown and add the threatened requirement.
  const threatensSelect = riskCard.locator('[data-link-editor="Threatens"] select');
  await threatensSelect.selectOption(`${threatenedReq.id} — ${threatenedReq.name}`);

  // Now add a requirement to "Mitigated By".
  // Addressed by name, not position: component pickers now sit after this one,
  // so `.last()` silently pointed at the wrong control.
  const mitigatedSelect = riskCard.locator('[data-link-editor="Mitigated By"] select');
  await mitigatedSelect.selectOption(`${mitigatingReq.id} — ${mitigatingReq.name}`);

  // Wait for the optimistic update + API call to settle.
  await app.waitForTimeout(1500);

  // Reload the page.
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');

  // The reloaded risk should have both lists independently.
  const reloaded: any[] = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
    return r.json();
  }, P);

  const reloadedRisk = reloaded.find((r: any) => r.id === risk.id);
  expect(reloadedRisk).toBeTruthy();
  expect(reloadedRisk.linked_requirements).toContain(threatenedReq.id);
  expect(reloadedRisk.mitigating_requirements || []).toContain(mitigatingReq.id);
});
