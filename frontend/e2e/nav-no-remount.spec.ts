import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * Navigating to a page for the first time must not tear down the chrome.
 *
 * Every route is React.lazy, so the first visit to each one suspends while its
 * chunk downloads. The Suspense boundary used to wrap the whole <Routes> tree
 * including <Layout />, so that suspension unmounted the nav pane, header and
 * graph canvas, painted a fullscreen splash, and remounted everything when the
 * chunk arrived — a full-screen flash on the first click of every nav item,
 * gone on the second (chunk cached) and back after a refresh (fresh registry).
 *
 * The boundary now sits inside Layout around the page area. This asserts the
 * invariant that broke: the nav element is never detached across a first-visit
 * navigation.
 */

const P = DEMO_PROJECT;

test('the chrome survives a first visit to each page', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('header');

  // Delay lazy route chunks so React actually suspends. On localhost a chunk
  // arrives in about a millisecond, React resolves it within the same commit,
  // and no fallback is ever shown — so without this the test passes whether or
  // not the boundary is in the right place, which is worse than no test.
  // Applied after the first page has loaded so only *subsequent* route chunks
  // are slowed.
  await app.route('**/assets/*.js', async (route) => {
    await new Promise((r) => setTimeout(r, 600));
    await route.continue();
  });

  // Tag the live header node — part of the chrome Layout owns. If React
  // unmounts it the property goes with it, which is a far stronger signal than
  // "a header exists": a remounted tree still has one.
  await app.evaluate(() => {
    (document.querySelector('header') as any).__navMarker = 'original';
  });

  // Click through the nav pane rather than app.goto(): a goto is a full page
  // load, which remounts the chrome whatever Suspense does, so it cannot
  // observe this bug at all. Client-side navigation is what flashed.
  for (const label of ['Risks', 'Baselines', 'Specifications', 'Metrics']) {
    await app.getByRole('button', { name: label, exact: true }).first().click();
    await app.waitForURL(new RegExp(`/${label.toLowerCase()}$`));
    await app.waitForSelector('main');
    const marker = await app.evaluate(
      () => (document.querySelector('header') as any)?.__navMarker ?? null,
    );
    expect(marker, `the chrome was remounted when navigating to ${label}`).toBe('original');
  }
});

test('the page-level fallback is scoped to the page, not the viewport', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('main');

  // The outer fullscreen splash must not be what a route suspension shows.
  // `fixed inset-0` is the fullscreen variant; the in-page one is `absolute`.
  await app.getByRole('button', { name: 'Risks', exact: true }).first().click();
  await app.waitForSelector('main');
  const fullscreenSplashes = await app.locator('.rm-splash.fixed').count();
  expect(fullscreenSplashes).toBe(0);
});
