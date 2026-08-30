import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The what-if results inline layout regresses on space, not just presence.
 * These assertions verify the panel is no longer a full-height overlay hiding
 * the requirement it evaluates, and that the floating summary bar appears on
 * every other page to keep the active override visible.
 */
test.describe('what-if inline layout', () => {
  test('Parameters & Constraints remains visible and results card is inline', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements/ACFT0000`);
    await app.waitForSelector('main', { timeout: 20_000 });
    await setEditMode(app, true);

    // Click the what-if toggle on the first literal parameter row.
    await app.click('button[title="What-if override"]');
    // Fill the override input and evaluate.
    const overrideInput = app.locator('input[type="number"][step="any"]');
    await overrideInput.waitFor({ timeout: 5000 });
    await overrideInput.fill('1200');
    await overrideInput.press('Enter');

    // Wait for the what-if results card to appear.
    await app.locator('h2:has-text("Live What-If Preview")').waitFor({ timeout: 15_000 });

    // The whole point: the Parameters & Constraints card is still visible.
    await expect(app.getByText('Parameters & Constraints')).toBeVisible();

    // No full-screen overlay inside the inspector.
    //
    // Measured, not matched by class name. This used to select
    // `main .absolute.inset-0`, which is a proxy for "overlay" that catches any
    // absolutely-positioned element filling *its own* container — a 20 px
    // expression-highlight mirror inside a textarea wrapper trips it just as a
    // full-pane overlay does. Ask the question the test actually means: is
    // anything positioned out of flow covering most of `main`?
    const overlays = await app.evaluate(() => {
      const main = document.querySelector('main');
      if (!main) return [];
      const box = main.getBoundingClientRect();
      return [...main.querySelectorAll('*')]
        .filter((el) => {
          const pos = getComputedStyle(el).position;
          if (pos !== 'absolute' && pos !== 'fixed') return false;
          const r = el.getBoundingClientRect();
          return r.width >= box.width * 0.9 && r.height >= box.height * 0.9;
        })
        .map((el) => `${el.tagName.toLowerCase()}.${(el.className || '').toString().split(' ')[0]}`);
    });
    expect(overlays).toEqual([]);

    // The results card height follows its content — no full-pane stretch.
    const geometry = await app.evaluate(() => {
      const card = [...document.querySelectorAll('.card')].find(
        (el) => el.textContent?.includes('Live What-If Preview'),
      ) as HTMLElement | undefined;
      if (!card) return null;
      const cardRect = card.getBoundingClientRect();
      const lastChild = card.lastElementChild as HTMLElement | null;
      const contentBottom = lastChild ? lastChild.getBoundingClientRect().bottom : cardRect.bottom;
      return {
        cardHeight: cardRect.height,
        contentEnd: contentBottom - cardRect.top,
        diff: Math.abs(cardRect.height - (contentBottom - cardRect.top)),
      };
    });
    expect(geometry).not.toBeNull();
    // Height gap between the card and its last child's bottom must be
    // reasonable — the old overlay left 481 px of dead space.
    expect(geometry!.diff).toBeLessThan(120);

    // The floating summary bar must not appear on the requirement detail page
    // — the inline card occupies that role.
    await expect(app.locator('.sticky.bottom-3.z-30')).toHaveCount(0);
  });

  test('floating bar persists across client-side navigation', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements/ACFT0000`);
    await app.waitForSelector('main', { timeout: 20_000 });
    await setEditMode(app, true);

    // Stage an override.
    await app.click('button[title="What-if override"]');
    const overrideInput = app.locator('input[type="number"][step="any"]');
    await overrideInput.waitFor({ timeout: 5000 });
    await overrideInput.fill('1200');
    await overrideInput.press('Enter');
    await app.locator('h2:has-text("Live What-If Preview")').waitFor({ timeout: 15_000 });

    // Navigate to /risks via the nav — client-side routing preserves context,
    // so the override set above stays active.
    await app.getByRole('button', { name: 'Risks', exact: true }).first().click();
    await app.waitForURL(/\/risks$/);
    await app.waitForSelector('main', { timeout: 20_000 });
    await expect(app.locator('.sticky.bottom-3.z-30')).toBeVisible();
  });
});
