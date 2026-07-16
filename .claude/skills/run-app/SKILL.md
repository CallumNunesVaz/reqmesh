---
name: run-app
description: Build, launch, and drive the reqmesh app (web or Electron desktop) with real mouse/keyboard via Playwright — for verifying UI changes, taking screenshots, or reproducing bugs. Use when asked to run the app, test a flow end-to-end, or see a change working.
---

reqmesh is a FastAPI backend + React/Vite SPA, shipped both as a web app and an
Electron desktop shell. Agents drive the real app through Playwright using the
helpers in `driver.mjs` (same directory). Screenshots are the feedback loop:
**take one after every meaningful step and actually look at it.**

## Prerequisites

```bash
cd <repo>/desktop && npm i --no-save playwright-core   # keep package.json unchanged
cd <repo>/frontend && npm run build                    # the driver serves frontend/dist
```

The backend runs from `backend/.venv` (falls back to `python3`). On this
machine `DISPLAY=:1` (the user's desktop) is available and there is **no xvfb
or tmux** — the window appears on the user's screen while you drive it, which
is a feature: they can watch. Pass `headless: true` (web mode only) to hide it.

## Choosing a mode

- **`mode: 'web'`** (default) — spawns the backend and drives it in Chromium.
  This is the primary deployment; use it unless the change is shell-specific.
  Supports `headless`.
- **`mode: 'desktop'`** — launches the Electron shell (`desktop/main.js`), which
  boots its own backend. Slower; use it when the change touches the shell,
  packaging, or single-origin static serving.

Both render the same SPA, so a UI change only needs one.

## Running a scripted flow (primary pattern)

```js
import { launch, helpers, close, sleep } from '<repo>/.claude/skills/run-app/driver.mjs'

const { page, handle } = await launch({ mode: 'web' })   // seeds the Cessna demo
const h = helpers(page)

await h.login()                                  // admin/admin
await h.clickText('Cessna 172S Skyhawk SP')      // project cards are divs — see gotcha 2
await sleep(2000)
await h.ss('project')
await h.setEditMode(true)                        // REQUIRED before any mutation — gotcha 3
// ... drive, screenshot, verify ...
await close(handle)                              // NOT browser.close() — gotcha 6
```

Run it: `node flow.mjs`. `node driver.mjs [web|desktop]` gives a stdin REPL with
the same commands.

**Launches dark by default.** reqmesh follows the OS colour scheme and
Chromium reports `light`, which is not how most people see the app — judging a
visual change in the wrong theme wastes a whole run. Pass `theme: 'light'` to
check the other one; always check both before calling a restyle done.

`ssOf(sel, name)` screenshots a single element — `h.ssOf('.react-flow', 'graph')`
frames the graph without the surrounding page. To judge node detail, zoom first:
`page.mouse.move(<centre of pane>)` then `page.mouse.wheel(0, -300)` a few times.

`launch()` sandboxes everything: `HOME=/tmp/rm-uitest-home` redirects
`~/.reqmesh/{users.yaml,secret}`, `RT_DATA_ROOT` puts projects under the same
temp dir, and `RT_GIT_AUTOCOMMIT=false` means driving the UI can never author
commits. **The user's real accounts and projects are never touched.** The dir is
wiped per launch (`fresh: false` to keep it) and the Cessna demo is seeded
(`seed: false` to start empty), giving you 57 requirements to drive.

## Gotchas (each cost a failed run)

1. **Every delete is a `window.confirm`**, and Playwright *auto-dismisses*
   dialogs unless something listens — the click reports `OK` and nothing
   happens. `launch()` installs an auto-accept handler; don't call
   `page.removeAllListeners('dialog')` unless you want a cancel. *(Verified:
   without the handler a delete leaves the count unchanged.)*
2. **Only header actions have `title=`.** `clickTitle` works for Graph / Export /
   Import / Users / the edit toggle. In-page actions (Delete, Save, New
   Requirement) are text buttons, and cards/rows are `.cursor-pointer` **divs**
   with React `onClick` — use `clickText`, which searches
   `button, a, [role=button], .cursor-pointer` and prefers the shortest match.
3. **Mutating UI does not exist while VIEWING.** "New Requirement" and friends
   are unrendered until `setEditMode(true)` — a missing button usually means
   edit mode is off, not that the selector is wrong. Editing needs a non-viewer
   account; guests are `viewer` and can never edit.
4. **A cold load auto-signs-in as a guest**, and the guest fills the *signed-in*
   header slot, so there is **no "Sign in" button** to click. `h.login()`
   handles this (signs the guest out first) — don't hand-roll it.
5. **The graph pane overlays the right ~38% of the window** and is open by
   default. Node ids are requirement ids
   (`.react-flow__node[data-id="AFRM0001"]`); edge ids are
   `<source>-<target>-<type>` (`AFRM0005-AFRM0004-refines`). Use `drag()` for
   React Flow connections and `pathPoint()` to click an edge — edges are curves,
   so their bounding-box centre misses the stroke. `clickTitle('Graph')` hides
   the pane if it is in the way.
6. **Always close via `close(handle)`** — in web mode the backend is a child
   process that outlives the browser. If a flow throws, `launch()`'s exit hook
   kills it for you *(verified on a simulated crash)*; if a run is `kill -9`'d,
   sweep strays: `pkill -f "uvicorn app.main:app"`.
7. **Rebuild before driving** (`cd frontend && npm run build`) — the driver
   serves `frontend/dist`, not the Vite dev server, so stale builds test stale
   code.

## Verifying state

Prefer reading over trusting clicks. `h.apiGet('/projects/cessna-172/requirements')`
hits the API with the signed-in token — the ground truth behind the UI, and the
cheapest way to prove a mutation landed (compare counts before/after).
`h.text('main')` reads the page, `h.nodeIds()` / `h.edgeIds()` inspect the graph.
Screenshot everything; a blank or wrong frame is a failed step even when the
click reported OK.

## Unit tests

This skill is for behaviour you have to *see*. Logic that can be asserted
belongs in the fast suites, which need no app at all:

```bash
cd backend  && .venv/bin/python -m pytest tests/   # API, storage, auth, import/export
cd frontend && npm test                            # stores, API client, pure helpers
cd frontend && npm run typecheck
```
