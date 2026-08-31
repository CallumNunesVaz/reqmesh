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
