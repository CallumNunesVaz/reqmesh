import { test, expect, signIn, setEditMode, pickLinkOption, DEMO_PROJECT } from './fixtures';

/**
 * Adding a requirement to "Mitigated By" on a risk persists independently
 * from "Threatens" — the two lists must not write over each other on save.
 */
const P = DEMO_PROJECT;

test('mitigated-by persists and does not overwrite threatens', async ({ app, server }) => {
  await signIn(app);

  // Get the list of risks and requirements to pick IDs. Both list endpoints
  // return a {items, total, offset, limit} page now, so unwrap `items`.
  const risks: any[] = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
    return (await r.json()).items;
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

  // Navigate to the risk's detail page and enter edit mode.
  await app.goto(`${server.baseURL}/project/${P}/risks/${encodeURIComponent(risk.id)}`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // Add a requirement to "Threatens" on the risk's detail page. The detail
  // page carries one editor per direction, so these are page-level locators.
  // Addressed by name, not position: component pickers now sit after this one,
  // so `.last()` silently pointed at the wrong control.
  await pickLinkOption(app.locator('[data-link-editor="Threatens"]'), threatenedReq.id);

  // Now add a requirement to "Mitigated By".
  await pickLinkOption(app.locator('[data-link-editor="Mitigated By"]'), mitigatingReq.id);

  // Poll the API until both link changes land — no fixed sleep.
  await expect(async () => {
    const current: any[] = await app.evaluate(async (project: string) => {
      const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
      return (await r.json()).items;
    }, P);
    const updated = current.find((r2: any) => r2.id === risk.id);
    expect(updated?.linked_requirements).toContain(threatenedReq.id);
    expect(updated?.mitigating_requirements || []).toContain(mitigatingReq.id);
  }).toPass({ timeout: 10_000 });

  // Reload the page.
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');

  // The reloaded risk should have both lists independently.
  const reloaded: any[] = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
    return (await r.json()).items;
  }, P);

  const reloadedRisk = reloaded.find((r: any) => r.id === risk.id);
  expect(reloadedRisk).toBeTruthy();
  expect(reloadedRisk.linked_requirements).toContain(threatenedReq.id);
  expect(reloadedRisk.mitigating_requirements || []).toContain(mitigatingReq.id);
});
