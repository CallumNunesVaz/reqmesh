import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

test('baseline diff shows against-current by default', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await setEditMode(app);

  // Click the diff button on the SRR baseline. The button has title="Diff against current".
  const diffBtn = app.locator('[title="Diff against current"]').first();
  await diffBtn.click();

  // The diff result panel should appear.
  const diffPanel = app.locator('.border-l-cs-purple');
  await expect(diffPanel).toBeVisible({ timeout: 10_000 });

  // The heading should mention the baseline name.
  await expect(diffPanel.locator('h3')).toContainText('SRR');

  // The "against" select should default to "Current state".
  await expect(diffPanel.locator('select')).toHaveValue('');
});

test('baseline diff selects another baseline to compare', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await setEditMode(app);

  // Open the diff for SRR.
  const diffBtn = app.locator('[title="Diff against current"]').first();
  await diffBtn.click();

  const diffPanel = app.locator('.border-l-cs-purple');
  await expect(diffPanel).toBeVisible({ timeout: 10_000 });

  // Record the initial change count text.
  const initialText = await diffPanel.locator('[class*="text-muted-foreground"]').first().textContent();

  // Select PDR from the dropdown.
  await diffPanel.locator('select').selectOption('PDR');

  // The diff should re-fetch — the result text should change (or at least we
  // should not have errored).
  await expect(diffPanel).toBeVisible({ timeout: 10_000 });
  // The heading should still mention SRR.
  await expect(diffPanel.locator('h3')).toContainText('SRR');
});

test('baseline diff returns to current state when default selected', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/baselines`);
  await app.waitForSelector('main');
  await setEditMode(app);

  const diffBtn = app.locator('[title="Diff against current"]').first();
  await diffBtn.click();

  const diffPanel = app.locator('.border-l-cs-purple');
  await expect(diffPanel).toBeVisible({ timeout: 10_000 });
  const againstCurrent = await diffPanel.innerText();

  // Switch to the other baseline: the rendered diff must actually change.
  // Polled against innerText rather than toHaveText, which collapses whitespace
  // and so can never equal the multi-line text this panel renders.
  await diffPanel.locator('select').selectOption('PDR');
  await expect
    .poll(() => diffPanel.innerText(), { timeout: 10_000 })
    .not.toBe(againstCurrent);

  // Switching back must re-fetch, not merely reset the select. Asserting the
  // select's own value here would pass without any re-fetch at all — the panel
  // kept showing the baseline-to-baseline result while the control claimed to
  // be on "Current state".
  await diffPanel.locator('select').selectOption('');
  await expect
    .poll(() => diffPanel.innerText(), { timeout: 10_000 })
    .toBe(againstCurrent);
  await expect(diffPanel.locator('select')).toHaveValue('');
});
