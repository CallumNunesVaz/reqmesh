import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * Matrices use the width of the pane they are given.
 *
 * The tables were intrinsically sized, so an axis with few columns drew at its
 * natural width and left the rest of the inspector blank — the baselines axis
 * used 437px of 620px. A dense axis must still overflow into the container's
 * scroll rather than squeezing 81 columns into the pane, so this asserts both
 * directions, and asserts them as geometry: a test that only checked the table
 * rendered would have passed the whole time.
 */
const P = DEMO_PROJECT;

async function tableFit(app: any) {
  return app.evaluate(() => {
    const t = document.querySelector('main table') as HTMLElement | null;
    const scroller = t?.parentElement as HTMLElement | null;
    if (!t || !scroller) return null;
    return {
      table: Math.round(t.getBoundingClientRect().width),
      container: Math.round(scroller.getBoundingClientRect().width),
      cols: t.querySelectorAll('thead th').length,
    };
  });
}

test('a sparse allocation axis fills the pane, a dense one still scrolls', async ({ app, server }) => {
  await app.setViewportSize({ width: 1600, height: 1000 });
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main table', { timeout: 20000 });
  await app.waitForTimeout(1500);

  // Components: many columns, must stay wider than the pane.
  const dense = await tableFit(app);
  expect(dense).not.toBeNull();
  expect(dense.cols).toBeGreaterThan(20);
  expect(dense.table).toBeGreaterThan(dense.container);

  // Baselines: few columns, must not leave the pane part-empty.
  await app.getByRole('tab', { name: /baseline/i }).click();
  await app.waitForTimeout(1500);
  const sparse = await tableFit(app);
  expect(sparse.cols).toBeLessThan(12);
  expect(sparse.table).toBeGreaterThanOrEqual(sparse.container - 2);
});

test('the matrix follows the pane when it is resized', async ({ app, server }) => {
  await signIn(app);
  await app.setViewportSize({ width: 1600, height: 1000 });
  await app.goto(`${server.baseURL}/project/${P}/allocation`);
  await app.waitForSelector('main table', { timeout: 20000 });
  await app.getByRole('tab', { name: /baseline/i }).click();
  await app.waitForTimeout(1500);

  const before = await tableFit(app);

  await app.setViewportSize({ width: 1900, height: 1000 });
  await app.waitForTimeout(1200);
  const after = await tableFit(app);

  // Wider pane, wider table — and still no blank strip beside it.
  expect(after.container).toBeGreaterThan(before.container);
  expect(after.table).toBeGreaterThan(before.table);
  expect(after.table).toBeGreaterThanOrEqual(after.container - 2);
});
