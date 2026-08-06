import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

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

  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main', { timeout: 20_000 });
  await setEditMode(app);

  // Wait for risk cards to render.
  await expect(app.locator('.card').filter({ hasText: /RSK/ }).first()).toBeVisible({ timeout: 15_000 });

  // Find a risk card and use the "Threatens" LinkEditor to add a link.
  // The select triggers setRiskRequirements -> updateRisk -> PUT -> 500 -> toast.
  const riskCard = app.locator('.card').filter({ hasText: /RSK/ }).first();
  const linkSelect = riskCard.locator('[data-link-editor="Threatens"] select');
  await linkSelect.waitFor({ timeout: 10_000 });

  // Pick any option except the empty first one.
  //
  // Asserted rather than skipped. These were early `return`s, which meant a
  // demo with no linkable requirements — or a picker that stopped rendering
  // its options at all — turned this test green while exercising nothing. A
  // test for an invisible failure must not itself be able to fail invisibly.
  const options = linkSelect.locator('option');
  await expect(options).not.toHaveCount(1);
  const value = await options.nth(1).getAttribute('value');
  expect(value, 'the first real option must carry a value to select').toBeTruthy();
  await linkSelect.selectOption(value!);

  // Wait for the optimistic update + API call + 500 response.
  await app.waitForTimeout(1500);

  // The error toast should appear.
  const alert = app.locator('[role=alert]').last();
  await expect(alert).toBeVisible({ timeout: 10_000 });
  await expect(alert).toContainText('Server write error');
});

test('a 409 delete guard surfaces the referrer count in the toast', async ({ app, server }) => {
  await signIn(app);

  // Verification cases have IDs starting with "VC" — intercept DELETE on
  // the verification-cases endpoint and return a 409 that mimics the
  // server's delete-guard response.
  await app.route(
    (url) => url.toString().includes(`/api/projects/${P}/verification-cases/`),
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

  // Verification case IDs start with "VC" (e.g. VCAF0001).  Wait for at
  // least one to render, then find its card by the id text.
  await expect(app.locator('.card').filter({ hasText: /VC/ }).first()).toBeVisible({ timeout: 15_000 });

  const vcCard = app.locator('.card').filter({ hasText: /VC/ }).first();
  // Hover the card to expose the delete button (opacity-0 until group-hover).
  await vcCard.hover();

  const deleteBtn = vcCard.locator('[title="Delete"]');
  await deleteBtn.click();

  // Auto-accepted window.confirm — the real server returns a 409 with
  // the referrer list.  Assert the toast contains the server's message,
  // not a generic fallback.
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
    await app.waitForTimeout(1500);
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
