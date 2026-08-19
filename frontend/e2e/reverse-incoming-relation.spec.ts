import { test, expect, signIn, setEditMode, api, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

// AFRM0004 is a clean target: three incoming relations (AFRM0005, AFRM0006,
// SAFE0001) and no outgoing ones, so a flip moves a row from Incoming to
// Outgoing without ambiguity. The flip we exercise is the seeded
// `AFRM0005 --refines--> AFRM0004`.
const TARGET = 'AFRM0004';
const SOURCE = 'AFRM0005';

test.describe('reverse incoming relation', () => {
  test('flipping an incoming relation leaves exactly one relation on this requirement and none on the source', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/${TARGET}`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    await app.getByTitle(`Flip: make ${TARGET} → refines → ${SOURCE}`).click();

    await expect(async () => {
      const target = await api<any>(app, `/projects/${P}/requirements/${TARGET}`);
      expect(target.relations.filter((r: any) => r.type === 'refines' && r.target === SOURCE)).toHaveLength(1);
      const source = await api<any>(app, `/projects/${P}/requirements/${SOURCE}`);
      expect(source.relations.filter((r: any) => r.target === TARGET)).toHaveLength(0);
    }).toPass({ timeout: 10_000 });
  });

  test('a flipped incoming relation persists across reload and flips back', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/${TARGET}`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    await app.getByTitle(`Flip: make ${TARGET} → refines → ${SOURCE}`).click();

    // Wait for the flip to land, then reload to prove it persisted.
    await expect(async () => {
      const target = await api<any>(app, `/projects/${P}/requirements/${TARGET}`);
      expect(target.relations.filter((r: any) => r.type === 'refines' && r.target === SOURCE)).toHaveLength(1);
    }).toPass({ timeout: 10_000 });

    await app.reload();
    await app.waitForSelector('main');
    await setEditMode(app, true);

    // The relation is now outgoing from the target — flip it back.
    await app.getByTitle(`Flip: make ${SOURCE} → refines → ${TARGET}`).click();

    await expect(async () => {
      const source = await api<any>(app, `/projects/${P}/requirements/${SOURCE}`);
      expect(source.relations.filter((r: any) => r.type === 'refines' && r.target === TARGET)).toHaveLength(1);
      const target = await api<any>(app, `/projects/${P}/requirements/${TARGET}`);
      expect(target.relations.filter((r: any) => r.target === SOURCE)).toHaveLength(0);
    }).toPass({ timeout: 10_000 });
  });

  test('flipping against a deleted source surfaces an error and leaves both records intact', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/${TARGET}`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    // Simulate the source being deleted after the page loaded: the incoming
    // row still renders from the cached list, but the server 404s the source.
    const sourceUrl = (url: URL) => url.pathname.endsWith(`/api/projects/${P}/requirements/${SOURCE}`);
    await app.route(sourceUrl, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Requirement not found' }),
        });
      } else {
        await route.continue();
      }
    });

    await app.getByTitle(`Flip: make ${TARGET} → refines → ${SOURCE}`).click();

    const alert = app.locator('[role=alert]').last();
    await expect(alert).toBeVisible({ timeout: 10_000 });
    await expect(alert).toContainText(/Could not flip relation|Requirement not found/);

    await app.unroute(sourceUrl);

    // Neither record changed.
    const source = await api<any>(app, `/projects/${P}/requirements/${SOURCE}`);
    expect(source.relations.filter((r: any) => r.target === TARGET)).toHaveLength(1);
    const target = await api<any>(app, `/projects/${P}/requirements/${TARGET}`);
    expect(target.relations.filter((r: any) => r.target === SOURCE)).toHaveLength(0);
  });
});
