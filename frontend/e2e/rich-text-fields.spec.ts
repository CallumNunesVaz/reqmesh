import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Rich-text fields for risks and components, plus the risk form overflow fix.
 *
 * Covers:
 *  1. No clipping on the risk create form at laptop width (the regression guard).
 *  2. Round-trip a rich description on a risk — bold survives save + reload.
 *  3. Component detail page has a TipTap editor, no description textarea.
 *  4. Baselines page renders HTML descriptions without literal tag soup.
 */

const P = DEMO_PROJECT;

// ── 1. No clipping ───────────────────────────────────────────────────────────

test.describe('risk create form', () => {
  test.use({ viewport: { width: 1280, height: 720 } });

  test('the create form does not overflow at laptop width', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/risks`);
    await app.waitForSelector('main');
    await setEditMode(app, true);

    // Open the create form
    await app.getByRole('button', { name: 'New Risk' }).click();
    const form = app.locator('form').filter({ has: app.locator('input[placeholder="RSK-001"]') });
    await expect(form).toBeVisible({ timeout: 10_000 });
    // Let the framer-motion height animation settle
    await app.waitForTimeout(500);

    // Regression guard: the form must not overflow its container
    const scrollWidth = await form.evaluate((el) => el.scrollWidth);
    const clientWidth = await form.evaluate((el) => el.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

    // The submit button must be visible and sit inside the form's bounds,
    // ignoring any y-overflow caused by flex-wrap pushing it to a second row.
    const button = form.getByRole('button', { name: /Create|Save/ });
    await expect(button).toBeVisible();

    const formBox = await form.boundingBox();
    const buttonBox = await button.boundingBox();
    expect(formBox).toBeTruthy();
    expect(buttonBox).toBeTruthy();
    expect(buttonBox!.x).toBeGreaterThanOrEqual(formBox!.x - 1);
    expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(formBox!.x + formBox!.width + 1);
  });
});

// ── 2. Round-trip rich description on a risk ─────────────────────────────────

test('bold text in a risk description survives save and reload', async ({ app, server }) => {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // Hover the first risk card to reveal the edit button
  const card = app.locator('.card').filter({ hasText: 'RSK00001' }).first();
  await card.hover();

  // Open the editor on this risk
  const editBtn = card.locator('[title="Edit risk"]');
  await expect(editBtn).toBeVisible();
  await editBtn.click();

  // The edit form should now show the risk's id (disabled) and a RichTextEditor
  const form = app.locator('form').filter({ has: app.locator('input[value="RSK00001"]') });
  await expect(form).toBeVisible({ timeout: 10_000 });

  // TipTap uses a contentEditable div, not an input — use keyboard to type
  const editor = form.locator('.ProseMirror');
  await editor.click();
  // Select all existing content and replace it
  await app.keyboard.press('Control+a');
  await app.keyboard.type('This is a ');

  // Bold the next word — use Control+b to keep focus in the editor
  await app.keyboard.press('Control+b');
  await app.keyboard.type('bold');
  await app.keyboard.press('Control+b');
  await app.keyboard.type(' description.');

  // Save
  await form.getByRole('button', { name: 'Save' }).click();
  // Wait for the save to complete and the form to close
  await expect(form).not.toBeVisible({ timeout: 10_000 });

  // Reload the page
  await app.goto(`${server.baseURL}/project/${P}/risks`);
  await app.waitForSelector('main');
  // Let the risks list load and the card render
  await app.waitForTimeout(1000);

  // The card for RSK00001 should now contain the description with a <strong>
  const riskCard = app.locator('.card').filter({ hasText: 'RSK00001' }).first();
  await expect(riskCard).toBeVisible({ timeout: 10_000 });

  // The description is rendered as HTML, so the <strong> must be a real element.
  //
  // Located by content rather than by class: this used to select
  // `.line-clamp-1`, which was the truncation bug itself, so removing the clamp
  // broke the test that was meant to be checking the bold round-trip. A test
  // pinned to a utility class fails when the styling is fixed.
  await expect(riskCard.locator('strong', { hasText: 'bold' })).toBeVisible();

  // And the literal string "<strong>" must not appear as visible text — that is
  // what an escaping renderer would produce.
  await expect(riskCard).not.toContainText('<strong>');
});

// ── 3. Component detail page: TipTap, no textarea ────────────────────────────

test('component detail page uses TipTap editor for description, not a textarea', async ({ app, server }) => {
  await signIn(app);
  // C172 is the top-level component in the demo seed
  await app.goto(`${server.baseURL}/project/${P}/components/C172`);
  await app.waitForSelector('main');
  await setEditMode(app, true);

  // The description control should be a TipTap editor (.ProseMirror)
  const editor = app.locator('.ProseMirror').first();
  await expect(editor).toBeVisible({ timeout: 15_000 });

  // There should be no textarea for description in the main content area
  // (The ProseMirror editor replaces the old textarea)
  const mainContent = app.locator('.grid').first();
  const descriptionTextarea = mainContent.locator('textarea');
  await expect(descriptionTextarea).toHaveCount(0, { timeout: 10_000 });
});

// ── 4. Baselines ─────────────────────────────────────────────────────────────
//
// Deliberately not covered. BaselinesPage's read-only description branch was
// changed here too (raw dangerouslySetInnerHTML -> AutoLinkHtml), but it is
// effectively unreachable: it renders only when `editable` is false, and the
// button that opens the form is itself gated on `editable`. The only way in is
// to open the form and then revoke edit mode while it is open.
//
// The test that stood here asserted "no literal <p> appears on the page" and
// passed against an empty list — it would have passed against entirely broken
// code, on a branch it never rendered. A test that cannot fail is worse than an
// acknowledged gap, so this is the gap, acknowledged.
