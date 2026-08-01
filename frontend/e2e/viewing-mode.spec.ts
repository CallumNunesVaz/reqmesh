import { test, expect, signIn, setEditMode, DEMO_PROJECT } from './fixtures';

/**
 * Viewing mode must not permit any data mutation.
 *
 * `canPropose()` once ignored edit mode entirely, so risks and change requests
 * were fully editable — and deletable — while the header said VIEWING. A
 * per-page assertion would have missed it; the sweep is the point, because the
 * defect was in one shared permission helper and showed up on whichever pages
 * happened to use it.
 */
const ROUTES = [
  'requirements', 'requirements/AFRM0001', 'components', 'components/GDC',
  'specifications', 'verification', 'risks', 'change-requests', 'baselines',
  'traces', 'allocation', 'metrics',
];

// Controls whose label implies they change project data.
const MUTATING = /^(new|add|create|delete|remove|save|freeze|import|apply|link|unlink|edit|rename|approve|reject|submit)\b/i;

async function mutatingControls(page: import('@playwright/test').Page) {
  return page.evaluate((pattern) => {
    const rx = new RegExp(pattern, 'i');
    const main = document.querySelector('main') || document.body;
    const found: string[] = [];

    for (const b of Array.from(main.querySelectorAll('button, [role=button]'))) {
      if ((b as HTMLButtonElement).disabled) continue;
      const label = (b.textContent || '').trim() || b.getAttribute('title') || '';
      if (label && rx.test(label)) found.push(`button:${label.slice(0, 30)}`);
    }
    for (const i of Array.from(main.querySelectorAll('input:not([disabled])'))) {
      const el = i as HTMLInputElement;
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      const ph = (el.getAttribute('placeholder') || '').toLowerCase();
      // Search and filter inputs do not mutate anything.
      if (type === 'search' || ph.includes('search') || ph.includes('filter') || ph.includes('…')) continue;
      found.push(`input:${ph || type}`);
    }
    for (const s of Array.from(main.querySelectorAll('select:not([disabled])'))) {
      const opts = Array.from((s as HTMLSelectElement).options).map((o) => o.value.toLowerCase());
      // A filter dropdown leads with an empty/"all" option.
      if (opts[0] === '' || opts[0] === 'all') continue;
      found.push('select');
    }
    found.push(...Array.from(main.querySelectorAll('[contenteditable="true"]')).map(() => 'editor'));
    return found;
  }, MUTATING.source);
}

test.describe('viewing mode', () => {
  for (const route of ROUTES) {
    test(`offers nothing that mutates data on /${route}`, async ({ app, server }) => {
      await signIn(app);
      await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/${route}`);
      await app.waitForSelector('main', { timeout: 20_000 });

      // Wait on the mode badge rather than on the clock — `main` appearing does
      // not mean the header has settled.
      //
      // Matched as a control, not as text: `getByText('VIEWING')` is a
      // case-insensitive substring match, so while a loading splash was up it
      // also hit the tagline "Reviewing everything at once…" and failed on a
      // strict-mode violation. That is what the intermittent failures on the
      // slower routes actually were — not a timeout, which is what the previous
      // note here guessed.
      await expect(app.getByRole('button', { name: 'VIEWING' })).toBeVisible({ timeout: 20_000 });
      // Then let the page's own data land, so a control that renders late is
      // still counted.
      await app.waitForTimeout(1200);
      expect(await mutatingControls(app)).toEqual([]);
    });
  }

  test('editing mode restores the controls, so viewing is not simply over-locked', async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
    await app.waitForSelector('main');
    await setEditMode(app, true);
    await app.waitForTimeout(800);

    const controls = await mutatingControls(app);
    expect(controls.length).toBeGreaterThan(0);
  });
});
