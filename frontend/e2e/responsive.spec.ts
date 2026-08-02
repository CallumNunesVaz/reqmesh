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

      const header = app.locator('header');
      const scrollWidth = await header.evaluate((el) => el.scrollWidth);
      const clientWidth = await header.evaluate((el) => el.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    });

    test('no header label wraps', async ({ app, server }) => {
      await signIn(app);
      await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
      await app.waitForSelector('header');

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

        const result: string[] = [];
        for (const el of leaves) {
          const text = el.textContent?.trim() || '';
          if (!text) continue;

          const style = window.getComputedStyle(el);
          let lineHeight = parseFloat(style.lineHeight);
          if (isNaN(lineHeight) || style.lineHeight === 'normal') {
            lineHeight = parseFloat(style.fontSize) * 1.2;
          }

          const rect = el.getBoundingClientRect();
          if (rect.height > lineHeight * 1.6) {
            result.push(
              `"${text}" wraps (height ${rect.height.toFixed(1)} > ${(lineHeight * 1.6).toFixed(1)})`,
            );
          }
        }
        return result;
      });

      expect(violations).toEqual([]);
    });
  });
}
