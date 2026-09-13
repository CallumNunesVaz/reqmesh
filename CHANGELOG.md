# Changelog

All notable changes to reqmesh are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and reqmesh uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**This file is what users read when they update.** `scripts/release.sh` takes the
body of `## [Unreleased]` as the release notes, which become the annotated tag
message, the GitHub release body, and the text shown in the in-app updater on the
System page. Write entries for the person deciding whether to apply the update —
not for the person who wrote the commit. If `[Unreleased]` is left empty the
release falls back to a grouped, deduplicated commit log, which is a safety net
rather than a substitute.

## [Unreleased]

## [0.6.1] - 2026-09-14

### Added

- Audit-trail retention, off by default. Set `RT_HISTORY_RETENTION_DAYS` to
  prune entries older than that at startup, or on demand with
  `POST /api/system/history/prune` (admin). Unset, the full history is kept.
- `POST /api/system/update/bundle` accepts the release's detached `.sig` as a
  second `signature` field, so an instance with `RT_UPDATE_PUBLIC_KEY` set can
  stage a signed bundle instead of having to disable verification. The System
  page does not send it yet; use the API or `curl` for now.
- The desktop AppImage is published with a detached Ed25519 `.sig` made with the
  same release key as the bundle; a release without the signing key is refused.
- `RT_SINGLE_INSTANCE=1` refuses to start when another process already holds
  the state dir, and `RT_LOCK_DIR` puts the advisory lock files on a shared
  volume. The Docker deployment sets both — two containers on one data root
  used to race each other's writes silently.
- The allocation matrix pages its rows, so a large project renders instead of
  building a million cells at once.
- A requirement page whose background sections fail to load (backlinks,
  definitions, risks…) now says which ones and offers a retry, instead of
  showing them empty.
- Every displayed timestamp carries its timezone.
- The requirement tree is a real tree for screen readers (levels, expanded
  state, roving focus).

### Changed

- `start.sh` binds to `127.0.0.1` by default. The personal profile allows
  anonymous reads and self-registration, so listening on every interface let
  anyone on the LAN read the data and create an account. Set `RT_BIND=0.0.0.0`
  to expose it deliberately.
- Live updates are per collection: another user's edit refreshes only the
  views that display that collection, plus anything it rewrites as a side
  effect (a requirement edit refreshes verification, a baseline change
  refreshes requirements and components, a rename or git restore refreshes
  everything). Every mounted page used to re-fetch and re-solve the whole
  project on each change.
- The offline image-mode update in the updater sidecar is refused unless
  `RT_UPDATE_ALLOW_UNSIGNED_IMAGE=1`: an uploaded image tarball carries no
  signature to verify, unlike the pull path.
- The nginx configs rate-limit at the edge: 30 r/s per client for the API and
  1 r/s (burst 5) for the credential endpoints — login, register, guest,
  forgot/reset-password and email verification only.
- Base images are digest-pinned, the security scanners are version-pinned, and
  the tectonic installer downloads a pinned release tarball and checks its
  SHA-256 instead of piping a remote script into a shell. The Docker installer
  is downloaded, checked non-empty, then run.
- Caddy's request cap is 52 MB so a large import passes through it as it
  already did through nginx.
- An unmatched `/api/...` path returns a JSON 404 instead of the SPA shell.
- The crash screen no longer shows the stack trace in production builds.

### Security

- Logging out revokes the session token. Clearing the cookie left a captured
  token valid for its full lifetime; the revocation is scoped to that session,
  so other devices stay signed in ("log out everywhere" is unchanged).
- Project permissions fail closed. An unreadable `_meta.yaml` used to fall back
  to the permissive role defaults; it now refuses the request, hides the
  project from the listing and rejects the live-update subscription. The
  project list itself is filtered to what the caller may view.
- A git remote URL with embedded credentials is refused on write (it would be
  committed and pushed with the project); a legacy one is masked on read and
  can still be tested and left in place.
- The code scan skips committed symlinks, which could point outside the
  scanned tree.
- Logging in to a locked or disabled account takes as long as a wrong password,
  so the lockout state no longer reveals whether the account exists.
- The request-body cap applies to every non-multipart body; declaring
  `text/plain` used to bypass it.
- uvicorn trusts forwarded headers from `127.0.0.0/8` only, matching the app's
  own `proxy_trusted_cidr`. On a deployment reachable from a private address a
  caller could choose its own client IP and mint a fresh rate-limit bucket per
  request.
- Rate-limit buckets are keyed on their window. Login's 60-second sweep used to
  evict the fresh 300-second buckets for register, forgot-password and
  verify-email, so the strictest limits degraded toward login's.
- `POST /evaluation/impact` requires view permission on the project.
- The desktop shell compares origins rather than URL prefixes when deciding
  whether to allow a navigation, and blocks off-origin redirects.

### Fixed

- A replace-mode import that fails partway is rolled back; it used to leave a
  half-imported project with no way back.
- Two audit entries written in the same microsecond no longer overwrite each
  other, and two concurrent creates of one id return 409 instead of the second
  silently replacing the first.
- A constraint expression that is nested too deeply, or holds a literal too
  large for a float, reports an expression error instead of a server error.
  Expressions are capped at 500 characters.
- Publishing a project whose requirements contain a parent cycle no longer
  hangs, and the hierarchy build is linear in the number of requirements.
- Git restore removes files added after the snapshot; it used to keep them and
  commit them as part of the "restore".
- The code scan kept only the last reference for a requirement referenced from
  several files.
- ReqIF export emits descriptions as XHTML markup; `<p>x</p>` used to
  round-trip as the literal string.
- Bulk delete keeps its per-id referrer check, so a reference created during
  the batch is honoured.
- The requirement list shows current constraint verdicts and baseline names
  after another user's change; those were only refreshed by your own edits.
- "Test connection" on the git settings works for `ssh://git@host` remotes
  again — the username was being masked as `***` and tested literally.
- Applying what-if overrides is rolled back if a later requirement is refused,
  and every write (including the rollback) carries If-Match so a concurrent
  edit is refused rather than overwritten.
- Escape inside a dialog no longer also navigates the page behind it, and
  focus returns to the control that opened the dialog when it closes.
- Leaving project settings with unsaved naming, stakeholder, risk-matrix or git
  edits asks first; only the name was guarded before.
- The SSE reconnect no longer races two connections after a dropped stream,
  and the graph's text cache is bounded.
- Per-page layout preferences are keyed by section, not by record id, so
  localStorage no longer grows one entry per visited requirement.
- A failed export download shows a toast instead of failing silently.
- Users with propose permission can post comments from the UI, matching what
  the API already allowed.
- Search and the activity view are markedly faster on large projects (HTML is
  stripped once and cached; entity labels are resolved through one index).

## [0.6.0] - 2026-09-01

### Added

- Desktop app: Linux AppImage is now published with each release, alongside a
  `.sha256`. Previously the desktop shell was built and boot-tested in CI but
  never reached a user.

### Changed

- Async results are announced to screen readers through a shared live region.
  Previously only toasts announced anything, so an import summary completed in
  silence.
- Release notes are curated from this file instead of being a raw commit log.
  When no entry exists the fallback groups commits by kind, deduplicates changes
  that landed on more than one branch, and orders security and features above
  build noise.

### Security

- `react-router` upgraded 6 → 7, clearing two moderate advisories (open redirect
  via backslash in `<Link>`/`useNavigate`, and constructor injection during SSR
  hydration). `npm audit` now reports no runtime vulnerabilities.

### Fixed

- Deleting a component now records the move in each promoted child's history.
  The child's parent changed silently before, so the move was invisible in the
  audit trail.
- Parametric rollups over a deep component tree no longer fail with a server
  error. Component chains are walked iteratively, and a derived parameter chain
  nested more than 100 levels now reports a clear expression error instead of
  crashing.
- A toast no longer disappears while you are hovering it or tabbing to its
  link — the dismiss timer pauses and resumes.

### Removed

- The System page no longer links out to the source repository.

## [0.5.0] - 2026-08-30

### Added

- Parametric editing: live expression syntax highlighting, full combobox ARIA on
  the autocomplete, and margin gauges showing constraint headroom in place.
- What-if analysis animates the cascade one step at a time instead of blinking
  each step into the list.
- Update bundles are signed end to end with Ed25519 and verified before a staged
  tree is swapped in.
- Every project-scoped read route is behind an authorization gate.
- The desktop shell bundles a frozen backend, so the packaged app boots.

### Changed

- Electron 31 → 39, electron-builder 24 → 26.
- Backend dependencies are hash-pinned; shell scripts are linted in CI.
- The backend is type-checked with mypy, gated in CI.
- Backend test coverage is measured and gated at 82%.

### Fixed

- Closed a delete TOCTOU and several composite-operation races.
- One auth source could lock an account it did not own.
- `users.yaml` writes are fsynced, and locking no longer depends on `fcntl`.
- Changing a password or email now requires the current password.
- SSE streams no longer have chunked encoding disabled by nginx.
- Startup refuses to boot with more than one worker, which the YAML store and
  the per-process event bus both require.

## [0.4.0] - 2026-08-22

### Added

- Comfortable/compact density setting for lists and tables.
- Verification cases get a list and a detail view.
- `Reveal` primitive and a shared reduced-motion hook, adopted app-wide.
- `EmptyState` adopted across the list pages.

### Fixed

- Selects regained their dropdown affordance.
- Clickable cards are keyboard-reachable.

## [0.3.7] - 2026-08-15

### Added

- Lists remember your position when you navigate back to them.

### Fixed

- A new parameter can be referenced before its requirement is saved.
- Canvas reserves layout height for a node's level-5 content.
- Canvas dims edges with CSS classes rather than 1,500 inline styles.

---

Releases before 0.3.7 are recorded in their annotated git tags
(`git tag -l --format='%(contents)' v0.3.6`).
