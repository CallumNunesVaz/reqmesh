import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * Every remaining route renders without crashing.
 *
 * Deliberately shallow — these assert the page mounts, reaches its own content
 * and logs no uncaught error. That is enough to catch the failure mode this
 * suite exists for: a lazy route whose chunk fails to resolve, or a component
 * that throws on mount, both of which now surface as the ErrorBoundary's
 * "Something went wrong" rather than a blank screen.
 */
const P = DEMO_PROJECT;

async function expectNoCrash(page: import('@playwright/test').Page) {
  await expect(page.getByText('Something went wrong')).toHaveCount(0);
  // The Suspense fallback must have resolved into real content.
  await expect(page.locator('main, [role=main]')).toBeVisible();
}

test('the users page renders', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/users`);
  await app.waitForSelector('main');
  await expect(app.getByRole('heading', { name: /users/i }).first()).toBeVisible();
  await expectNoCrash(app);
});

test('the system page renders', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/system`);
  await app.waitForSelector('main');
  await expectNoCrash(app);
});

test('the graph page renders the canvas', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/graph`);
  await app.waitForSelector('main');
  // ELK is dynamically imported, so give the layout a beat to land.
  // `.first()`: this route renders a second graph pane alongside the
  // persistent canvas, so the locator legitimately matches twice.
  await expect(app.locator('.react-flow').first()).toBeVisible({ timeout: 20_000 });
  await expectNoCrash(app);
});

test('the publish page renders its format options', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/publish`);
  await app.waitForSelector('main');
  await expectNoCrash(app);
});

test('an unknown route redirects to the project list rather than blanking', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/no-such-page`);
  await app.waitForSelector('main');
  await expect(app.getByRole('heading', { name: /projects/i }).first()).toBeVisible();
});
