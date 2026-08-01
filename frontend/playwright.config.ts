import { defineConfig, devices } from '@playwright/test';

/**
 * The backend is booted per worker by the `server` fixture rather than by
 * `webServer` here, because the projects below need it started with different
 * environments — an auth-required deployment behaves differently from the
 * first request onward.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['list']] : 'list',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1600, height: 1000 },
    // reqmesh follows the OS colour scheme and Chromium reports "light",
    // which is not how most people see the app.
    colorScheme: 'dark',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'app',
      testIgnore: /auth-gate\.spec\.ts/,
    },
    {
      // RT_REQUIRE_AUTH=true: no guest session, so /api/projects 401s on load.
      name: 'auth-required',
      testMatch: /auth-gate\.spec\.ts/,
      use: { requireAuth: true },
    },
  ],
});
