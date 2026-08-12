import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Associating labels with their controls put many inputs *inside* a <label>.
 * Tailwind's preflight makes form controls inherit `letter-spacing` and
 * `font-weight`, and `.label` carries `tracking-wider font-semibold` — so a
 * wrapped input renders what the user typed bold and wide-spaced unless
 * `.input` states those properties itself.
 *
 * This pins that. Revert the `tracking-normal font-normal` in `.input`
 * (styles/index.css) and this fails with letterSpacing 0.6px / fontWeight 600.
 * Note it only fails against a *rebuilt* bundle — the e2e app project serves
 * dist, so `npm run build` must run before the CSS change is visible here.
 */
test('an input wrapped in its label does not inherit label typography', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/risks`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await app.getByRole('button', { name: /new risk|add risk|create/i }).first().click();

  const wrapped = app.getByLabel('Title').first();
  await expect(wrapped).toBeVisible();

  // The control really is inside its label — otherwise this test proves nothing.
  const isWrapped = await wrapped.evaluate((el) => el.closest('label') !== null);
  expect(isWrapped).toBe(true);

  const style = await wrapped.evaluate((el) => {
    const c = getComputedStyle(el);
    return { letterSpacing: c.letterSpacing, fontWeight: c.fontWeight };
  });
  expect(style.letterSpacing).toBe('normal');
  expect(style.fontWeight).toBe('400');
});
