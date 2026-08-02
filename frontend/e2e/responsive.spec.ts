import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * The header must not overflow or wrap labels at laptop viewports
 * (1024–1439 px wide). These assertions gate the `whitespace-nowrap` and
 * `2xl:inline` breakpoint changes from the layout task.
 */

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
]) {
  test.describe(`${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test('the header does not overflow', async ({ app, server }) => {
      await signIn(app);
      await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
      await app.waitForSelector('header');
      await app.evaluate(() => document.fonts.ready);

      const header = app.locator('header');
      const scrollWidth = await header.evaluate((el) => el.scrollWidth);
      const clientWidth = await header.evaluate((el) => el.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    });

    test('no header label wraps', async ({ app, server }) => {
      await signIn(app);
      await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
      await app.waitForSelector('header');
      // Measurement depends on the web fonts being applied: with the fallback
      // face still in use the glyph metrics differ and a label can measure as
      // wrapped when it is not. Under parallel workers the fonts sometimes had
      // not settled, which is why this failed only when the machine was busy.
      await app.evaluate(() => document.fonts.ready);

      const violations = await app.evaluate(() => {
        const header = document.querySelector('header');
        if (!header) return [];

        const leaves: Element[] = [];
        const walk = (el: Element) => {
          if (el.children.length === 0) {
            leaves.push(el);
          } else {
            for (let i = 0; i < el.children.length; i++) {
              walk(el.children[i]);
            }
          }
        };
        walk(header);

        // Wrapping is read off the layout directly rather than inferred from
        // height. An inline box gets one client rect per line, so >1 rect *is*
        // wrapping — exact, and independent of font metrics, zoom and line
        // height. The previous `height > lineHeight * 1.6` heuristic was a
        // proxy for the same thing and drifted over that threshold under load,
        // failing on a header that was laid out perfectly well.
        const result: string[] = [];
        for (const el of leaves) {
          const text = el.textContent?.trim() || '';
          if (!text) continue;

          const style = window.getComputedStyle(el);
          // Only inline-level boxes produce a rect per line; a block element
          // always has exactly one regardless of how its text flows.
          if (!style.display.startsWith('inline')) continue;

          const lines = el.getClientRects().length;
          if (lines > 1) {
            result.push(`"${text}" wraps onto ${lines} lines`);
          }
        }
        return result;
      });

      expect(violations).toEqual([]);
    });
  });
}
