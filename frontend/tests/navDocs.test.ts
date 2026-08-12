import { describe, it, expect } from 'vitest';
import { navGroups } from '../src/components/RequirementNav';
import { SECTION_TITLES, ENTITY_META } from '../src/components/entities';

/**
 * The UI counterpart to `backend/tests/test_docs_currency.py`.
 *
 * That test walks the live FastAPI route table and fails if an `/api` path is
 * missing from README.md, which is why the API section has stayed current. The
 * navigation had no such gate: a page could exist, be routed, sit in the
 * sidebar and appear nowhere in the docs — which is exactly how decisions,
 * definitions and analysis cases ended up with full CRUD and no mention.
 *
 * It lives here rather than in pytest because `navGroups` is a TypeScript
 * array. Reading it from Python would mean regexing a .tsx file, and a gate
 * that reformatting can defeat is not a gate.
 */

// Node's built-ins are available under vitest but the project tsconfig sets
// `"types": []` on purpose — this is a browser app, and pulling in Node globals
// would let server-only APIs type-check inside `src/`. Declaring just the two
// functions needed keeps that boundary intact while leaving the rest of this
// file type-checked, which a file-level @ts-nocheck would not: the `navGroups`
// call below is the part that must fail loudly if the nav's shape changes.
declare function require(id: string): { readFileSync(p: string, enc: string): string };
const { readFileSync } = require('fs');

const readme: string = readFileSync(new URL('../../README.md', import.meta.url).pathname, 'utf-8');

describe('nav docs gate', () => {
  it('every sidebar nav label is documented in README.md', () => {
    const labels = navGroups('demo').flat().map((item) => item.label);
    const readmeLower = readme.toLowerCase();

    // Every missing label, not just the first — a gate that surfaces one
    // problem per run is a gate people stop running.
    //
    // Known limitation: this is a substring match, so a label can be satisfied
    // incidentally. Adding the Analysis page passed on the strength of the
    // pre-existing "Analysis & Validation" heading alone. The gate reliably
    // catches a page documented *nowhere*, which is the case it exists for
    // (decisions, definitions and analysis cases each shipped full CRUD with no
    // mention anywhere); it does not prove the mention is about the page.
    // Tightening it to require a heading was considered and rejected: several
    // legitimate entries are documented in prose under a differently-worded
    // heading, so that rule would fail honest documentation.
    const missing = labels.filter((label) => !readmeLower.includes(label.toLowerCase()));

    if (missing.length > 0) {
      expect.fail(
        'The following sidebar navigation labels are missing from README.md:\n'
        + missing.map((l) => `  - ${l}`).join('\n')
        + '\nAdd documentation for each one — a sentence or two saying what the page is for.',
      );
    }
  });

  it('reads a non-empty README and a non-empty nav, so a silent pass is impossible', () => {
    // Without this, an unreadable README or an empty nav array would make the
    // gate above pass vacuously — the failure mode that makes a green check
    // worse than no check at all.
    expect(readme.length).toBeGreaterThan(1000);
    expect(navGroups('demo').flat().length).toBeGreaterThan(5);
  });
});

describe('nav label / page heading share one source', () => {
  const navByRoute = Object.fromEntries(
    navGroups('demo').flat().map((item) => [item.to.split('/').pop() as string, item.label]),
  );

  it('verification and analysis nav labels are the ENTITY_META plural — the same source the page headings read', () => {
    // The pages render these titles from SECTION_TITLES too, so asserting the
    // nav uses SECTION_TITLES (not a hardcoded label) holds both to one source.
    expect(navByRoute.verification).toBe(SECTION_TITLES.verification);
    expect(navByRoute.analysis).toBe(SECTION_TITLES.analysis);
    // And the source follows the canonical per-kind name, so a drift in
    // ENTITY_META.label surfaces here rather than in a mismatched heading.
    expect(SECTION_TITLES.verification).toBe(`${ENTITY_META.verification.label}s`);
    expect(SECTION_TITLES.analysis).toBe(`${ENTITY_META.analysis.label}s`);
  });

  it('the trace matrix nav label matches its page heading', () => {
    // Not an entity kind, so there is no ENTITY_META label to derive from — but
    // the nav said "Trace Matrix" while the page said "Traceability Matrix",
    // which is the same drift, so it is held to one source too.
    expect(navByRoute.traces).toBe(SECTION_TITLES.traces);
  });
});
