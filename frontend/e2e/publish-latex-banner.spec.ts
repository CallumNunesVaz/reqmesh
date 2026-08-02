import { test, expect, signIn, api, DEMO_PROJECT } from './fixtures';

/**
 * The publish page's "LaTeX engine not detected" banner must reflect what the
 * server actually said, never an unanswered probe.
 *
 * It used to initialise its state to `false` and swallow fetch failures, so the
 * banner rendered on every page load until the request resolved — and forever
 * if it failed. The endpoint requires auth, so an expired session was enough to
 * tell a perfectly healthy deployment that its PDFs were being downgraded to
 * HTML. Observed on the production host, where the server was in fact
 * compiling LaTeX PDFs successfully the whole time.
 *
 * Asserted as an invariant rather than a fixed expectation, so it holds whether
 * or not a LaTeX engine exists on the machine running the test.
 */

const BANNER = 'LaTeX engine not detected';

test('the LaTeX warning matches what the server reports', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/publish`);
  await app.waitForSelector('main');

  const status = await api<{ available: boolean; engine: string | null }>(
    app, '/system/latex-status',
  );

  // Select PDF — the banner is gated on the chosen format.
  await app.getByText('PDF', { exact: false }).first().click();
  // Give the probe time to resolve; the bug was that the banner showed while
  // it was still in flight, so a bare expect() could pass by racing it.
  await app.waitForTimeout(1500);

  const shown = await app.getByText(BANNER).count();

  if (status.available) {
    expect(shown, `server reports engine "${status.engine}", so the banner must not claim otherwise`)
      .toBe(0);
  } else {
    expect(shown, 'server reports no engine, so the warning is correct and must appear')
      .toBeGreaterThan(0);
  }
});

test('the banner is absent before the probe resolves', async ({ app, server }) => {
  // Unknown is not "unavailable". With the probe hung, the page must stay
  // silent rather than assert a downgrade that may not be happening.
  await signIn(app);
  await app.route('**/api/system/latex-status', async () => { /* never respond */ });
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/publish`);
  await app.waitForSelector('main');
  await app.getByText('PDF', { exact: false }).first().click();
  await app.waitForTimeout(1500);

  await expect(app.getByText(BANNER)).toHaveCount(0);
});
