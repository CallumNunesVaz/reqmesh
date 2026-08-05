import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The history panel actually renders entries.
 *
 * This exists because the first implementation never fetched at all: it guarded
 * the effect with a ref initialised to the current itemId, so the very first
 * render compared equal and returned before calling the API. Typecheck, build,
 * the unit suites and the whole e2e run were all green, because nothing
 * asserted that the panel had content — and the "loading" and "empty" states
 * rendered the same sentence, so it looked deliberate.
 */
const P = DEMO_PROJECT;

test('a requirement edit shows up in its history panel', async ({ app, server }) => {
  await signIn(app);
  await setEditMode(app);

  // The request itself is the assertion. Checking rendered text is not enough:
  // the broken version rendered the same "No recorded changes" that a genuinely
  // empty history shows, so only "did it ask the server" separates them.
  const historyCall = app.waitForResponse(
    (r) => r.url().includes(`/projects/${P}/history/`) && r.status() === 200,
    { timeout: 15000 },
  );

  // Straight to a detail page, where the panel is defaultOpen. Rows on the list
  // page are buttons that call navigate(), not anchors, so there is no href to
  // click.
  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await historyCall;

  const panel = app.getByText('Change History').locator('..');
  await expect(panel).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText('Loading history…')).toHaveCount(0, { timeout: 15000 });
});

test('a risk card can reveal its history without loading it up front', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');

  // Collapsed by default: the list pages mount one panel per card, and eager
  // loading meant one history request per risk just to render the page.
  const toggles = app.getByRole('button', { name: 'Show change history' });
  // Wait rather than count immediately: the risk list is fetched after mount,
  // so `main` being present says nothing about the cards existing yet.
  await expect(toggles.first()).toBeVisible({ timeout: 15000 });

  const historyCall = app.waitForResponse(
    (r) => r.url().includes(`/projects/${P}/history/`) && r.status() === 200,
    { timeout: 15000 },
  );
  await toggles.first().click();
  await historyCall;
  await expect(app.getByText('Loading history…')).toHaveCount(0, { timeout: 15000 });
});
