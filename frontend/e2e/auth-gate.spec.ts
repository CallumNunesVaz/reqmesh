import { test, expect, signIn } from './fixtures';

/**
 * Runs against a server booted with RT_REQUIRE_AUTH=true, so there is no guest
 * session and the first GET /api/projects returns 401.
 *
 * Both assertions below are regressions from a real deployment. The app
 * rendered the 401 as "Can't reach the backend — Is the API running on port
 * 8000?", which sends an operator to inspect a healthy server and hides the
 * fact that a sign-in control exists. And because the projects fetch did not
 * re-run on sign-in, a successful login left the error on screen — from the
 * outside, indistinguishable from the login having failed.
 */
test.describe('a deployment that requires authentication', () => {
  test('asks for sign-in rather than claiming the backend is unreachable', async ({ app }) => {
    await expect(app.getByText(/sign in to see your projects/i)).toBeVisible();
    await expect(app.getByText(/can't reach the backend/i)).toHaveCount(0);
    await expect(app.getByText(/running on port 8000/i)).toHaveCount(0);
  });

  test('lists projects immediately after signing in, with no reload', async ({ app }) => {
    await signIn(app);
    await expect(app.getByText('Cessna 172S Skyhawk SP')).toBeVisible({ timeout: 15_000 });
    await expect(app.getByText(/sign in to see your projects/i)).toHaveCount(0);
  });
});
