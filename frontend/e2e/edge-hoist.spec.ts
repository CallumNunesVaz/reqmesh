import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * When a group is collapsed, a relationship whose endpoint lives inside it is
 * redrawn to the group itself — the line must still reach the group rather
 * than silently disappearing. The demo project opens with most groups
 * auto-collapsed, so the hoisted path is the *common* case on first paint:
 * `ENVR0001 → PROP0001` (cabin heat depends on the engine) lives inside
 * `ENVR0000` and `PROP0000` respectively, and both are folded, so the relation
 * is hoisted to `ENVR0000 → PROP0000`.
 */
const HOISTED_EDGE_ID = 'ENVR0000-PROP0000-depends-hoist';

async function openGraph(app: any, server: any) {
  await signIn(app);
  // The overview route shows the Layout canvas beside the overview page — a
  // single GraphPane. (The dedicated /graph route renders a second full-page
  // GraphPane, doubling every edge.)
  await app.goto(`${server.baseURL}/project/${P}`);
  await app.waitForSelector('main');
  // Widen the canvas so the toolbar controls gated on the pane width (the
  // hoist toggle among them) are rendered.
  const collapse = app.locator('[title="Collapse sidebar"]');
  if (await collapse.count()) {
    await collapse.first().click();
    await app.waitForTimeout(300);
  }
}

async function waitForCanvas(app: any) {
  await expect(app.locator('.react-flow').first()).toBeVisible({ timeout: 20_000 });
  await expect.poll(async () => {
    return app.locator('.react-flow').first().locator('.react-flow__edge').count();
  }, { timeout: 20_000 }).toBeGreaterThan(0);
  await expect(app.locator('.rm-splash')).toHaveCount(0, { timeout: 20_000 });
}

test('a collapsed group still receives the line of a relationship into it', async ({ app, server }) => {
  await openGraph(app, server);
  await waitForCanvas(app);

  // The relation into a folded group is drawn to that group (hoisted).
  // (React Flow renders each edge in two identical <g> layers here, so assert
  // on the first rather than an exact count.)
  const hoisted = app.locator(`.react-flow__edge[data-id="${HOISTED_EDGE_ID}"]`);
  await expect(hoisted.first()).toBeAttached({ timeout: 15_000 });

  // A hoisted edge is visually distinct: it is dashed.
  const dash = await hoisted.locator('.react-flow__edge-path').first().evaluate((el) => {
    return getComputedStyle(el).strokeDasharray;
  });
  expect(dash).not.toBe('none');
});

test('toggling hoist off drops the line into the collapsed group', async ({ app, server }) => {
  await openGraph(app, server);
  await waitForCanvas(app);

  const hoisted = app.locator(`.react-flow__edge[data-id="${HOISTED_EDGE_ID}"]`);
  await expect(hoisted.first()).toBeAttached({ timeout: 15_000 });

  await app.getByRole('button', { name: 'Toggle hoisted edges' }).first().click();

  // The setting persists with the other graph settings, so assert the toggle
  // actually flipped and the edge disappeared after the relayout.
  await expect(app.getByRole('button', { name: 'Toggle hoisted edges' }).first()).toHaveAttribute('aria-pressed', 'false');
  await expect(hoisted).toHaveCount(0, { timeout: 15_000 });
});
