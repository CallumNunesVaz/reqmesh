import { test, expect, signIn, setEditMode, pickLinkOption, DEMO_PROJECT } from './fixtures';

/**
 * When a write (create/update/delete) fails the server MUST surface the
 * failure through an error toast.  Before 047 every mutation difference
 * that ended in `.catch(() => {})` / `catch { }` / `console.error` was
 * invisible — a rejected save rendered identically to a successful one.
 */
const P = DEMO_PROJECT;

test('a failed requirement update raises an error toast', async ({ app, server }) => {
  await signIn(app);

  // Intercept PUT to the risks endpoint — changing a risk's linked
  // requirements triggers a PUT (updateRisk) and the catch block now
  // calls addToast.
  await app.route(
    (url) => url.toString().includes(`/api/projects/${P}/risks/`),
    async (route) => {
      const req = route.request();
      if (req.method() === 'PUT') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Server write error — disk full' }),
        });
      } else {
        await route.continue();
      }
    },
  );

  await app.goto(`${server.baseURL}/project/${P}/risks/RSK00001`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  // The risk detail page carries one LinkEditor per direction, so there is no
  // per-risk card to scope to. Picking a requirement triggers
  // setRiskRequirements -> updateRisk -> PUT -> 500 -> toast.
  //
  // Pick a linkable requirement, asserted rather than skipped. These were
  // early `return`s, which meant a demo with no linkable requirements — or a
  // picker that stopped rendering its options at all — turned this test green
  // while exercising nothing. A test for an invisible failure must not itself
  // be able to fail invisibly.
  const risks: any[] = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/risks`, { credentials: 'include' });
    return (await r.json()).items;
  }, P);
  const reqsPage: any = await app.evaluate(async (project: string) => {
    const r = await fetch(`/api/projects/${project}/requirements`, { credentials: 'include' });
    return r.json();
  }, P);
  const requirements: any[] = reqsPage.items || reqsPage;
  const risk = risks.find((r: any) => r.id === 'RSK00001') ?? risks[0];
  expect(risk).toBeTruthy();
  const linkable = requirements.find((r: any) => !risk.linked_requirements.includes(r.id));
  expect(linkable, 'the first real option must carry a value to select').toBeTruthy();

  const editor = app.locator('[data-link-editor="Threatens"]');
  await editor.waitFor({ timeout: 10_000 });
  await pickLinkOption(editor, linkable.id);

  // The error toast should appear — the expect below has its own timeout,
  // so no fixed sleep is needed here.
  const alert = app.locator('[role=alert]').last();
  await expect(alert).toBeVisible({ timeout: 10_000 });
  await expect(alert).toContainText('Server write error');
});

test('a 409 delete guard surfaces the referrer count in the toast', async ({ app, server }) => {
  await signIn(app);

  // Verification cases live under the /verification endpoint — intercept
  // DELETE and return a 409 that mimics the server's delete-guard response.
  await app.route(
    (url) => url.toString().includes(`/api/projects/${P}/verification/`),
    async (route) => {
      const req = route.request();
      if (req.method() === 'DELETE') {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'referenced by 7 verification runs' }),
        });
      } else {
        await route.continue();
      }
    },
  );

  await app.goto(`${server.baseURL}/project/${P}/verification`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  // The row navigates to the detail page, which is where delete now lives.
  await app.locator('#entity-VCAF0001').click();
  await app.waitForSelector('main', { timeout: 20_000 });
  await app.locator('[title="Delete"]').waitFor({ timeout: 10_000 });
  await app.locator('[title="Delete"]').click();

  // The themed confirmation dialog appears — click Delete to confirm.
  // Restrict to the dialog so we don't match the page's own Delete button.
  const dialog = app.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Delete' }).click();

  // The server returns a 409 with the referrer list.  Assert the toast
  // contains the server's message, not a generic fallback.
  const alert = app.locator('[role=alert]').last();
  await expect(alert).toBeVisible({ timeout: 10_000 });
  await expect(alert).toContainText(/referenced by \d/);
});

test('a successful save raises no error toast', async ({ app, server }) => {
  await signIn(app);

  await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await expect(app.locator('h1, h2').filter({ hasText: /AFRM0001/ }).first()).toBeVisible({ timeout: 20_000 });

  await setEditMode(app);

  // Wait for the editor to mount.
  const editor = app.locator('.ProseMirror').first();
  await editor.waitFor({ state: 'visible', timeout: 15_000 });

  // If the Save button is enabled the form is dirty from a prior test;
  // do a real save to clear the dirty state so we can verify clean state
  // produces no error toast.
  const saveBtn = app.getByRole('button', { name: 'Save changes' });
  if (await saveBtn.isEnabled({ timeout: 3000 }).catch(() => false)) {
    await saveBtn.click();
    // Wait for the save to complete — the button becomes disabled when there
    // are no unsaved changes, which is a real condition, not a guess.
    await expect(saveBtn).toBeDisabled({ timeout: 10_000 });
  }

  // No [role=alert] error toast anywhere.
  const alerts = app.locator('[role=alert]');
  const count = await alerts.count();
  if (count > 0) {
    for (let i = 0; i < count; i++) {
      const text = await alerts.nth(i).textContent();
      expect(text, `unexpected error toast: "${text}"`).not.toMatch(/error|fail/i);
    }
  }
});
