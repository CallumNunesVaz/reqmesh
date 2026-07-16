// Playwright driver for the reqmesh app.
//
// reqmesh ships in two shapes and this drives both:
//   mode: 'web'      — spawns the FastAPI backend (serving the built SPA) and
//                      drives it in Chromium. The primary deployment.
//   mode: 'desktop'  — launches the Electron shell from desktop/, which boots
//                      its own backend. Use when the change touches the shell.
//
// Two ways to use it:
//   1. Import the helpers into a scripted flow (recommended):
//        import { launch, helpers, close } from './driver.mjs'
//        const { page, handle } = await launch({ mode: 'web' })
//        const h = helpers(page)
//        await h.login()
//   2. Run directly for a stdin REPL: node driver.mjs [web|desktop]
//        commands: ss [name] | goto <path> | click <sel> | click-text <t> |
//                  click-title <t> | login [user] [pass] | edit | drag <a> <b> |
//                  type <text> | press <key> | eval <js> | text [sel] | quit
//
// See SKILL.md in this directory for the gotchas — read it first.
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as net from 'node:net'
import * as http from 'node:http'
import * as readline from 'node:readline'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const BACKEND_DIR = path.join(REPO_ROOT, 'backend')
const DESKTOP_DIR = path.join(REPO_ROOT, 'desktop')
const FRONTEND_DIST = path.join(REPO_ROOT, 'frontend', 'dist')
const HOST = '127.0.0.1'

// playwright-core is installed into desktop/ (--no-save) so the repo's
// package.json files stay untouched — see SKILL.md prerequisites.
const require = createRequire(path.join(DESKTOP_DIR, 'package.json'))
const { chromium, _electron: electron } = require('playwright-core')

const SHOT_DIR = process.env.SCREENSHOT_DIR || '/tmp/rm-shots'
const SANDBOX = process.env.RM_TEST_HOME || '/tmp/rm-uitest-home'

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/**
 * Environment that redirects every write reqmesh makes into a throwaway
 * sandbox. HOME is what moves ~/.reqmesh/{users.yaml,secret} — the real
 * accounts and signing secret are never touched. Git auto-commit is off so
 * driving the UI cannot author commits.
 */
function sandboxEnv(seed) {
  return {
    ...process.env,
    HOME: SANDBOX,
    RT_DATA_ROOT: path.join(SANDBOX, 'projects'),
    RT_GIT_AUTOCOMMIT: 'false',
    RT_SEED_DEMO: seed ? 'true' : 'false',
    RT_ADMIN_PASSWORD: 'admin',
    DISPLAY: process.env.DISPLAY || ':1',
  }
}

/** Resolve a free TCP port on loopback. */
function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.on('error', reject)
    srv.listen(0, HOST, () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
  })
}

/** Poll /health until the backend answers or we give up. */
async function waitForBackend(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const ok = await new Promise((resolve) => {
      const req = http.get(`http://${HOST}:${port}/health`, (res) => {
        res.resume()
        resolve(res.statusCode === 200)
      })
      req.on('error', () => resolve(false))
      req.setTimeout(2000, () => { req.destroy(); resolve(false) })
    })
    if (ok) return
    if (Date.now() > deadline) throw new Error('backend did not become healthy in time')
    await sleep(400)
  }
}

/**
 * Kill the app if the flow dies before reaching close() — an uncaught error
 * would otherwise strand a backend (and an Electron window) on the user's
 * machine. The 'exit' hook must stay synchronous, so these are hard kills.
 */
function killOnExit(kill) {
  const once = () => { try { kill() } catch { /* already gone */ } }
  process.once('exit', once)
  for (const sig of ['SIGINT', 'SIGTERM']) {
    process.once(sig, () => { once(); process.exit(1) })
  }
  return once
}

/** Every delete in the UI is a window.confirm — Playwright auto-DISMISSES
 *  dialogs unless something is listening, which silently turns deletes into
 *  no-ops. Accept by default; flows that need a cancel can override. */
function autoAcceptDialogs(page) {
  page.on('dialog', (d) => d.accept().catch(() => {}))
}

/**
 * Launch the app against a sandboxed data root.
 * @returns {{ page, handle }} — pass `handle` to close().
 */
export async function launch(options = {}) {
  const { mode = 'web', seed = true, headless = false, fresh = true, theme = 'dark' } = options
  fs.mkdirSync(SHOT_DIR, { recursive: true })
  if (fresh) fs.rmSync(SANDBOX, { recursive: true, force: true })
  fs.mkdirSync(SANDBOX, { recursive: true })

  if (!fs.existsSync(path.join(FRONTEND_DIST, 'index.html'))) {
    throw new Error(`no build at ${FRONTEND_DIST} — run: cd frontend && npm run build`)
  }

  return mode === 'desktop'
    ? launchDesktop({ seed, theme })
    : launchWeb({ seed, headless, theme })
}

async function launchWeb({ seed, headless, theme }) {
  const python = fs.existsSync(path.join(BACKEND_DIR, '.venv/bin/python'))
    ? path.join(BACKEND_DIR, '.venv/bin/python')
    : 'python3'
  const port = await freePort()
  const backend = spawn(
    python,
    ['-m', 'uvicorn', 'app.main:app', '--host', HOST, '--port', String(port)],
    { cwd: BACKEND_DIR, env: { ...sandboxEnv(seed), RT_STATIC_DIR: FRONTEND_DIST }, stdio: 'ignore' }
  )
  killOnExit(() => backend.kill('SIGKILL'))
  try {
    await waitForBackend(port)
  } catch (err) {
    backend.kill('SIGKILL')
    throw err
  }
  const browser = await chromium.launch({ headless, args: ['--no-sandbox'] })
  // reqmesh follows the OS colour scheme, and Chromium reports "light" by
  // default — which is NOT how most users see the app. Drive dark unless a
  // flow explicitly asks otherwise.
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1000 },
    colorScheme: theme,
  })
  autoAcceptDialogs(page)
  await page.goto(`http://${HOST}:${port}/`)
  await page.waitForSelector('header', { timeout: 15000 })
  await sleep(800)
  console.log(`launched web on :${port} (data root ${SANDBOX})`)
  return { page, handle: { mode: 'web', browser, backend, port } }
}

async function launchDesktop({ seed, theme }) {
  const app = await electron.launch({
    executablePath: path.join(DESKTOP_DIR, 'node_modules/electron/dist/electron'),
    args: ['--no-sandbox', path.join(DESKTOP_DIR, 'main.js')],
    cwd: DESKTOP_DIR,
    env: sandboxEnv(seed),
    timeout: 45000, // the shell boots a backend before the window appears
  })
  // The shell reaps its own backend on before-quit, so killing it is enough.
  killOnExit(() => app.process().kill('SIGKILL'))
  const page = await app.firstWindow()
  autoAcceptDialogs(page)
  await page.waitForSelector('header', { timeout: 20000 })
  // Electron has no colorScheme knob, but the app prefers a stored theme over
  // the OS setting — so persist one and reload into it.
  if (theme) {
    await page.evaluate((t) => localStorage.setItem('rt-theme', t), theme)
    await page.reload()
    await page.waitForSelector('header', { timeout: 20000 })
  }
  await sleep(1200)
  console.log(`launched desktop (data root ${SANDBOX})`)
  return { page, handle: { mode: 'desktop', app } }
}

/**
 * ALWAYS close through this. In web mode the backend is our child process and
 * outlives the browser otherwise; in desktop mode the Electron shell reaps its
 * own backend on before-quit.
 */
export async function close(handle) {
  if (!handle) return
  if (handle.mode === 'desktop') {
    await handle.app.close().catch(() => {})
    return
  }
  await handle.browser.close().catch(() => {})
  handle.backend.kill('SIGTERM')
  // Escalate if uvicorn ignores the polite ask.
  const gone = await Promise.race([
    new Promise((r) => handle.backend.once('exit', () => r(true))),
    sleep(4000).then(() => false),
  ])
  if (!gone) handle.backend.kill('SIGKILL')
}

/** Interaction helpers bound to a page. All log what they did. */
export function helpers(page) {
  let shot = 0

  const ss = async (name) => {
    shot += 1
    const f = path.join(SHOT_DIR, `${String(shot).padStart(2, '0')}-${name || 'shot'}.png`)
    await page.screenshot({ path: f })
    console.log('SHOT', f)
    return f
  }

  /** Screenshot one element — for judging a component's look without hunting
   *  for it in a full-page frame. */
  const ssOf = async (sel, name) => {
    shot += 1
    const f = path.join(SHOT_DIR, `${String(shot).padStart(2, '0')}-${name || 'el'}.png`)
    const el = page.locator(sel).first()
    if (!(await el.count())) { console.log('NO_ELEMENT:', sel); return null }
    await el.screenshot({ path: f })
    console.log('SHOT', f)
    return f
  }

  // DOM click — coordinate-free, so it works under overlays.
  const click = async (sel) =>
    console.log('click', sel, '→', await page.evaluate((s) => {
      const el = document.querySelector(s)
      if (!el) return 'NOT_FOUND'
      el.click()
      return 'OK'
    }, sel))

  const clickTitle = async (t) =>
    console.log('click-title', t, '→', await page.evaluate((s) => {
      const el = document.querySelector(`[title="${s}"]`)
      if (!el) return 'NOT_FOUND'
      el.click()
      return 'OK'
    }, t))

  // Matches buttons, links AND the plain divs used as cards/rows — reqmesh
  // hangs React onClick on `.cursor-pointer` divs (project cards, nav rows),
  // which a button/anchor-only search silently misses. Among partial matches
  // the shortest wins, so we click the row and not its container.
  //
  // `rootSel` scopes the search. Names repeat across panes (a requirement and
  // a component can both be "Wing Assembly"), and an unscoped click can land
  // in the nav and navigate away — leaving later steps hunting for a button
  // on a page you already left.
  const clickText = async (t, rootSel) =>
    console.log('click-text', t, rootSel ? `in ${rootSel}` : '', '→', await page.evaluate(({ s, r }) => {
      const root = r ? document.querySelector(r) : document
      if (!root) return 'NO_ROOT'
      const els = [...root.querySelectorAll('button, a, [role="button"], .cursor-pointer')]
      const exact = els.filter((e) => e.textContent?.trim() === s)
      const partial = els
        .filter((e) => e.textContent?.includes(s))
        .sort((a, b) => (a.textContent?.length ?? 0) - (b.textContent?.length ?? 0))
      const el = exact[0] ?? partial[0]
      if (!el) return 'NOT_FOUND'
      el.click()
      return 'OK'
    }, { s: t, r: rootSel || null }))

  /**
   * Sign in through the real login modal (default account: admin/admin).
   * On a cold load the app has already auto-signed-in as a guest, and a guest
   * occupies the signed-in header branch — so there is no "Sign in" button
   * until we sign the guest out first.
   */
  const login = async (username = 'admin', password = 'admin') => {
    const opened = await page.evaluate(() => {
      const signIn = document.querySelector('[title="Sign in"]')
      if (signIn) { signIn.click(); return 'opened' }
      const signOut = document.querySelector('[title="Sign out"]')
      if (signOut) { signOut.click(); return 'signed-out-guest' }
      return 'NO_BUTTON'
    })
    if (opened === 'NO_BUTTON') return console.log('login FAILED — no sign in/out button')
    if (opened === 'signed-out-guest') {
      await sleep(300)
      await clickTitle('Sign in')
    }
    await page.waitForSelector('input[placeholder="password"]', { timeout: 5000 })
    await page.locator('input[placeholder="username"]').fill(username)
    await page.locator('input[placeholder="password"]').fill(password)
    await page.keyboard.press('Enter')
    await page.waitForSelector('[title*="diting"]', { timeout: 8000 })
    console.log('login OK', username)
  }

  /** Turn on EDITING mode — mutating UI is hidden/disabled while VIEWING. */
  const setEditMode = async (on = true) => {
    const state = await page.evaluate(() => {
      const el = document.querySelector('[title*="diting"]')
      return el ? el.textContent?.includes('EDITING') : null
    })
    if (state === null) return console.log('edit toggle NOT_FOUND — signed in?')
    if (state !== on) await clickTitle(on ? 'Click to enable editing' : 'Editing mode ON - click to disable')
    console.log('edit mode →', on)
  }

  const goto = async (hashPath) => {
    await page.evaluate((p) => { window.history.pushState({}, '', p); window.dispatchEvent(new PopStateEvent('popstate')) }, hashPath)
    await sleep(600)
    console.log('goto', hashPath)
  }

  // Element center + occlusion check.
  const probe = (sel) =>
    page.evaluate((s) => {
      const el = document.querySelector(s)
      if (!el) return { err: 'NO_ELEMENT' }
      const r = el.getBoundingClientRect()
      const x = r.x + r.width / 2
      const y = r.y + r.height / 2
      const hit = document.elementFromPoint(x, y)
      const onTarget =
        el === hit || el.contains(hit) ||
        (s.includes('react-flow__handle') && !!hit?.closest?.('.react-flow__handle'))
      return { x, y, onTarget, hitDesc: hit?.className?.toString?.().slice(0, 60) }
    }, sel)

  const center = async (sel) => {
    for (let i = 0; i < 6; i++) {
      const p = await probe(sel)
      if (p.err) { console.log('NO_ELEMENT:', sel); return null }
      if (p.onTarget) return p
      console.log(`occluded (${sel}) by:`, p.hitDesc, '— retrying')
      await sleep(400)
    }
    console.log('GIVING UP (occluded):', sel)
    return null
  }

  // Real mouse drag — needed for React Flow gestures in the graph pane.
  const drag = async (fromSel, toSel) => {
    const a = await center(fromSel)
    const b = await center(toSel)
    if (!a || !b) return console.log('DRAG SKIPPED', fromSel, '→', toSel)
    await page.mouse.move(a.x, a.y)
    await page.mouse.down()
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 10 })
    await page.mouse.move(b.x, b.y, { steps: 10 })
    await sleep(150)
    await page.mouse.up()
    console.log('drag OK', fromSel, '→', toSel)
  }

  // A screen point actually ON an SVG path — graph edges are curves, so their
  // bounding-box centre usually misses the stroke.
  const pathPoint = (sel, frac = 0.5) =>
    page.evaluate(({ s, f }) => {
      const p = document.querySelector(s)
      if (!p) return null
      const pt = p.getPointAtLength(p.getTotalLength() * f)
      const m = p.getScreenCTM()
      return { x: m.a * pt.x + m.c * pt.y + m.e, y: m.b * pt.x + m.d * pt.y + m.f }
    }, { s: sel, f: frac })

  const nodeIds = () =>
    page.evaluate(() =>
      [...document.querySelectorAll('.react-flow__node')].map((e) => e.getAttribute('data-id'))
    )

  const edgeIds = () =>
    page.evaluate(() =>
      [...document.querySelectorAll('.react-flow__edge')].map((e) => e.getAttribute('data-id'))
    )

  const text = async (sel) =>
    page.evaluate((s) => (s ? document.querySelector(s) : document.body)?.innerText ?? '(null)', sel || null)

  /** Read the API the way the app does — with the signed-in token attached. */
  const apiGet = (apiPath) =>
    page.evaluate(async (p) => {
      const t = localStorage.getItem('rt-token')
      const res = await fetch(`/api${p}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} })
      return { status: res.status, body: await res.json().catch(() => null) }
    }, apiPath)

  return { ss, ssOf, click, clickTitle, clickText, login, setEditMode, goto, probe, center, drag, pathPoint, nodeIds, edgeIds, text, apiGet }
}

// ---------- REPL mode ----------
const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const mode = process.argv[2] === 'desktop' ? 'desktop' : 'web'
  const { page, handle } = await launch({ mode })
  const h = helpers(page)
  const stdin = fs.createReadStream(null, { fd: fs.openSync('/dev/stdin', 'r') })
  const rl = readline.createInterface({ input: stdin, output: process.stdout, prompt: 'driver> ' })
  const COMMANDS = {
    async ss(a) { await h.ss(a) },
    async goto(a) { await h.goto(a) },
    async click(a) { await h.click(a) },
    async 'click-text'(a) { await h.clickText(a) },
    async 'click-title'(a) { await h.clickTitle(a) },
    async login(a) { const [u, p] = a.split(/\s+/); await h.login(u || undefined, p || undefined) },
    async edit() { await h.setEditMode(true) },
    async drag(a) { const [f, t] = a.split(/\s+/); await h.drag(f, t) },
    async type(a) { await page.keyboard.type(a, { delay: 30 }) },
    async press(a) { await page.keyboard.press(a) },
    async eval(a) { console.log(JSON.stringify(await page.evaluate(a))) },
    async text(a) { console.log(await h.text(a)) },
    async quit() { await close(handle); process.exit(0) },
    help() { console.log('commands:', Object.keys(COMMANDS).join(', ')) },
  }
  rl.on('line', async (line) => {
    const i = line.indexOf(' ')
    const cmd = i < 0 ? line.trim() : line.slice(0, i)
    const rest = i < 0 ? '' : line.slice(i + 1).trim()
    const fn = COMMANDS[cmd]
    if (cmd) {
      if (!fn) console.log('unknown:', cmd, '— try: help')
      else { try { await fn(rest) } catch (e) { console.log('ERROR:', e.message) } }
    }
    rl.prompt()
  })
  console.log(`reqmesh driver (${mode}) — "help" for commands`)
  rl.prompt()
}
