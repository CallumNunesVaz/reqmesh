#!/usr/bin/env node
/**
 * Fail the build if the bundle loads anything over the network at runtime.
 *
 * reqmesh is deployed to air-gapped and CSP-restricted networks. A stylesheet
 * or script pulled from a CDN does not error there — it silently does nothing,
 * so the app renders with fallback fonts (or a missing feature) and nobody
 * finds out until someone looks at a browser console on the deployed box.
 * That is exactly how the Google Fonts <link> survived to production.
 *
 * Only *resource loads* count. Links a human clicks, and URLs inside strings
 * (documentation, error messages, library metadata) are fine.
 */
import { readdirSync, readFileSync, statSync } from 'fs';
import { join, extname } from 'path';

const DIST = new URL('../dist/', import.meta.url).pathname;

// href/src on a loading element, and CSS url(). Not <a href>, which is a link
// the user chooses to follow.
const PATTERNS = [
  { re: /<link\b[^>]*\bhref\s*=\s*["'](https?:)?\/\/[^"']+/gi, what: '<link> to a remote host' },
  { re: /<script\b[^>]*\bsrc\s*=\s*["'](https?:)?\/\/[^"']+/gi, what: '<script> from a remote host' },
  { re: /<img\b[^>]*\bsrc\s*=\s*["'](https?:)?\/\/[^"']+/gi, what: '<img> from a remote host' },
  { re: /url\(\s*["']?(https?:)?\/\/[^)"']+/gi, what: 'CSS url() to a remote host' },
  { re: /@import\s+(url\()?\s*["'](https?:)?\/\/[^"']+/gi, what: '@import from a remote host' },
];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (['.html', '.css', '.js'].includes(extname(p))) out.push(p);
  }
  return out;
}

// Hosts that cannot leave the machine. An air-gapped deployment reaches these
// exactly as well as a connected one, so they are not what this check is for.
const LOCAL_HOST = /\/\/(localhost|127\.0\.0\.1|\[::1\])([:/"')]|$)/i;

let failures = 0;
for (const file of walk(DIST)) {
  const text = readFileSync(file, 'utf8');
  for (const { re, what } of PATTERNS) {
    for (const m of text.matchAll(re)) {
      // Data URIs and protocol-relative paths into our own origin are fine.
      if (/^(<[a-z]+\b[^>]*["'])?(data:|blob:)/i.test(m[0])) continue;
      // Not a remote host at all — an air-gapped box reaches it fine.
      //
      // This is also what excuses the JavaScript `URL(...)` constructor, which
      // the case-insensitive CSS `url()` pattern matches too: react-router v7
      // builds `new URL(href, "http://localhost")` as a sentinel base for
      // resolving relative hrefs. Skipping on the *host* rather than on the
      // `URL(` spelling matters — `URL(https://cdn…)` is valid, case-
      // insensitive CSS that really would fetch, and a spelling-based skip
      // silently stopped catching it.
      if (LOCAL_HOST.test(m[0])) continue;
      console.error(`✗ ${file.replace(DIST, 'dist/')}: ${what}`);
      console.error(`  ${m[0].slice(0, 140)}`);
      failures++;
    }
  }
}

if (failures) {
  console.error(
    `\n${failures} remote resource reference(s) in the build.\n` +
    `Bundle the asset instead — see frontend/src/styles/fonts.css for how the\n` +
    `fonts were brought in-tree. An air-gapped deployment cannot fetch these.`,
  );
  process.exit(1);
}
console.log('✓ bundle is self-contained (no remote resource loads)');
