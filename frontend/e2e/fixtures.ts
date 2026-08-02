import { test as base, expect, type Page } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { cpSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../..');
const BACKEND = join(REPO, 'backend');
const DIST = join(REPO, 'frontend/dist');

export const ADMIN = 'admin';
export const ADMIN_PASSWORD = 'e2e-admin-password';
export const DEMO_PROJECT = 'cessna-172';

function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const srv = net.createServer();
    srv.on('error', rej);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address() as net.AddressInfo;
      srv.close(() => res(port));
    });
  });
}

async function waitForHealth(port: number, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/health`);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`backend never became healthy on :${port}`);
}

export interface Server {
  port: number;
  baseURL: string;
  /** Live project data root — restored from `pristine` before every test. */
  projects: string;
  /** Copy of the seeded state taken once, immediately after boot. */
  pristine: string;
}

/**
 * A backend per worker, each with its own data root.
 *
 * Specs mutate project data — re-banding the risk matrix, deleting entities —
 * so sharing one server across workers would make results depend on scheduling.
 * The cost is one uvicorn per worker, which is cheap next to a flaky suite.
 *
 * `requireAuth` is a *worker* option because it changes how the server boots:
 * with it, there is no guest session and the first request 401s, which is the
 * whole point of the auth-gate spec.
 */
export const test = base.extend<{ app: Page }, { requireAuth: boolean; server: Server }>({
  requireAuth: [false, { option: true, scope: 'worker' }],

  server: [async ({ requireAuth }, use) => {
    if (!existsSync(join(DIST, 'index.html'))) {
      throw new Error(`no build at ${DIST} — run: npm run build --prefix frontend`);
    }
    const dataRoot = mkdtempSync(join(tmpdir(), 'reqmesh-e2e-'));
    const home = mkdtempSync(join(tmpdir(), 'reqmesh-e2e-home-'));
    const port = await freePort();

    // The repo venv locally; whatever python is on PATH in CI.
    const venvPython = join(BACKEND, '.venv/bin/python');
    const python = existsSync(venvPython) ? venvPython : 'python3';

    const proc: ChildProcess = spawn(
      python,
      ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
      {
        cwd: BACKEND,
        stdio: 'ignore',
        env: {
          ...process.env,
          HOME: home,                     // redirects ~/.reqmesh — never touches real accounts
          RT_DATA_ROOT: join(dataRoot, 'projects'),
          RT_STATIC_DIR: DIST,
          RT_SEED_DEMO: 'true',
          RT_GIT_AUTOCOMMIT: 'false',     // driving the UI must not author commits
          RT_ADMIN_PASSWORD: ADMIN_PASSWORD,
          RT_REQUIRE_AUTH: requireAuth ? 'true' : 'false',
          RT_PROFILE: 'team',
          RT_COOKIE_SECURE: 'false',      // tests speak plain HTTP
          // Buckets are keyed `ip:path` and every request here comes from
          // 127.0.0.1, so specs sharing a worker exhaust an endpoint's
          // allowance between them and start seeing 429s unrelated to what
          // they assert. The server logs a warning when this is off.
          RT_RATE_LIMIT_ENABLED: 'false',
        },
      },
    );

    try {
      await waitForHealth(port);
      // Snapshot the freshly seeded projects so each test can start from them.
      // The server seeds on first boot, so this must happen after health.
      const projects = join(dataRoot, 'projects');
      const pristine = join(dataRoot, '__pristine');
      cpSync(projects, pristine, { recursive: true });
      await use({ port, baseURL: `http://127.0.0.1:${port}`, projects, pristine });
    } finally {
      proc.kill('SIGKILL');
      rmSync(dataRoot, { recursive: true, force: true });
      rmSync(home, { recursive: true, force: true });
    }
  }, { scope: 'worker' }],

  app: async ({ page, server }, use) => {
    // Restore the seeded projects before each test.
    //
    // The backend is worker-scoped, so without this every spec inherits
    // whatever the previous one left behind: a re-banded risk matrix, a
    // deleted requirement, an extra baseline. That is why the suite's failures
    // moved around between runs and with worker count — the failing test was
    // whichever one happened to run after a mutating neighbour.
    //
    // The store caches parses by mtime, and a fresh copy has new mtimes, so
    // the restore invalidates it without needing a server restart.
    rmSync(server.projects, { recursive: true, force: true });
    cpSync(server.pristine, server.projects, { recursive: true });

    // Every destructive action is a window.confirm, and Playwright auto-
    // *dismisses* dialogs unless something listens — which silently turns a
    // delete into a no-op that still reports success.
    page.on('dialog', (d) => d.accept().catch(() => {}));
    await page.goto(server.baseURL);
    await page.waitForSelector('header', { timeout: 20_000 });
    await use(page);
  },
});

export { expect };

/** Sign in through the header control. It is an icon button whose only label
 *  is `title="Sign in"`, so there is no text to match on. */
export async function signIn(page: Page, username = ADMIN, password = ADMIN_PASSWORD) {
  // A cold load auto-signs-in as a guest, and the guest fills the signed-in
  // header slot — so there is no "Sign in" control until the guest signs out.
  const signIn = page.locator('[title="Sign in"]');
  if (!(await signIn.count())) {
    const signOut = page.locator('[title="Sign out"]');
    if (await signOut.count()) {
      await signOut.first().click();
      await signIn.first().waitFor({ timeout: 10_000 });
    }
  }
  await signIn.first().click();
  const dialog = page.locator('input[type=password]');
  await dialog.waitFor({ state: 'visible', timeout: 10_000 });
  const inputs = page.locator('input');
  await inputs.first().fill(username);
  await dialog.fill(password);
  await page.keyboard.press('Enter');
  await expect(page.locator('input[type=password]')).toHaveCount(0, { timeout: 15_000 });
}

/** Edit mode resets on every navigation, so call this *after* landing on the
 *  page under test. Mutating controls are unrendered or disabled without it. */
export async function setEditMode(page: Page, on = true) {
  const toggle = page.locator('[title*="enable editing" i], [title*="disable editing" i]');
  await toggle.first().waitFor({ timeout: 10_000 });
  const editing = await page.locator('text=EDITING').count();
  if ((on && !editing) || (!on && editing)) {
    await toggle.first().click();
    await page.waitForTimeout(400);
  }
}

/** Read through the API with the browser's session — the ground truth behind
 *  the UI, and the cheapest way to prove a mutation actually landed. */
export async function api<T = any>(page: Page, path: string): Promise<T> {
  return page.evaluate(async (p) => {
    const r = await fetch(`/api${p}`, { credentials: 'include' });
    return r.json();
  }, path);
}
