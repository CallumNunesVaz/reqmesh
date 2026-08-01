import { test, expect, signIn, DEMO_PROJECT } from './fixtures';

/**
 * reqmesh is deployed to air-gapped networks. A resource fetched from a CDN
 * does not error there — it silently does nothing, and the page renders in
 * fallback fonts (or without a feature) until somebody opens a console on the
 * deployed box. That is exactly how a Google Fonts <link> reached production.
 *
 * `npm run build` already fails on remote references in the output; this
 * catches the runtime equivalent, including anything injected by a dependency.
 */
test('the app makes no requests off its own origin', async ({ app, server }) => {
  const external: string[] = [];
  app.on('request', (r) => {
    const host = new URL(r.url()).host;
    if (host && host !== new URL(server.baseURL).host) external.push(host);
  });

  await signIn(app);
  await app.goto(`${server.baseURL}/project/${DEMO_PROJECT}/requirements`);
  await app.waitForSelector('main');
  await app.waitForTimeout(2500);

  expect([...new Set(external)]).toEqual([]);
});

test('the bundled typefaces actually load', async ({ app }) => {
  await app.waitForTimeout(1500);
  const faces = await app.evaluate(async () => {
    await (document as any).fonts.ready;
    return [...new Set(Array.from((document as any).fonts)
      .filter((f: any) => f.status === 'loaded')
      .map((f: any) => f.family))];
  });
  expect(faces).toContain('Inter');
  expect(faces).toContain('JetBrains Mono');
});
