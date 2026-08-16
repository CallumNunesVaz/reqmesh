import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

const P = DEMO_PROJECT;

/**
 * Column alignment on the requirements tree.
 *
 * The tree indent used to live on the row itself, so every column after the
 * name — description, priority chip, status, the Σ verdict — started further
 * right the deeper the row sat, and the description was `flex-1` so its left
 * edge also floated with the length of the name beside it. Nothing below the
 * name lined up. The indent now sits on an inner left cell and the columns to
 * its right are fixed widths, so they hold one column at every depth.
 */

async function open(app: any, server: any) {
  await signIn(app);
  await app.goto(`${server.baseURL}/project/${P}/requirements`);
  await app.waitForSelector('[role=treeitem]');
}

/** Left edge of each direct child of a row — one number per column. */
async function columnEdges(app: any, id: string): Promise<number[]> {
  return app.evaluate((rowId: string) => {
    const row = document.getElementById(`entity-${rowId}`);
    if (!row) throw new Error(`no row ${rowId}`);
    return [...row.children].map((c) => Math.round(c.getBoundingClientRect().left));
  }, id);
}

test('the columns after the name line up across tree depths', async ({ app, server }) => {
  await open(app, server);

  // ACFT0000 is the root, AFRM0000 its child, AFRM0001 a grandchild — three
  // different indents, and each carries a different set of optional badges.
  const root = await columnEdges(app, 'ACFT0000');
  const child = await columnEdges(app, 'AFRM0000');
  const grandchild = await columnEdges(app, 'AFRM0001');

  expect(root.length).toBeGreaterThan(1);
  expect(child).toEqual(root);
  expect(grandchild).toEqual(root);
});

test('a row with no description does not collapse the description column', async ({ app, server }) => {
  await open(app, server);

  // OVERVIEW01 is a plain overview node; compare its columns to a row that
  // carries a long description.
  const withText = await columnEdges(app, 'ACFT0000');
  const overview = await columnEdges(app, 'OVERVIEW01');
  expect(overview).toEqual(withText);
});

test('the list uses the full width of its pane', async ({ app, server }) => {
  // Wide enough that the pane exceeds the 56rem cap the page used to carry —
  // at the default viewport the pane is narrower than the cap, so the gutters
  // it caused would not show.
  await app.setViewportSize({ width: 2600, height: 1200 });
  await open(app, server);

  const { rowWidth, paneWidth } = await app.evaluate(() => {
    const row = document.querySelector('[role=treeitem]') as HTMLElement;
    const pane = row.closest('main') ?? document.body;
    return {
      rowWidth: row.getBoundingClientRect().width,
      paneWidth: pane.getBoundingClientRect().width,
    };
  });

  // Page padding only — no centred max-width cap leaving gutters.
  expect(rowWidth).toBeGreaterThan(paneWidth - 120);
});
