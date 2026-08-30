# reqmesh — Comprehensive Software Review

**Reviewed:** commit `8c3352c` (v0.4.0)
**Scope:** backend (FastAPI, ~27k LOC Python), frontend (React/Vite SPA, ~37k LOC TypeScript), desktop shell (Electron), deployment/ops (Docker, installers, updater), and engineering process (tests, CI, schemas).

---

## 1. Executive summary

reqmesh is a requirements-management tool whose defining architectural bet — one
YAML file per entity, validated against Pydantic-derived JSON Schemas, versioned
natively by git — is executed unusually well. The codebase shows real
engineering discipline: atomic fsync'd writes, cross-process file locking,
read-side validation that treats the disk as untrusted input, a single link
registry driving deletes/renames/integrity, a CI pipeline that tests its own
workflows, and four independent XSS defenses.

The review found **no critical vulnerabilities**, but several structural
limitations that define the product's envelope:

- **Single-process ceiling.** All collaboration state (event bus, presence,
  rate limiter, git counters) is in-process, and `--workers 1` is hardcoded in
  both deployment paths. The web app cannot be scaled horizontally without a
  redesign of that state. Data integrity survives multi-worker via flock, but
  liveness does not.
- **No read-level authorization.** The per-project permission map (view/
  contribute/maintain/admin) only gates writes. Any authenticated user can
  read every project, and the full report download route has no auth
  dependency at all. Fine for the desktop/single-team profile; a real gap for
  multi-project team deployments.
- **Unsigned update chain.** The bare-metal updater accepts unsigned bundles by
  default (SEC-9, tracked but open), and the Docker self-update pulls mutable
  `latest` tags with no digest pinning. A compromised release account or
  registry is arbitrary code execution on every self-updating instance.
- **The desktop product cannot boot when packaged.** The Electron packaging
  config does not include the backend it tries to spawn; CI never builds or
  boots a packaged artifact. Desktop is effectively a dev convenience, not a
  shippable product.
- **List reads do not scale.** Every list request parses and validates the
  entire collection; pagination bounds the response, not the work. Measured
  ~0.8 s per list read at 8k entities. Practical comfort ceiling is roughly
  2–5k entities per project.

| Dimension | Rating | One-line verdict |
| --- | --- | --- |
| Correctness & data integrity | Excellent | Atomic writes, cross-process locks, read-side validation are all carefully done |
| Security | Good | Strong XSS/CSRF/path defenses; weakest spots are missing read authz and unsigned updates |
| Maintainability | Good | Clear layer discipline, single source of truth for links and error envelopes; a few very large files |
| Scalability | Fair | Single-worker by design; linear full-parse list reads cap data growth |
| Portability | Fair | Linux server path is excellent; desktop packaging broken; no macOS/Windows story |
| Testing & CI | Excellent | 2,137 backend tests, 624 frontend unit + 258 e2e, schema-drift gates, 4 SAST/SCA tools |
| Observability/ops | Good | Health endpoints, audit log, SSE/WS presence; docs largely honest and accurate |

---

## 2. Architecture

```
frontend (React 18 SPA)  desktop (Electron shell)
        │  REST + SSE/WS        │ spawns backend
        ▼                        ▼
backend (FastAPI, sync handlers on threadpool)
  api/     — thin routers: parse, authorize, delegate
  models/  — Pydantic: the contract (source of truth for schemas/ and TS write models)
  services/— business logic, FastAPI-free
  core/    — auth, ids, filelock, rate limiting, config
  storage/ — YAML store: one file per entity, 11 collection dirs, git-versioned
```

Key design decisions:

- **YAML on disk + git as the persistence layer.** Every entity is its own
  YAML file under a project root; commits are debounced per project; the disk
  is treated as untrusted input (hand-edits, `git pull`) and re-validated on
  read (`backend/app/services/load_guard.py:67-89`).
- **Writes are atomic and serialized.** temp file → `fsync` → `os.replace` →
  dir `fsync` (`backend/app/storage/yaml_store.py:193-221`); read-modify-write
  is guarded by per-file advisory `flock` (`backend/app/core/filelock.py`).
- **Single link registry.** Every cross-entity reference is declared once in
  `backend/app/services/link_registry.py:72-119`; delete guard, integrity
  checker, rename sweeps, and tracing all derive from it.
- **Middleware for cross-cutting concerns.** Auth, CSRF, security headers,
  streamed body-size cap, git auto-commit, and SSE mutation broadcast live in
  `backend/app/main.py`, not per-route dependencies.
- **Two-way schema generation.** `schemas/*.json` and the TS write models are
  generated from Pydantic and CI fails on drift (`.github/workflows/ci.yml`
  `schema-freshness` job).
- **Error envelope discipline.** Structured errors use one factory
  (`backend/app/services/errors.py:20-26`) with shape `{error, message, ...}`;
  the frontend switches on `error` and preserves details (no
  `[object Object]` interpolation).

---

## 3. Strengths

### Backend
- **Atomic, durable writes done right** — file fsync *before* rename, directory
  fsync *after* (`yaml_store.py:199-214`); per-call `ruamel` instances avoid
  poisoned-emitter bugs.
- **Cross-process locking with documented non-re-entrancy handling**
  (`yaml_store.py:230-255`, `router.py:1460-1497`).
- **Defense-in-depth on ids/paths** — `safe_id` grammar, symlink/`..` guards in
  middleware (`main.py:386-399`), reference-path confinement
  (`services/references.py:8-24`).
- **Corrupt files are skipped-and-reported, never coerced to `{}`**
  (`yaml_store.py:299-357`).
- **Collection cache with mtime+size signature invalidation and copy-on-hit**
  (`yaml_store.py:62-105`) — genuinely well designed.
- **Migration safety** — idempotent per-file migrations, startup marker,
  per-file error tolerance (`services/migrations.py:198-226`).
- **Git security posture** — commit serialization per project, remote scheme
  allowlist, `IdentitiesOnly` SSH, credential redaction, `restore_commit`
  verified via `rev-parse` before checkout (`services/git_service.py:438-485`).
- **Evaluator sandbox** — AST whitelist interpreter, no `eval`
  (`services/evaluation.py:165-243`).
- **All ~180 routes are sync** (`def`), keeping CPU work off the event loop.

### Security
- **Stored XSS defended at four layers** — write-side Pydantic sanitizers,
  read-side sanitize off disk (`load_guard.py:76-84`), export-side sanitize
  (`publisher.py:576`), and a client-side allowlist renderer that drops all
  attributes (`frontend/src/components/autoLink.tsx:155-189`);
  `dangerouslySetInnerHTML` is banned by unit test.
- **No `shell=True` anywhere**; argv-list subprocess calls; commit messages and
  restore hashes validated against whitelist regexes.
- **CSRF enforced globally** via middleware with constant-time comparison,
  HttpOnly JWT cookie + readable double-submit token (`main.py:311-331`).
- **Secrets hygiene** — prod compose requires `RT_SECRET`/`RT_ADMIN_PASSWORD`,
  no default credentials; bootstrap admin password burned after first login;
  startup refuses to run if state dir sits inside the git-versioned data root
  (`main.py:93-99`).
- **Login hardening** — uniform 401s, dummy bcrypt for unknown users, per-account
  lockout, 12-char password policy with complexity rules.
- **Import/XML hardening** — DOCTYPE refused in JUnit/ReqIF parsers (XXE
  defense); tar extraction blocks traversal/symlinks/hardlinks
  (`bundle_update.py:155-170`).
- **Electron basics right** — `contextIsolation: true`, `sandbox: true`,
  `nodeIntegration: false`, navigation locked to local origin
  (`desktop/main.js:121-139`).
- **Container hardening** — non-root user, read-only rootfs,
  `cap_drop: ALL`, `no-new-privileges` (`docker-compose.prod.yml:79-83`).

### Frontend
- **Write-contract codegen with CI gate** — Pydantic → `writeModels.ts`, diffed
  in CI (`backend/tests/test_write_models_currency.py`).
- **Real graph performance work** — ELK in a Web Worker with memoized singleton
  and bundled fallback, viewport culling, perf mode above a node threshold,
  `contain: layout style`, stale-response sequence guards
  (`GraphPane.tsx:184-205, 2117, 2521-2580`).
- **Refactor discipline** — `Reveal` replaced 55 copy-pasted motion
  incantations; `useBulkActions` unified confirm+undo+invalidate flows that
  "most copies were missing something of".
- **Error-model care** — 401→logout only when previously signed in (with a
  comment explaining the redirect loop it avoids); `?next=` validated by
  `safeNext.ts`.
- **Accessibility** — keyboard/focus-trap/label e2e specs, live
  `prefers-reduced-motion` handling, real button semantics on card grids.
- **Air-gapped self-containment enforced at build time**
  (`frontend/scripts/check-selfcontained.mjs` fails on any remote resource).

### Testing & CI
- **2,137 backend tests** (1,936 fast + 199 Schemathesis contract + 2 bench),
  **624 frontend unit** (1.5 s), **258 Playwright e2e** across 78 specs with
  an auth-required variant and pristine-data fixtures.
- **Real-role auth fixtures** test guards through the real dependency chain
  (`backend/tests/conftest.py:43-67`).
- **Contract suite anti-shrinkage floors** — the OpenAPI test asserts >100
  documented paths so coverage cannot silently shrink.
- **Four SAST/SCA tools** (CodeQL, semgrep, bandit, gitleaks) + pip-audit on
  prod *and* dev trees + trivy container scan + digest-pinned actions and
  tools; Dependabot with cooldowns.
- **CI config is itself tested** (`scripts/tests/test_ci_config.sh`).
- **Schema-drift gate** regenerates all four generated artifacts and fails on
  any diff (schemas, write models, `docs/api.md`, quality rules).
- **Installer robustness is exceptional** — `set -euo pipefail` throughout,
  0600 `.env` before content, port-holder detection via `ss`, real post-deploy
  login check, idempotent re-runs preserving secrets.

---

## 4. Findings

Severity scale: **Critical / High / Medium / Low**.

### 4.1 Correctness & concurrency

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| C1 | Medium | **Multi-file operations are ordered, not atomic.** Rename, reparent, cascade, and import-`replace` touch many files with only per-file locks; nothing serializes two composite operations against each other. Interleaving can produce states no single operation would produce (self-documented for rename). | `services/rename.py:496-500`, `reparent.py:161-211`, `router.py:692-733` |
| C2 | Medium | **TOCTOU in the delete guard.** `check_deletable` scans referrers outside any lock; a concurrent request can create a reference between the scan and the `os.remove`, leaving a dangling reference. Integrity checker reports it afterward, so it is not silent. | `services/delete_guard.py:48` vs `router.py:607-615` |
| C3 | High | **Multi-worker deployment breaks liveness invariants; workers pinned to 1.** SSE/WS bus, presence, rate-limit buckets, git debounce counters, and live settings are all per-process. `--workers 1` is hardcoded, which is the only thing holding this together. flock *does* work across workers, so data integrity survives; presence, events, rate limits, and live config do not. | `Dockerfile.prod:147`, `scripts/templates/reqmesh.service.tmpl:22`, `event_bus.py:118-122`, `rate_limit.py:6` |
| C4 | Medium | **File locking is a silent no-op on Windows.** `fcntl` import failure degrades the lock to a bare `yield`; even single-process threadpool concurrency loses read-modify-write serialization on the platform the desktop shell targets. | `core/filelock.py:14-17, 28-30` |
| C5 | Medium | **`users.yaml` writes skip the fsync discipline.** `save_users` does temp → `os.replace` with no fsync and no directory fsync, while the entity store does both. Power loss can silently revert the most security-sensitive file in the product. | `core/auth.py:202-219` |
| C6 | Medium | **Unmarked data roots are stamped "current" without migrating.** `run_migrations` assumes no marker = fresh install; legacy installs predating the framework genuinely skip their migrations. The read-side coercions paper over the two known cases; every future migration inherits the hole. | `services/migrations.py:201-212` |
| C7 | Low | **Migration runner has no inter-process lock.** Two instances against one data root can race on the marker; benign today because steps are idempotent. | `services/migrations.py:218-224` |
| C8 | Low | **Optimistic concurrency for traces versions the whole document.** Any concurrent link change 409s every other editor. Correct, but coarse. | `yaml_store.py:504-530` |
| C9 | Low | **Cascade propagation can clobber concurrent child edits** — residual last-writer-wins on shared fields; acceptable for the domain, worth documenting. | `router.py:569-604` |

### 4.2 Security

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| S1 | Medium | **Report download has no authorization.** `GET /projects/{id}/publish/download` (full HTML/PDF/MD/LaTeX/ReqIF/SysML/CSV/XLSX export incl. changelog) depends only on a rate limit; its sibling POST requires maintainer. Under `team` profile any authenticated user can export any project; under `personal` it is anonymous. Also a CPU DoS vector (~11 s PDF per request). | `api/publish_routes.py:52-61` |
| S2 | Medium | **Permission maps do not gate reads.** View/contribute/maintain/admin tiers are consulted only by write guards and the WS handler; every HTTP read route is unguarded (e.g. all 16 `analysis_routes.py` routes have zero auth dependencies). Any authenticated user can read every project. | `core/dependencies.py:39-57`, `api/analysis_routes.py` |
| S3 | Medium | **Password change without the current password.** `PATCH /auth/profile` validates complexity but never requires the old password. A stolen/leftover session can silently change it and lock the owner out permanently. | `api/auth_routes.py:227-230` |
| S4 | Medium | **Self-update accepts unsigned bundles by default.** With `RT_UPDATE_PUBLIC_KEY` unset (the default) the Ed25519 check is skipped. The Docker path has no authenticity check at all — pulls mutable `:latest` tags with no digest pinning. A compromised release account or registry ⇒ arbitrary code execution on every self-updating instance. Tracked internally as SEC-9, still open. | `services/bundle_update.py:185-199`, `scripts/updater/updater.py:257`, `scripts/updater/watch.sh:50-66` |
| S5 | Low | **X-Forwarded-For spoofing via default trusted proxy ranges.** `proxy_trusted_cidr` defaults to all RFC1918 ranges, so any LAN host that can reach the app port can mint fresh rate-limit buckets. Only a startup warning exists; per-account lockout still applies. | `core/config.py:155`, `rate_limit.py:52-63` |
| S6 | Low | **Account-lockout DoS / username spray.** 5 failures locks an account 15 min with no per-(IP, username) accounting; an attacker who knows a username can keep it locked. | `core/auth.py:330-340` |
| S7 | Low | **`GET /projects` discloses absolute filesystem paths** to any authenticated user. | `api/router.py:158-171` |
| S8 | Low | **`/auth/register` does not validate the role field** (the admin path bypasses `_validate_role`; unknown roles fall back to view-tier, so no escalation, but malformed roles can be persisted). | `api/auth_routes.py:112-115` |
| S9 | Low | **TrustedHost enforcement off by default** (`allowed_hosts = ["*"]`); Host-header spoofing defense is absent unless configured. | `core/config.py:127`, `main.py:178-179` |
| S10 | Low | **SSH `StrictHostKeyChecking=accept-new`** (TOFU) — MITM on first push can capture the deploy key's use and project history. | `services/git_service.py:292-297` |
| S11 | Low | **Credentialed git remote URL returned in plaintext** to edit-tier users; log/status redaction not applied to the API response. | `api/router.py:229-230` |
| S12 | Info | **WS-scoped tokens usable as HTTP session credentials** for 120 s (`decode_token` ignores `scp`). Negligible impact; scope should be enforced. | `core/auth.py:289-293`, `dependencies.py:84-94` |
| S13 | Info | **Comment/decision rich-text fields outside sanitizer coverage** — safe today because consumers render as text or latex-escape; fragile if a future consumer renders HTML. | `services/load_guard.py:43` |
| S14 | Info | **Rate limiter is per-process, in-memory** — buckets vanish on restart and multiply with workers (see C3). Acceptable under the pinned single-worker posture; document the constraint. | `core/rate_limit.py:6` |

### 4.3 Scalability & performance

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| P1 | Medium | **Pagination bounds the response, not the work.** `list_requirements` materializes, validates, and decorates every requirement before slicing; `limit=1` costs the same as `limit=2000` (measured ~0.8 s at 8k entities). The frontend truncation banner is honest, but pagination cannot make a large project usable. | `api/router.py:446-468` |
| P2 | Medium | **Every save is a full-file parse-dump-fsync; bulk routes loop it per entity.** Importing a few thousand SysML entities is thousands of parse-dump-fsync cycles. Per-file granularity is the right design (meaningful git diffs), but bulk paths need a batched write mode. | `storage/yaml_store.py:383-405`, `api/bulk_routes.py:114-122` |
| P3 | Medium | **Activity feed scans and parses every history entry.** Default unbounded query is O(total history entries) with the slow round-trip parser (measured 4.7 s at 9k files), growing linearly forever. | `storage/yaml_store.py:553-607` |
| P4 | Low | **Referrer/integrity scans are O(collection) per operation**; `bulk_delete_*` is O(N·M); circular-parent checking re-walks chains from every requirement (O(N²) worst case). Fine at thousands of entities, degenerate at tens of thousands. | `services/link_registry.py:183-221`, `integrity.py:160-179` |
| P5 | Low | **Mutation events carry no payload** — N collaborating users × full-list refetch per keystroke-level mutation, each a full-project parse (multiplies P1). | `main.py:459-464` |
| P6 | Low | **History duplicates git's versioning** — two uncompressed audit trails (entity file + history entry per save), unbounded storage amplification. Defensible for UI-level audit access. | `services/history.py:21-31` |
| P7 | Low | **Single-item reads bypass the collection cache** and pay the ~6.5× round-trip parser on every detail view. | `storage/yaml_store.py:49-52, 359-363` |

**Scalability ceiling:** comfortable to ~2–5k entities per project; linear
degradation beyond, with no relief from pagination. Single-digit concurrent
editors before requests queue behind publishing/validation CPU work (sync
handlers under the GIL, default 40-thread pool). ~20 active projects fit the
256-entry collection cache. Horizontal scaling is blocked by C3. For a
git-native desktop/small-team requirements tool this envelope is a legitimate
product decision — but it should be stated in the docs, and the list-read cost
is the thing that will actually cap data growth.

### 4.4 Maintainability

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| M1 | High | **Read-model types are hand-maintained with no currency gate.** ~90 response interfaces and ~190 endpoint signatures in `client.ts` are typed by hand against the Pydantic read models; only the write models are generated and CI-diffed. A backend rename/type change silently mismatches at runtime. | `frontend/src/api/client.ts:440-1717` |
| M2 | Medium | **God components.** `GraphPane.tsx` (2,626 lines, ~40 hooks), `RequirementDetailPage.tsx` (1,826 lines, ~35 `useState`), `client.ts` (1,717 lines). The biggest files are the hardest to change safely. | `frontend/src/components/GraphPane.tsx`, `pages/RequirementDetailPage.tsx` |
| M3 | Medium | **Every mutation causes 2–3 full-project refetches and 2 full graph relayouts.** The mutating client reloads, then the SSE broadcast (which reaches the mutator too) bumps versions again; `GraphPane` fully reloads + ELK-relayouts per bump with no debounce. At the 2,000-entity cap that is ~2× multi-endpoint refetch and 2× worker relayout per save, amplified N-fold per collaborator. | `main.py:460`, `frontend/src/components/Layout.tsx:381-384`, `GraphPane.tsx:730-774` |
| M4 | Medium | **No virtualization for big lists/trees.** Up to 2,000 DOM rows × ~8 columns rendered unconditionally; nav tree mounts thousands of elements. | `pages/RequirementsPage.tsx:561`, `components/RequirementNav.tsx` |
| M5 | Low | **Implicit global state in the API module.** `_lastPageMeta` is module-level, invisible to React, keyed only by collection (a second project's fetch clobbers the first's truncation info). | `frontend/src/api/client.ts:373-381` |
| M6 | Low | **Dead/legacy store fields + whole-store subscriptions.** `verificationCases`, `loading`, `error` have no readers; several pages destructure the whole store and re-render on canvas-interaction state changes. | `frontend/src/store/index.ts:24-49` |
| M7 | Low | **SSE reconnect is a fixed 3 s hammer** with no backoff/jitter, against hard per-user (5) and global connection caps — N tabs reconnect in lockstep during outages and can trip the caps. | `frontend/src/components/Layout.tsx:391-394` |
| M8 | Low | **Homegrown HTML sanitizer** (DOMParser + tag allowlist, drops all attributes). Safe in practice, but hand-rolled sanitization is a poor-track-record category with no XSS input-matrix tests; it also silently drops `<img>` while the editor offers image paste — a functional inconsistency. | `frontend/src/components/autoLink.tsx:153-209`, `RichTextEditor.tsx:241-243` |
| M9 | Low | **Static content embedded in code** — `DocumentationPanel.tsx` (1,002 lines) and `loadingMessages.ts` (518 lines) are mostly prose; hard to review, rebuild required to change. | `frontend/src/components/DocumentationPanel.tsx` |
| M10 | Low | **Dead vite chunk rule** referencing `@dagrejs` (not in package.json; leftover from the dagre→ELK migration). | `frontend/vite.config.ts:45` |

### 4.5 Portability & deployment

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| D1 | High | **Packaged desktop app cannot boot; packaging untested in CI.** `desktop/package.json` ships only `main.js`/`preload.js`/`package.json` + `frontend/dist`; `main.js` spawns the backend with `cwd` = `<resources>/backend`, which is never packed — spawn fails with an unhandled ENOENT and the main process crashes. CI lints the two JS files but never builds or boots an artifact; the historical AppImages/snaps in `desktop/release/` predate the layout. Decide: bundle the backend (venv/PyInstaller) + CI smoke boot, or drop the packaging claim. | `desktop/package.json:23-26`, `desktop/main.js:16-17, 84-85`, `.github/workflows/ci.yml:118-135` |
| D2 | High | **Docker self-update pulls mutable tags with no integrity verification; sidecar trusts uploaded archives.** The sidecar holds the Docker socket (root-equivalent) and `handle_image` retags any uploaded archive as the app image. Combined with S4, the update chain is unsigned end-to-end. | `scripts/updater/watch.sh:50-96`, `docker-compose.prod.yml:119` |
| D3 | Medium | **Nothing enforces the single-worker constraint** beyond hardcoding. A scaling operator gets split presence, missing events, per-worker rate-limit buckets, and cross-worker `git index.lock` collisions; sticky sessions cannot fix it. A one-line refusal of `--workers > 1` at startup would make the failure loud instead of silent. | `main.py:41`, `core/event_bus.py:118` |
| D4 | Medium | **nginx config disables chunked encoding on the SSE stream** — with keep-alive and no content-length, framing relies on connection close. The Caddy path is correct; the nginx template and DEPLOYMENT.md both carry the bad setting. | `nginx.conf:54`, `scripts/templates/nginx.conf.tmpl`, `DEPLOYMENT.md:255` |
| D5 | Medium | **Updater never verifies the post-swap container is healthy.** If the new image crash-loops, status stays `in_progress` forever — no timeout, no health poll, no rollback to the previous tag. | `scripts/updater/watch.sh:58-62` |
| D6 | Medium | **Docs drift:** manual systemd unit in DEPLOYMENT.md runs as root (generated template is hardened); docs promise "Python 3.11+" while the image uses 3.12 and `deploy-bare.sh` has no version floor (comment claims one). | `DEPLOYMENT.md:27, 274`, `Dockerfile.prod:17` |
| D7 | Low | **`RT_ALLOWED_HOSTS` falls through to `*` even in the prod compose** (S9). | `docker-compose.prod.yml:62` |
| D8 | Low | **No arm64 image** (tectonic is x86_64-only) — unstated in DEPLOYMENT.md. | `Dockerfile.prod:56` |
| D9 | Low | **No automated backup** beyond git history and pre-update tags; tags cover project repos only, never `users.yaml`/secret. Manual tarball procedure is well documented. | `scripts/updater/updater.py:220-231` |
| D10 | Low | **Installer via `curl | bash`** — TLS + `bash -n` + pinned ref, no checksums (acknowledged in comments); acceptable risk. | `DEPLOYMENT.md:85` |

**Portability matrix**

| Target | Web | Desktop |
| --- | --- | --- |
| Linux x86_64 | Primary, tested, hardened (Docker or systemd installer) | Packaging config exists but broken (D1) |
| Linux arm64 | Manual only — no image | None |
| macOS | None (installer requires systemd) | Dev via `start.sh` only |
| Windows | None (bash installers) | Code-path only (`Scripts/python.exe`, kill degradation); no packaging, CI, or docs |

### 4.6 Testing & engineering process

| # | Severity | Finding | Location |
| --- | --- | --- | --- |
| T1 | Medium | **No static type checking for the backend** — no mypy/pyright anywhere. A 27k-LOC FastAPI/Pydantic codebase whose models are the contract, validated only at runtime. | `backend/requirements-dev.txt` |
| T2 | Medium | **No coverage measurement** — nothing tells you where the holes are in 1,936 tests. | — |
| T3 | Medium | **Desktop shell ships a runtime with 12 known advisories** (11 high, 1 critical; electron 31 / electron-builder 24) — deliberately non-gating, surfaced in every security run. It ships to users as the actual runtime; needs a date-bound migration issue. | `.github/workflows/security.yml:102-117` |
| T4 | Low | **E2e job fragility** — 78 specs, ~18 min on 2 workers against a 30-min cap; `playwright install --with-deps` hits apt mirrors every run (the known 5h59m hang); no browser cache. | `.github/workflows/ci.yml:150-160` |
| T5 | Low | **Backend deps pinned but not hash-pinned** (no `--require-hashes`). | `backend/requirements.txt` |
| T6 | Low | **No shellcheck in CI** for the installer scripts (behavior-tested, never statically linted). | — |
| T7 | Low | **No SBOM, image signing (cosign), or SLSA provenance** in releases — notable given the otherwise strong supply-chain posture. | `.github/workflows/release.yml` |

---

## 5. Prioritized recommendations

**Top 10, roughly in order of impact:**

1. **Close the read-authorization gap (S1, S2).** Add a `require_view(project_id)`
   dependency honoring the permissions map and apply it to project-scoped GET
   routes, starting with `publish/download`. If global reads are deliberate,
   state that in SECURITY.md — but then the permission tiers are misleading.
2. **Require the current password for password/email changes (S3).**
3. **Make the update chain verifiable end-to-end (S4, D2).** Sign releases
   (cosign keyless for images, Ed25519 for bundles), pin image digests in the
   updater, and default `RT_UPDATE_PUBLIC_KEY` to required with an explicit
   opt-out.
4. **Decide the desktop product question (D1).** Either bundle the backend and
   add a CI job that builds and boots the packaged artifact, or remove the
   packaging config so nobody ships a broken binary. Either way, fix
   `isQuiting`/`RT_PORT` validation while there.
5. **Make multi-worker failure loud (C3, D3).** Refuse `--workers > 1` at
   startup with an explanatory error until the shared-state story exists; add
   a threading-based lock fallback for Windows (C4) so the desktop path is not
   silently unserialized.
6. **Add a per-project write lock for composite operations (C1, C2).** One RW
   lock (async or file-based) per project around rename/reparent/cascade/
   import-replace and guard+delete closes the interleaving and TOCTOU holes.
7. **Mirror the store's fsync discipline in `save_users` (C5)** and treat
   unmarked non-empty data roots as legacy schema 1 rather than current (C6).
8. **Generate the frontend read models too (M1).** Extend the
   gen-and-diff-in-CI discipline from write models to read models (OpenAPI →
   typed client) so the contract cannot drift silently.
9. **Break the refetch/relayout amplification (M3).** Skip the publishing
   client in the SSE broadcast (the bus already tracks client identity), or
   debounce `loadData`; this matters most at the 2,000-entity cap.
10. **Introduce a write-maintained list index (P1) if >5k-entity projects are
    a target** — otherwise state the ~5k comfort ceiling in the docs so it is
    a product decision, not a surprise.

**Also worth doing:** mypy on `backend/app/services/` (T1); pytest-cov with a
floor (T2); replace the hand-rolled sanitizer with DOMPurify or pin an XSS
test matrix (M8); exponential backoff + jitter on SSE reconnect (M7); delete
dead store fields and use selector subscriptions (M6); split `GraphPane`/
`RequirementDetailPage`/`client.ts` (M2); hash-pin requirements (T5); publish
an SBOM (T7); date-bounded electron upgrade (T3); drop
`chunked_transfer_encoding off` from nginx (D4); add health-check + rollback to
the Docker updater (D5); fix the docs drift (D6).

---

## 6. Overall assessment

reqmesh is one of the more carefully engineered small-team tools this reviewer
has seen. Its two hardest problems — filesystem persistence with git-native
versioning, and a three-way contract (Pydantic ↔ JSON Schema ↔ TypeScript) —
are handled with genuine rigor: atomic durable writes, cross-process locks,
read-side validation of hand-editable data, a single link registry, and
CI-gated schema generation. The security posture is defense-in-depth at the
layers people usually forget (CSRF middleware, four-layer XSS defense,
credential redaction, XXE refusal, secret-hygiene in installers), and the test
culture — 3,000+ tests including a property-based contract suite with
anti-shrinkage floors and workflows that test themselves — is exceptional.

The gaps are concentrated, not scattered, and mostly follow from deliberate
posture choices that have outgrown their assumptions: the single-process
collaboration model (fine for desktop, binding for web), the global-read
authorization model (fine for one team, wrong for multi-project instances),
the unsigned update chain (fine for a hobby tool, wrong for a product with a
deployment story), and the vestigial desktop packaging (which has not kept up
with the architecture). The linear list-parse cost will cap data growth well
before anything else degrades. None of these require re-platforming; they
require a decision per item — and the codebase's own audit trail
(`docs/internal/AUDIT.md`, `HOUSEKEEPING-*.md`) shows that is a rhythm this
project already practices.

---

## Appendix: key metrics

| Metric | Value |
| --- | --- |
| Backend LOC (app + tests) | ~27k + ~27k |
| Frontend source files / LOC | 144 TS/TSX / ~37k |
| Largest frontend files | `GraphPane.tsx` 2,626 · `RequirementDetailPage.tsx` 1,826 · `client.ts` 1,717 |
| Backend tests | 2,137 collected (1,936 fast + 199 contract + 2 bench) |
| Frontend unit tests | 624 across 58 files (1.5 s) |
| Playwright e2e | 258 tests across 78 specs (incl. 4 a11y specs, auth-required variant) |
| CI jobs | 8 (lint, backend, contract, frontend, desktop, deploy-checks, e2e, schema-freshness) |
| Security tooling | CodeQL, semgrep, bandit, gitleaks, pip-audit ×2, npm audit, trivy, Dependabot |
| Bundle | main 307 KB · editor 403 KB · charts 301 KB · graph 259 KB · elk 1.44 MB + worker 1.43 MB (both lazy) |
