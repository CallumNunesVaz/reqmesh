import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

test.describe('session expiry', () => {
  test('a 401 on project data redirects to sign-in, not an empty project', async ({ app, server }) => {
    await signIn(app);

    // Wait for the projects list to render — the test user is signed in
    // and can see their projects.
    await expect(app.getByText('Cessna 172S Skyhawk SP')).toBeVisible({ timeout: 15_000 });

    // Intercept every project API call, list endpoint included, to simulate an
    // expired session.
    //
    // The list endpoint used to be exempt here because intercepting it looped
    // the sign-in page. That exemption was hiding a real bug rather than
    // avoiding a test artefact: with RT_REQUIRE_AUTH the live server also 401s
    // `/api/projects` to a signed-out caller, so production would have looped
    // too. The redirect now fires only for a session that *was* signed in, so
    // this can cover the endpoint that exposed it.
    await app.route(
      (url) => /\/api\/projects(\/|$|\?)/.test(url.toString()),
      async (route) => {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Session expired' }),
        });
      },
    );

    // whoami must also 401, or the redirect reloads the app and
    // AuthInit silently restores the user from the server session.
    await app.route('**/api/auth/whoami', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' }),
      });
    });

    // Click the project link — this is a client-side (React Router)
    // navigation, not a page load, so it won't conflict with the
    // window.location.href redirect that follows.
    await app.locator('h3:has-text("Cessna 172S Skyhawk SP")').click();

    // The SPA renders the project overview page, which fires API calls.
    // The first project-data call returns 401 — client.ts clears auth
    // state and sets window.location.href to /?next=...
    //
    // waitForURL chokes on the frame detach from the redirect, so poll
    // window.location.href directly with waitForFunction instead.
    await app.waitForFunction(
      (fragment) => window.location.href.includes(fragment),
      '?next=',
      { timeout: 20_000 },
    );

    // Sign-in control must be visible (user is logged out).
    await expect(app.locator('[title="Sign in"]')).toBeVisible({ timeout: 10_000 });

    // The empty-state text must NOT be visible — that was the actual bug:
    // the project rendered with zero requirements, indistinguishable from
    // data loss.
    await expect(app.getByText(/No requirements/i)).toHaveCount(0);

    // The URL must carry the original path so the user can return after
    // signing in again.
    const url = await app.evaluate(() => window.location.href);
    expect(url).toContain('next=%2Fproject%2Fcessna-172');

    // Click the sign-in control to reveal the login form.
    await app.locator('[title="Sign in"]').first().click();
    const passwordInput = app.locator('input[type=password]');
    await expect(passwordInput).toBeVisible({ timeout: 10_000 });

    // And the page must have settled rather than be reloading in a loop.
    // The sign-in page's own listProjects() is 401 under the route above, so
    // an unguarded redirect would still be cycling here. Same URL after a
    // pause, with the form still up, is what "settled" means.
    const before = await app.evaluate(() => window.location.href);
    await app.waitForTimeout(2000);
    expect(await app.evaluate(() => window.location.href)).toBe(before);
    await expect(passwordInput).toBeVisible();
  });
});
