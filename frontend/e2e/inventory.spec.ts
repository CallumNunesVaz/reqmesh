import { test, expect, signIn } from './fixtures';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { REQUIREMENT_TYPES } from '../src/lib/requirementTypes';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const APP_TSX = resolve(E2E_DIR, '../src/App.tsx');

/**
 * Coverage guards.
 *
 * A suite that only asserts what someone remembered to write rots quietly: the
 * page count grows, the spec count does not, and nothing fails. This is the
 * same idea as the backend's route-collection floor, which was added after a
 * dependency upgrade silently reduced the permission tests from 190 cases to
 * zero while the run still reported green.
 */

function routePaths(): string[] {
  const src = readFileSync(APP_TSX, 'utf8');
  return [...src.matchAll(/<Route\s+path="([^"]+)"/g)]
    .map((m) => m[1])
    .filter((p) => p !== '*');
}

function specText(): string {
  return readdirSync(E2E_DIR)
    .filter((f) => f.endsWith('.spec.ts'))
    .map((f) => readFileSync(join(E2E_DIR, f), 'utf8'))
    .join('\n');
}

test('every route in App.tsx is exercised by some spec', () => {
  const specs = specText();
  const uncovered = routePaths().filter((route) => {
    // Match on the distinctive final segment: specs navigate to concrete URLs
    // (/project/cessna-172/risks), not to the parameterised pattern.
    const segments = route.split('/').filter((s) => s && !s.startsWith(':'));
    const leaf = segments[segments.length - 1];
    if (!leaf) return false;                    // the bare "/" route
    // Specs name a route either as a URL fragment (`/risks`) or as a bare
    // segment in a list of routes to sweep ('risks'), so match the segment as
    // a token rather than requiring the slash.
    return !new RegExp(`[/'"\`]${leaf}\\b`).test(specs);
  });

  expect(uncovered, `routes with no spec — add one or extend an existing file:\n  ${uncovered.join('\n  ')}`)
    .toEqual([]);
});

test('the spec suite has not silently shrunk', () => {
  const files = readdirSync(E2E_DIR).filter((f) => f.endsWith('.spec.ts'));
  expect(files.length).toBeGreaterThanOrEqual(5);
});

test('the UI offers exactly the requirement types the API accepts', async ({ app }) => {
  // The list was previously copied into six files and had drifted: the
  // allocation matrix filter offered 5 of the 16, so filtering there silently
  // hid most of the register. One shared table fixes today's drift; this stops
  // tomorrow's, by failing when the enum and the UI disagree in either
  // direction — a type added to the backend and forgotten in the UI is just as
  // broken as the reverse.
  await signIn(app);
  const schema = await app.evaluate(async () => {
    const r = await fetch('/openapi.json', { credentials: 'include' });
    return r.json();
  });
  const schemas = schema.components?.schemas ?? {};
  const enumDef = schemas.RequirementType;
  expect(enumDef, 'RequirementType is no longer in the OpenAPI schema').toBeTruthy();

  const apiTypes: string[] = enumDef.enum;
  expect(apiTypes.length).toBeGreaterThan(10);
  expect([...apiTypes].sort()).toEqual([...REQUIREMENT_TYPES].sort());
  // Order matters too: it is the order every dropdown renders in, and the
  // backend enum is the declared reference for it.
  expect(REQUIREMENT_TYPES).toEqual(apiTypes);
});

test('every documented API path is reachable through the running app', async ({ app }) => {
  await signIn(app);
  const schema = await app.evaluate(async () => {
    const r = await fetch('/openapi.json', { credentials: 'include' });
    return r.json();
  });
  const paths = Object.keys(schema.paths || {});
  // The floor is the guard: if a router stops being registered, the schema
  // shrinks and this fails rather than the suite quietly testing less.
  expect(paths.length).toBeGreaterThan(100);
  expect(paths.some((p) => p.startsWith('/api/projects'))).toBe(true);
});
