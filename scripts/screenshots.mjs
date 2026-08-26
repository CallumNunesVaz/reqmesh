// Regenerate the README screenshots in docs/screenshots/.
//
//   node scripts/screenshots.mjs [name ...]      (no args = all)
//
// Runs against a throwaway sandbox seeded with the Cessna demo (see
// .claude/skills/run-app/driver.mjs), so it never touches real projects or
// accounts and the output is reproducible.
//
// Each shot is framed on what its README caption actually describes rather than
// on the whole window: a caption about one card gets that card, a caption about
// the workspace gets the workspace. `target` is either 'viewport', a CSS
// selector, or { sel, hasText } to disambiguate one card among many.
//
// The canvas pane is closed for content-focused pages. It is a sibling of
// <main>, so leaving it open squeezes the page into ~62% of the width and the
// wide matrices in particular end up scrolled rather than shown.
import { launch, helpers, close, sleep } from '../.claude/skills/run-app/driver.mjs'
import * as path from 'node:path'
import * as fs from 'node:fs'

const OUT = path.resolve('docs/screenshots')
const PROJECT = 'cessna-172'
const p = (route) => `/project/${PROJECT}${route}`

/** `wait` is extra settle time for pages that animate or lay out (the canvas). */
const SHOTS = [
  // Hero: the caption names three panes, so this one is legitimately the
  // whole workspace.
  { name: 'requirements-inspector', route: p('/requirements/ACFT0000'), target: 'viewport', canvas: true, wait: 3500 },
  { name: 'requirements',           route: p('/requirements'),          target: 'viewport', canvas: true, wait: 3000 },

  // The canvas itself, without the surrounding chrome.
  { name: 'graph',                  route: p('/graph'),                 target: '.react-flow', canvas: true, wait: 4000 },

  // One card, because the caption is about one card.
  { name: 'requirement-detail',     route: p('/requirements/ACFT0000'),
    target: { sel: '.card', hasText: 'Parameters & Constraints' }, canvas: false, wait: 2500 },
  // 'Git Integration', not the 'Version Control' card below it: the caption is
  // about remote configuration, and Version Control shows only the empty
  // "not a git repository" state on a freshly seeded demo project.
  { name: 'git-panel',              route: p('/settings'),
    target: { sel: '.card', hasText: 'Git Integration' }, canvas: false, wait: 2500 },

  // Page content, full width.
  { name: 'traces',          route: p('/traces'),          target: 'main', canvas: false, wait: 2500 },
  { name: 'verification',    route: p('/verification'),    target: 'main', canvas: false, wait: 2000 },
  { name: 'metrics',         route: p('/metrics'),         target: 'main', canvas: false, wait: 3500 },
  { name: 'allocation',      route: p('/allocation'),      target: 'main', canvas: false, wait: 2500 },
  { name: 'decisions',       route: p('/decisions'),       target: 'main', canvas: false, wait: 2000 },
  { name: 'definitions',     route: p('/definitions'),     target: 'main', canvas: false, wait: 2000 },
  { name: 'risks',           route: p('/risks'),           target: 'main', canvas: false, wait: 2000 },
  { name: 'baselines',       route: p('/baselines'),       target: 'main', canvas: false, wait: 2000 },
  { name: 'change-requests', route: p('/change-requests'), target: 'main', canvas: false, wait: 2000 },
  // The sandbox seeds only `admin`, and a one-row table does not show the
  // roles/status/actions the caption promises. These are demo accounts in a
  // throwaway instance, created through the real API so the row rendering is
  // genuine rather than mocked.
  { name: 'users',           route: '/users',              target: 'main', canvas: false, wait: 2500,
    setup: () => seedUsers() },
]

const only = process.argv.slice(2)
const wanted = only.length ? SHOTS.filter((s) => only.includes(s.name)) : SHOTS

const { page, handle } = await launch({ mode: 'web' })
const h = helpers(page)

/** The canvas pane is open by default on most project pages. */
async function setCanvas(open) {
  const state = await page.evaluate(() => !!document.querySelector('.react-flow'))
  if (state === open) return
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.textContent || '').trim() === 'Canvas')
    btn?.click()
  })
  await sleep(1200)
}

async function seedUsers() {
  const people = [
    { username: 'j.okafor',  full_name: 'Jomi Okafor',    email: 'j.okafor@acme-aero.com',  role: 'maintainer' },
    { username: 'r.lindqvist', full_name: 'Rita Lindqvist', email: 'r.lindqvist@acme-aero.com', role: 'contributor' },
    { username: 'p.mehta',   full_name: 'Priya Mehta',    email: 'p.mehta@acme-aero.com',   role: 'contributor' },
    { username: 's.novak',   full_name: 'Sam Novak',      email: 's.novak@acme-aero.com',   role: 'guest' },
  ]
  await page.evaluate(async (list) => {
    // Auth here is cookie-based and mutations are CSRF-protected, so a bare
    // fetch gets 403. `whoami` is a GET (no CSRF needed) and hands back the
    // token the app's own client sends as X-CSRF-Token.
    const me = await fetch('/api/auth/whoami', { credentials: 'include' }).then((r) => r.json())
    const headers = {
      'Content-Type': 'application/json',
      ...(me?.csrf_token ? { 'X-CSRF-Token': me.csrf_token } : {}),
    }
    for (const p of list) {
      await fetch('/api/auth/users', {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify({ ...p, password: 'Demo-Passw0rd!' }),
      }).catch(() => {})
    }
    // One disabled account so the Status column shows more than "Active".
    await fetch('/api/auth/users/s.novak/disable', {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify({ disabled: true }),   // the body is required, not optional
    }).catch(() => {})
  }, people)
}

try {
  // Before navigating, not just before the shot: GraphPane's chrome is gated on
  // container breakpoints, so at a small viewport the canvas never renders.
  await page.setViewportSize({ width: 1920, height: 1400 })
  await h.login()
  await sleep(1200)

  fs.mkdirSync(OUT, { recursive: true })
  for (const shot of wanted) {
    if (shot.setup) { await shot.setup(); }
    await h.goto(shot.route)
    await sleep(shot.wait)
    await setCanvas(shot.canvas)
    await sleep(600)

    const file = path.join(OUT, `${shot.name}.png`)
    if (shot.target === 'viewport') {
      await page.screenshot({ path: file })
    } else if (shot.target === 'main') {
      // <main> is viewport-height, so a short page would be captured with a
      // screenful of dead space under it. Clip to where the content actually
      // ends, never past the fold.
      const clip = await page.evaluate(() => {
        const m = document.querySelector('main')
        const r = m.getBoundingClientRect()
        let bottom = r.top
        for (const child of m.children) {
          const b = child.getBoundingClientRect()
          if (b.height > 0) bottom = Math.max(bottom, b.bottom)
        }
        return { x: r.x, y: r.y, width: r.width, height: Math.max(120, Math.min(bottom, r.bottom) - r.top) }
      })
      await page.screenshot({ path: file, clip })
    } else {
      const loc = typeof shot.target === 'string'
        ? page.locator(shot.target).first()
        : page.locator(shot.target.sel, { hasText: shot.target.hasText }).first()
      if (!(await loc.count())) { console.log(`MISSING  ${shot.name}: ${JSON.stringify(shot.target)}`); continue }
      await loc.screenshot({ path: file })
    }
    const kb = Math.round(fs.statSync(file).size / 1024)
    console.log(`ok  ${shot.name.padEnd(24)} ${String(kb).padStart(5)} KB`)
  }
} catch (e) {
  console.log('FLOW ERROR:', e.message)
} finally {
  await close(handle)
}
