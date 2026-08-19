import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * The traceability matrix wants the whole pane, not a reading column, and its
 * two axes should show the requirement tree rather than a flat id list.
 *
 * At 1920 wide the old `max-w-5xl mx-auto` cap kept the grid to 1024px while
 * the pane beside it sat empty. The hierarchy comes from `requirement.parent`
 * (depth-first, indented); the seeded project's AFRM0000 → AFRM0001 pair makes
 * the indentation visible on the column axis.
 */
const P = DEMO_PROJECT;

async function openGrid(app: any, server: any) {
  await app.goto(`${server.baseURL}/project/${P}/traces`);
  await app.waitForSelector('main');
  await app.getByRole('button', { name: 'Grid' }).click();
  await app.waitForSelector('main table');
}

test('the grid fills the pane beyond the old 5xl cap without body overflow', async ({ app, server }) => {
  await app.setViewportSize({ width: 1920, height: 1400 });
  await signIn(app);
  await openGrid(app, server);

  const metrics = await app.evaluate(() => {
    const table = document.querySelector('main table') as HTMLElement | null;
    const scroller = table?.parentElement as HTMLElement | null;
    if (!table || !scroller) return null;
    return {
      grid: Math.round(scroller.getBoundingClientRect().width),
      bodyOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });

  expect(metrics).not.toBeNull();
  // max-w-5xl is 64rem = 1024px; the grid must exceed it.
  expect(metrics!.grid).toBeGreaterThan(1024);
  // The pane scrolls the matrix internally; the page itself must not widen.
  expect(metrics!.bodyOverflow).toBe(false);
});

test('a child requirement is indented relative to its parent and both navigate', async ({ app, server }) => {
  await app.setViewportSize({ width: 1920, height: 1400 });
  await signIn(app);
  await openGrid(app, server);

  const axes = await app.evaluate(() => {
    const measure = (id: string) => {
      const th = Array.from(document.querySelectorAll('main thead th'))
        .find((el) => (el.textContent || '').trim().startsWith(id));
      if (!th) return null;
      const link = th.querySelector('a') as HTMLElement | null;
      if (!link) return null;
      const thRect = th.getBoundingClientRect();
      const linkRect = link.getBoundingClientRect();
      return {
        left: Math.round(linkRect.left - thRect.left),
        href: link.getAttribute('href') || '',
      };
    };
    return { parent: measure('AFRM0000'), child: measure('AFRM0001') };
  });

  expect(axes.parent).not.toBeNull();
  expect(axes.child).not.toBeNull();
  // Both are links to their own requirement page.
  expect(axes.parent!.href).toContain('/requirements/AFRM0000');
  expect(axes.child!.href).toContain('/requirements/AFRM0001');
  // The child sits deeper in the tree, so its label starts further right.
  expect(axes.child!.left).toBeGreaterThan(axes.parent!.left);

  // And the indentation wrapper has not broken the link itself.
  await app.locator('main thead th a', { hasText: 'AFRM0001' }).first().click();
  await expect(app).toHaveURL(/\/requirements\/AFRM0001$/);
});
