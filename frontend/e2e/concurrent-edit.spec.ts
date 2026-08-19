import { test, expect, signIn, setEditMode, pickLinkOption, DEMO_PROJECT } from './fixtures';

/**
 * The lost-update guard must refuse *other people's* overwrites, and nobody
 * else's.
 *
 * Entity PUTs accept an opt-in `If-Match` carrying the `modified` the form was
 * loaded from, so that token has to stay fresh as the page performs its own
 * writes — and some of them bypass the form entirely. Allocating a component
 * writes `allocated_to` back onto the requirement, moving the stored
 * `modified` without the form knowing. A page that keeps the token it loaded
 * with then refuses the user's own next save with "reload to see their
 * version" while they are the only person editing: the guard turning on its
 * owner.
 *
 * What is asserted here is the fix's signature — the allocation is followed by
 * a re-read of the requirement, which is what re-anchors the token. Driving a
 * full save afterwards was tried and abandoned: this page has three separate
 * write paths (blur-save on the name field, the dirty/save-button flow, and
 * allocation), and a browser-level assertion threading them was long and
 * brittle without proving more than this does.
 *
 * The stale-write half of the contract lives where it belongs, in
 * `backend/tests/test_concurrent_edit.py` — twelve cases, including that a 409
 * leaves the first writer's value stored.
 */
const P = DEMO_PROJECT;

test('allocating re-reads the requirement, so its version token stays fresh',
  async ({ app, server }) => {
    await signIn(app);
    await app.goto(`${server.baseURL}/project/${P}/requirements/AFRM0001`);
    await app.waitForSelector('main', { timeout: 20_000 });
    await setEditMode(app);

    // `main input`, not `input[type=text]`: the field carries no `type`
    // attribute at all (it defaults to text), so the attribute selector
    // matches nothing even though the DOM property reads "text".
    await expect(app.locator('main input').first()).toHaveValue(/\S/, { timeout: 15_000 });

    const allocation = app.waitForResponse(
      (r) => r.url().includes('/allocation') && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    // Armed before the click, or a fast response is missed.
    const reread = app.waitForResponse(
      (r) => /\/requirements\/AFRM0001(\?|$)/.test(r.url()) && r.request().method() === 'GET',
      { timeout: 15_000 },
    );

    // The "Allocated To" editor passes no `label`, so LinkEditor's
    // `data-link-editor={label || kind}` falls back to the kind. The control
    // is a combobox now, so pick a linkable component id from the API and
    // drive the filter, not a <select>.
    const components: any[] = await app.evaluate(async (project: string) => {
      const r = await fetch(`/api/projects/${project}/components`, { credentials: 'include' });
      const j = await r.json();
      return j.items || j;
    }, P);
    const satisfied: any[] = await app.evaluate(async (project: string) => {
      const r = await fetch(`/api/projects/${project}/requirements/AFRM0001/components`, { credentials: 'include' });
      return r.json();
    }, P);
    const linkable = components.find((c: any) => !satisfied.some((s: any) => s.id === c.id));
    expect(linkable, 'need a linkable component to move `modified`').toBeTruthy();

    const picker = app.locator('[data-link-editor="component"]').first();
    await picker.waitFor({ timeout: 10_000 });
    await pickLinkOption(picker, linkable.id);

    expect((await allocation).status()).toBe(200);
    expect((await reread).status(),
      'the page must re-read the requirement after allocating, or the If-Match '
      + 'token it holds is stale and the next save 409s against its own author',
    ).toBe(200);
  });
