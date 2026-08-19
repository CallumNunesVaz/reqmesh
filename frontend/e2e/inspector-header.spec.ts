import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * The requirement inspector header bunched its buttons onto one row, where the
 * flex-1 identity block squeezed them until they overlapped at the inspector's
 * 300px floor. The header is now two rows: identity (back + id) above a toolbar
 * that wraps. The assertions here are geometric — overlap, overflow and row
 * count — because a class-name check would pass regardless of the actual
 * layout, and an accessible-name census so a button dropped during the reflow
 * fails the test.
 *
 * The requirement is picked to render the full toolbar: children (cascade),
 * a multi-clause description (split) and no review snapshot (mark reviewed).
 * Editing the priority dirties the form, which is what turns on Save/Discard.
 */
const P = DEMO_PROJECT;
const REQ = 'ELEC0000';

interface Box {
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

function intersects(a: Box, b: Box): boolean {
  const ix = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const iy = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return ix > 0 && iy > 0;
}

/** Every button in the header, in the identity row and toolbar, with its box
 *  and a human-readable label for failure messages. */
async function headerButtonBoxes(app: any): Promise<Box[]> {
  const identity = app.locator('[data-testid="requirement-header-identity"]');
  const toolbar = app.locator('[data-testid="requirement-header-toolbar"]');

  const boxes: Box[] = [];
  const push = async (loc: any, name: string) => {
    const b = await loc.boundingBox();
    if (b) boxes.push({ name, ...b });
  };

  await push(identity.locator('button').first(), 'back');
  await push(identity.locator('button[title^="Copy link"]'), 'copy link');
  await push(identity.locator('button[title^="Rename"]'), 'rename');

  const buttons = toolbar.locator('button');
  const count = await buttons.count();
  for (let i = 0; i < count; i++) {
    const loc = buttons.nth(i);
    const name = await loc.evaluate(
      (el) => el.getAttribute('title') || el.textContent?.trim() || `toolbar button #${i}`,
    );
    await push(loc, name as string);
  }
  return boxes;
}

test('the inspector header reflows onto two rows without overlapping at 300px', async ({ app, server }) => {
  await app.setViewportSize({ width: 1600, height: 1000 });
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements/${REQ}`);
  await app.waitForSelector('main');
  await setEditMode(app);

  await expect(app.getByRole('heading', { name: REQ, exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(app.getByRole('button', { name: 'Show in graph' })).toBeVisible();

  // Dirty the form so Save and Discard join the toolbar — the widest toolbar
  // the page ever draws.
  await app.getByLabel('Priority').selectOption('medium');
  await expect(app.getByRole('button', { name: 'Save changes' })).toBeVisible();

  // Drag the canvas/inspector divider to the right edge: the clamp in Layout.tsx
  // stops the inspector at CONTEXT_MIN (300px), not at whatever the drag asks.
  const divider = app.locator('[title="Drag to resize the canvas"]');
  const dbox = await divider.boundingBox();
  expect(dbox).toBeTruthy();
  const y = dbox!.y + dbox!.height / 2;
  await app.mouse.move(dbox!.x + dbox!.width / 2, y);
  await app.mouse.down();
  await app.mouse.move(app.viewportSize().width, y, { steps: 20 });
  await app.mouse.up();
  await app.waitForTimeout(600);
  await app.evaluate(() => document.fonts.ready);

  // The full set of toolbar buttons survives the reflow, each by accessible name.
  const toolbar = app.locator('[data-testid="requirement-header-toolbar"]');
  const expected = [
    'Show in graph',
    'Show derivation',
    'Mark Reviewed',
    'Save changes',
    'Discard changes',
    /Cascade a copy into \d+ child group/,
    'Add child requirement',
    'Duplicate requirement',
    'Split into child requirements',
    'Delete',
    'Request a Change',
  ];
  for (const name of expected) {
    await expect(toolbar.getByRole('button', { name })).toHaveCount(1);
  }
  await expect(toolbar.locator('button')).toHaveCount(expected.length);
  await expect(app.locator('[data-testid="requirement-header-identity"] button')).toHaveCount(3);

  // No horizontal overflow.
  const header = app.locator('[data-testid="requirement-header"]');
  const widths = await header.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 1);

  // Geometry: no two buttons overlap, and the toolbar occupies at least two rows.
  const boxes = await headerButtonBoxes(app);
  expect(boxes.length).toBeGreaterThanOrEqual(expected.length + 2);
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      expect(intersects(boxes[i], boxes[j]), `${boxes[i].name} overlaps ${boxes[j].name}`).toBe(false);
    }
  }

  const yBands = new Set(boxes.map((b) => Math.round(b.y)));
  expect(yBands.size).toBeGreaterThanOrEqual(2);
});
