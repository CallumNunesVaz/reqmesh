# reqmesh Design Principles Compliance Review

**Project:** reqmesh v0.1.17
**Original review:** August 2026
**Verification pass:** Claude, August 2026 — every finding below was checked against the code; corrections are marked **[CORRECTED]**, **[WITHDRAWN]** or **[ADDED]**.

---

## What this pass changed

The original review is structurally sound: the architectural criticisms (monster
files, no format registry, no storage interface, file-per-entity scaling) are
accurate and well-targeted, and the file-size figures are exact. Six specific
findings did not survive verification, and one real bug was missed.

| # | Original claim | Verdict |
|---|---|---|
| 1 | **High** — `_read_yaml` *silently* returns `{}` on corrupt files, "bypassing 404 checks and allowing downstream consumption of garbage data" | **[CORRECTED]** → Low. Not silent, and no route serves garbage. See §1. |
| 2 | **Medium** — Missing `safe_id` on CR/Risk/Decision creation, "bad ID results in 500 rather than clean 400" | **[WITHDRAWN]** — all three return a clean 400. See §3. |
| 3 | **Low** — `except BaseException` is "unnecessary" | **[WITHDRAWN]** — it is the correct choice there. See §1. |
| 4 | **Low** — `refocusGraph` is dead code, "zero references anywhere" | **[WITHDRAWN]** — five references in `GraphPane.tsx`. |
| 5 | "No optimistic updates" | **[CORRECTED]** — overstated; some exist. See §13. |
| 6 | 598 tests across 48 files | **[CORRECTED]** — 538 functions / 771 collected across 50 files. |
| 7 | — | **[ADDED]** Rationale is published as escaped literal markup. See §1. |

Scores adjusted accordingly: **Reliable 6 → 7**, **Robust 7 → 7** (composition
changed), **Testable 5 → 6**. All others stand.

Verification method: findings were reproduced against a running instance
(`TestClient` for API behaviour, a real publish for the rendering bug, `grep`
for the reference counts). Claims about design *judgement* — "god object",
"no abstraction layer" — are opinions I largely agree with and did not attempt
to falsify.

---

## Summary Table

| Principle | Score | Assessment |
|-----------|-------|------------|
| Clean | 8/10 | Exceptional documentation. Minor naming collisions. Very readable codebase overall. |
| Secure | 7/10 | Strong fundamentals — bcrypt, CSP, CSRF, allowlist sanitization. A few actionable gaps. |
| Robust | 7/10 | Strong input validation, especially path traversal. Bulk operations remain unvalidated. |
| Reliable | 7/10 | Corrupt-file handling is better than first assessed. Two real frontend defects. |
| Decoupled | 6/10 | No circular imports. Cross-cutting violations and a scheduler embedded in `main.py`. |
| Testable | 6/10 | 771 tests with genuine isolation. Key services still untested. |
| Maintainable | 5/10 | Several monster files (extra_routes 1665L, publisher 2200L, GraphPane 2270L) and duplication. |
| Modular | 5/10 | Good `core/` separation but the main extra-routes file is a dumping ground. |
| Efficient | 4/10 | Full directory scans on cache misses, no search index, no streaming for large reports. |
| Scalable | 3/10 | File-per-entity storage degrades linearly. In-memory rate limits. No pagination on analysis endpoints. |
| Extensible | 3/10 | No API versioning, no format registry, no auth/storage interfaces. |

---

## 1. Reliable — Runs without errors and gives correct results every time

**Score: 7/10** *(was 6/10 — the headline High did not hold)*

### Strengths

- Global `@app.exception_handler(Exception)` returns structured 500s; debug mode gates whether raw exception strings leak. (`main.py:474-485`)
- Email notification failures never break primary writes — each is wrapped in `try/except Exception: logger.exception(...)`.
- File-level advisory locking (`fcntl.flock`) protects read-modify-write cycles. (`core/filelock.py:21-42`)
- Cascade propagation uses BFS with a `seen` set. (`api/router.py:518-553`)
- Parent-cycle detection for reparenting is thorough and correct. (`api/router.py:490-504`)
- **[ADDED]** Corrupt entity files are handled deliberately and well — see the correction below. `_read_collection` skips them, records them, and `corrupt_files()` surfaces them through `/validate` as `corrupt_file`. This is better than most codebases manage.

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Critical** | No React Error Boundary anywhere in the tree — a crash in any component unmounts the whole app. **Verified**: zero matches for `componentDidCatch` / `getDerivedStateFromError` / `ErrorBoundary` in `frontend/src`. | Frontend |
| **High** | Permanent loading spinner on fetch failure — `setLoading(false)` is called only in `.then()`; the `.catch()` just `console.error`s. **Verified** at `RequirementDetailPage.tsx:255` (review said 256). | `pages/RequirementDetailPage.tsx:255` |
| **High** | **[ADDED]** Rationale is published as escaped literal markup. `description` is `sanitize_html()`'d and emitted as HTML; `rationale` is `esc()`'d. Since Rationale became a rich-text editor, every HTML report renders it as raw tags. **Verified** — a rationale of `<p>Rationale with <strong>bold</strong></p>` publishes as `&lt;p&gt;Rationale with &lt;strong&gt;bold&lt;/strong&gt;&lt;/p&gt;` while the description beside it renders formatted. | `services/publisher.py:632` vs `:644` |
| **Medium** | Race condition in git autocommit counters — `_git_change_counts` incremented outside the `asyncio.Lock`. | `main.py:440-442` |
| **Medium** | `break_cascade` writes the full requirement dict back — concurrent edits to unrelated fields are lost. | `api/router.py:613-614` |
| **Low** | **[CORRECTED]** `get_item` returns `{}` rather than `None` for a corrupt file. The original filed this as **High**, claiming it is *silent* and lets garbage reach consumers. Neither holds: `_read_yaml` logs at WARNING, and every reachable path is guarded — a corrupt entity is skipped from lists, `GET` a corrupt requirement returns **404**, `PUT` returns **409 naming the offending file**, and `/validate` reports `corrupt_file`. What remains is an internal inconsistency: `_read_yaml`'s own docstring says "Never use this for entity files", and `get_item` uses it for every non-requirement entity. A latent trap for the next caller, not a live defect. | `services/yaml_store.py:295` |
| **Low** | Silent `except Exception: continue` in `entity_backlinks` obscures real storage errors as 404. *(Mine — the intent was tolerating collections that don't exist in older projects, but it swallows too much.)* | `api/extra_routes.py:729-730` |
| **Low** | `_dir_signature` returns `()` on OSError — the directory becomes uncacheable with no log line. | `services/yaml_store.py:63-64` |
| ~~Low~~ | **[WITHDRAWN]** ~~`except BaseException` in the download handler is unnecessary~~ — it unlinks a temp file and then `raise`s. Catching `BaseException` is *correct* here: on `KeyboardInterrupt` you still want the partial export removed. Narrowing it to `Exception` would leak files on shutdown. | `api/extra_routes.py:1059` |

---

## 2. Maintainable — Easy for developers to update, fix, and read

**Score: 5/10** — unchanged. All file sizes verified exact.

### Strengths

- Consistent 3-model pattern per entity (Entity, EntityCreate, EntityUpdate).
- Class-based test grouping with descriptive names.
- Zustand stores segmented by concern (app, auth, undo).
- Custom hooks extract cross-cutting logic (`usePersistedState`, `useKeyboardShortcuts`, `useFocusedEntity`).

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Critical** | `extra_routes.py` — **1665 lines verified**, 15+ distinct concerns (change requests, risks, comments, decisions, bulk ops, publishing, import/export, SSE, search). | `api/extra_routes.py` |
| **Critical** | `publisher.py` — **2200 lines verified**, HTML + Markdown + LaTeX + PDF in one class. | `services/publisher.py` |
| **Critical** | `GraphPane.tsx` — **2270 lines verified**, ReactFlow + force simulation + orthogonal routing + semantic zoom + filtering + minimap + ELK + shortcuts + filter bar. | `components/GraphPane.tsx` |
| **High** | 7 bulk-update endpoints with identical structure, ~300 lines of duplication. | `api/extra_routes.py:338-549` |
| **High** | Email notification try/except duplicated 8 times in one file. | `api/extra_routes.py` |
| **High** | Git autocommit scheduling (230+ lines) embedded in `main.py` rather than a service. | `main.py:216-465` |
| **Medium** | Pagination offset/limit logic duplicated 10+ times. | Both route files |
| **Medium** | `BaselineCreate` defined twice with different shapes. | `api/router.py:93`, `models/baseline.py:13` |
| **Medium** | Cycle detection duplicated with two different implementations. | `api/router.py:490` vs `api/component_routes.py:27` |

---

## 3. Robust — Handles unexpected problems or bad inputs without crashing

**Score: 7/10** — unchanged, but one finding withdrawn and one strength corrected.

### Strengths

- `safe_id()` blocks traversal (`..`, `/`, `\`) and double-percent-decode (`%252e%252e%252f`). (`core/ids.py:1-18`)
- Expression evaluator uses an AST walker with a strict whitelist — no `eval()`. (`services/evaluation.py:160-235`)
- ReqIF import strips `<!DOCTYPE` before parsing. (`services/reqif_import.py:24`)
- All `subprocess.run` calls use list arguments, never `shell=True`. (`services/git_service.py`)
- `resolve().is_relative_to(data_root)` defends against symlink escapes. (`main.py:399-401`)
- HTML sanitization is allowlist-only — 16 tags, dangerous elements dropped with their content. (`services/sanitize.py:32-40`)
- **[ADDED]** The frontend's rich-text *renderer* is safe by construction: `AutoLinkHtml` parses with `DOMParser` (inert) and `nodeToReact` copies **no attributes at all**, allowlisting tags and dropping the rest to Fragments. Stored `onerror`/`javascript:` cannot survive rendering regardless of what reaches the database. Worth stating explicitly, because it is what makes the unsanitized `rationale` field a rendering bug rather than a stored-XSS hole.

> **[CORRECTED]** The original listed "YAML bomb risk: no timeout on YAML parsing" under *Strengths*. It is a finding, not a strength — moved to the table below.

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Medium** | Bulk operations accept raw `dict` with no Pydantic structural validation. | `api/extra_routes.py:340,363,389` |
| **Medium** | **[MOVED]** No timeout on YAML parsing — a pathological hand-edited file can hold the global parse mutex. | `services/yaml_store.py:34` |
| **Low-Medium** | Non-requirement entity types lack collection-specific structural validation on load. | `services/load_guard.py:99-101` |
| **Low** | Content-Length check applies only to `application/json`; multipart bypasses it (mitigated by separate upload limits). | `main.py:127-138` |
| **Low** | IDs allow `.` — harmless on Linux, confusing on Windows. | `core/ids.py:9` |
| ~~Medium~~ | **[WITHDRAWN]** ~~Missing `safe_id` on Change Request / Risk / Decision creation; bad IDs yield 500 rather than 400.~~ **Verified false.** `_item_path` calls `safe_id` on every collection, so all three return a clean **400** with `Invalid id: '../../etc/passwd'`. Adding a route-level call would be defence in depth, not a fix — the behaviour the finding predicts does not occur. | `api/extra_routes.py:91,173,301` |

---

## 4. Efficient — Uses low CPU, memory, and network power

**Score: 4/10** — unchanged. Findings accepted as written; these are design-level
and match what I saw while working in the code.

### Strengths

- Two-parser strategy: round-trip parser for mutations, fast parser for reads (~6.5x). (`services/yaml_store.py:36-42`)
- Atomic writes: `mkstemp` + `os.replace` + `fsync` on file and directory. (`services/yaml_store.py:147-176`)
- Deep copy on cache hit prevents cache poisoning. (`services/yaml_store.py:221`)
- SSE queue bounded at 256. (`services/event_bus.py:28`)
- Vite `manualChunks` splits graph, charts, editor, motion, React. (`vite.config.ts:17-24`)
- `elkjs` dynamically imported. (`GraphPane.tsx:194`)

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **High** | `invalidate_cache()` drops the entire collection on every write — each mutation forces a full directory re-read. | `services/yaml_store.py:151` |
| **High** | `list_all_history()` reads every history file with no index or date filtering. | `services/yaml_store.py:474-504` |
| **High** | Project search scans all 11 collections per query — no index, no result cache. | `services/search.py:81-260` |
| **High** | Reports built in memory by string concatenation — no streaming. | `services/publisher.py:890-982` |
| **High** | No route-level lazy loading — all pages bundled eagerly. | `App.tsx` |
| **Medium** | `_identity_for()` builds a new YamlStore and re-reads `_meta.yaml` per git subprocess call. | `services/git_service.py:103-134` |
| **Medium** | Double JWT decode per authenticated request. | `main.py:157-179` |
| **Medium** | Git autocommit middleware re-reads `_meta.yaml` twice per mutating request. | `main.py:378-471` |
| **Medium** | `data:image` base64 in rich text has no size limit. | `services/sanitize.py:44,58` |
| **Low** | Global YAML mutex serializes parsing across all projects and threads. | `services/yaml_store.py:34,42` |
| **Low** | Lock files never cleaned from `/tmp/reqmesh-locks/`. | `core/filelock.py:35-36` |

---

## 5. Scalable — Grows smoothly to handle more data or users

**Score: 3/10** — unchanged, one finding contextualised.

### Strengths

- Signature-based cache invalidation (`(name, mtime_ns, st_size)` per file). (`services/yaml_store.py:44-73`)
- SSE connection limits — 100 global, 5 per user. (`api/extra_routes.py:1372-1390`)
- Offset/limit pagination on key endpoints (requirements: default 500, max 2000).
- Presence pruning with a 300s TTL. (`services/event_bus.py:76-107`)

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **High** | File-per-entity storage with full directory scans on cache miss — linear degradation. | `services/yaml_store.py:210-226` |
| **Medium** | **[CORRECTED]** Rate limiting is in-memory per-worker and lost on restart. The original's "4 workers = 4x the allowed rate" is hypothetical: `Dockerfile.prod` runs `--workers 1`, so the limits are currently correct in the shipped deployment. The finding is real as a *constraint* — the app cannot be scaled horizontally without a shared store — rather than as a live defect. | `core/rate_limit.py:6-7` |
| **Medium** | Abandoned SSE subscriber queues never cleaned up. | `services/event_bus.py:32-35` |
| **Medium** | No WebSocket connection limit, where SSE has one. | `services/websocket_bus.py:18-24` |
| **Medium** | Full HTML report returned as a JSON string field — no streaming. | `api/extra_routes.py:991` |
| **Medium** | Pagination fallback reads and parses the whole collection before slicing. | `api/router.py:634-640` |
| **Medium** | Analysis endpoints (gap, coverage, conflicts, backlog, stakeholder value) return all items unpaginated. | `api/extra_routes.py:686-955` |
| **Low** | `rate_limit_auth` / `rate_limit_analysis` / `rate_limit_publish` config strings are defined and **never read** — verified: zero references outside `config.py`. Operator settings silently ignored. | `core/config.py:146-148` |

---

## 6. Secure — Protects private data and blocks cyber attacks

**Score: 7/10** — unchanged. Findings accepted.

### Strengths

- bcrypt with `gensalt()`; rejects >72 bytes; 12-char minimum with complexity. (`core/auth.py:143-148,190-192`)
- JWT HS256 with `iat`/`exp`, 7-day TTL, `tv` claim for global revocation. (`core/auth.py:159-167`)
- Account lockout with uniform 401s; unknown users get a dummy hash for timing normalization. (`core/auth.py:197-221`)
- Stateless double-submit CSRF compared with `secrets.compare_digest()`. (`main.py:193-213`)
- Allowlist-only HTML sanitization; strict image URI restrictions. (`services/sanitize.py:32-59`)
- WeasyPrint URL fetcher refuses all network/file access — `data:` only. (`services/sanitize.py:112-140`)
- Git remote scheme whitelist and credential redaction in logs. (`services/git_service.py`)
- Full security header set including CSP and HSTS. (`main.py:363-375`)
- CORS wildcard refused at startup — the app crashes rather than serving it. (`main.py:109-115`)

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Medium** | Unsanitized user text interpolated into email notification bodies — a user with edit access can inject tracking pixels or phishing links into mail sent to all project users. | `services/email_service.py:145,228-229` |
| **Medium** | `github_token` is plain `str`, not `SecretStr` (unlike `smtp_password`) — can leak in tracebacks. | `core/config.py:216` |
| **Medium** | `csrf_secret` is declared and **never used** — verified: zero references outside `config.py`. Operators setting `RT_CSRF_SECRET` get nothing. | `core/config.py:143` |
| **Medium** | No connection limit on the WebSocket handler. | `services/websocket_bus.py:18-24` |
| **Low** | Reset/verification tokens in URL query parameters — leak via history, Referer, and mail provider logs. | `services/email_service.py:207,309` |
| **Low** | Unused progressive lockout code never called. | `core/rate_limit.py:83-111` |
| **Low** | No JWT `jti` — sessions can only be revoked in bulk via `token_version`. | `core/auth.py:160-166` |
| **Info** | No `Cache-Control: no-store` on auth responses. | `api/auth_routes.py:68-86` |
| **Info** | No encryption at rest for secret files — `0o600` only. | `core/auth.py:29-32`, `core/settings_store.py:21` |

---

## 7. Modular — Built in separate, independent blocks

**Score: 5/10** — unchanged.

### Strengths

- `core/` deliberately isolated, with the boundary documented. (`core/filelock.py:4-5`)
- `link_registry.py` consolidates cross-entity relationship knowledge into one module.
- `component_routes.py` (218 lines) is the model example — clean and focused.
- Small focused services: `history.py` (31L), `delete_guard.py` (65L), `workflow.py` (57L), `stakeholder_value.py` (107L), `risk_matrix.py` (176L).

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Critical** | `extra_routes.py` — 1665 lines, 15+ concerns. | `api/extra_routes.py` |
| **Critical** | `publisher.py` — 2200-line god object. | `services/publisher.py` |
| **Medium** | `models/risk.py` holds Risk, Comment and DecisionRecord — three unrelated entities. | `models/risk.py` |
| **Medium** | Module-level mutable state in a route file (`_sse_lock`, `_sse_conns_by_user`, `_sse_conns_global`). | `api/extra_routes.py:1372-1374` |
| **Medium** | Model layer imports from the service layer (`sanitize_html`). | `models/requirement.py:17` |
| **Medium** | Cross-route import of `normalize_baseline_defs`. | `api/extra_routes.py:17` |

---

## 8. Clean — Simple to read with clear names and no clutter

**Score: 8/10** — unchanged, one finding withdrawn.

### Strengths

- Comments explain *why*, not *what* — edge cases, security reasoning and performance tradeoffs are documented throughout. This is the codebase's standout quality.
- Module docstrings explain design philosophy (`link_registry.py`, `load_guard.py`, `delete_guard.py`).
- Consistent 3-model Pydantic pattern across entity types.

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **Medium** | `BaselineCreate` defined with different shapes in two modules. | `api/router.py:93`, `models/baseline.py:13` |
| **Low** | Hardcoded CLI version `"0.4.0"` instead of `core/version.py` — **verified**, and it disagrees with the actual 0.1.17. | `cli.py:13` |
| **Low** | Unused imports (`patch`, `MagicMock`) in a test file. | `tests/test_deployment.py:3` |
| **Low** | Inconsistent import style — mid-file imports, logger between import blocks. | `api/extra_routes.py:17-23` |
| **Low** | Leading underscore on `_bumpVersions` in the undo store. | `store/undo.ts:27` |
| ~~Low~~ | **[WITHDRAWN]** ~~Dead code: `refocusGraph` has zero references anywhere in the codebase.~~ **Verified false.** It has five references in `GraphPane.tsx` (647, 649, 657, 658, 665) implementing re-centre-on-change, and is written by `bumpGraphVersion` in `store/index.ts:64`. Deleting it on this advice would have broken graph refocusing. | `store/index.ts:14` |

---

## 9. Testable — Easy to check with automated scripts

**Score: 6/10** *(was 5/10 — the volume was understated and isolation is better than credited)*

### Strengths

- **[CORRECTED]** **538 test functions across 50 files, 771 tests collected** (the gap is parametrisation — `test_permissions.py` alone generates ~190 cases from the live route table). The original's "598 tests across 48 files" matches neither metric. Frontend: **99 tests across 11 files**.
- Strong isolation via `monkeypatch` — the workspace fixture provides isolated filesystem, auth and rate-limiter state.
- Dedicated security tests (XSS, CSRF, path traversal, git remote scheme restrictions).
- Destructive-import rollback test ensures a failed import never empties a project.
- Concurrency tests for lost updates, stale writes and cascade conflicts.
- No flaky tests: no `sleep`, no randomness; debounce set to 0.0 via `monkeypatch`.
- CI runs CodeQL, Semgrep, Bandit, pip-audit, npm audit, Gitleaks and Trivy.

### Findings

| Severity | Finding | Location |
|----------|---------|----------|
| **High** | No abstraction over external dependencies — no protocols for email, git, HTTP or subprocess; everything is `monkeypatch`ed against concrete implementations. *(Agreed, with one caveat: the parametrised route-table tests are the opposite of fragile — they bind to the live app object and caught a real regression when the router internals changed.)* | `email_service.py`, `git_service.py`, `updater.py` |
| **Medium** | WebSocket layer has zero tests. | `websocket_bus.py` |
| **Medium** | Email formatting/sending untested. | `email_service.py:133-232` |
| **Medium** | Publisher pipeline (~1500 lines of HTML/LaTeX/PDF) untested beyond changelog collection. **This is why the rationale-escaping bug in §1 shipped unnoticed.** | `publisher.py:853-2188` |
| **Medium** | Migration system never exercised — `MIGRATIONS` registry is empty. | `migrations.py:29` |
| **Medium** | Pervasive `any` in frontend catch blocks and API calls. | Frontend |
| **Low** | No contributor/maintainer client fixtures — only admin and guest. | `tests/conftest.py` |
| **Low** | No component-level frontend tests. | Frontend |

---

## 10. Extensible — Ready to accept new features without rewriting

**Score: 3/10** — unchanged. Findings accepted.

| Severity | Finding | Location |
|----------|---------|----------|
| **High** | No API versioning — no `/api/v1/`, no deprecation policy. | All routes |
| **High** | Import format detection is a hardcoded if/elif chain. | `services/importer.py:176-198` |
| **High** | No export format abstraction — rendering hardcoded in `Publisher`. | `services/publisher.py` |
| **Medium** | No authentication backend abstraction — JWT cookie/bearer only. | `core/auth.py` |
| **Medium** | No storage backend interface — hardcoded to YAML filesystem. | `services/yaml_store.py` |
| **Low** | `_HTML_FIELDS = ("description",)` is a single point of failure — **and it has already failed once**: `rationale` became a rich-text field without being added here, which is the root of the §1 publishing bug. Not merely a theoretical extensibility risk. | `services/load_guard.py:41` |

---

## 11. Decoupled — Low coupling between parts

**Score: 6/10** — unchanged.

| Severity | Finding | Location |
|----------|---------|----------|
| **High** | Git autocommit scheduling (230+ lines with global mutable state) embedded in `main.py`. | `main.py:216-465` |
| **Medium** | Model layer depends on service layer. | `models/requirement.py:17` |
| **Medium** | Cross-route imports between `extra_routes.py` and `router.py`. | `api/extra_routes.py:17` |
| **Medium** | Undo store reaches into the main store via `useStore.getState()`. | `store/undo.ts:27-30` |

---

## 12. Intuitive — Accessibility

Accepted as written. Only ~15 `aria-*` occurrences across ~25 interactive
components; colour-only status indicators; no skip-to-content link; icon-only
buttons relying on `title` alone; no keyboard navigation for graph nodes.

> Worth noting the `title`-only pattern has a second cost beyond accessibility:
> the sign-in control is an icon button whose only label is `title="Sign in"`,
> which is a large part of why a deployment requiring auth reads as "the app is
> broken" rather than "you need to log in".

---

## 13. Responsive — Reacts fast to user actions

**[CORRECTED]** — the blanket claim is overstated.

- ~~"No optimistic updates — all mutations follow: API call → reload entire dataset"~~ **Partly false.** `RisksPage` applies optimistic updates with explicit rollback on failure (`RisksPage.tsx:104-108, 119`), and `LinkEditor` mutations do the same. The pattern is *inconsistent*, not absent: most pages do reload wholesale, a few do not. The finding should be "optimistic updates are applied inconsistently", which is a maintainability problem rather than a performance one.
- No loading indicators for individual mutations — accepted.
- `listRequirements` silently truncates past 2000 — accepted, and worth raising: it returns `.items` at the server maximum with no signal that more exist.
- No request timeout or retry in the API client — accepted.
- `statCards` recreated per render without `useMemo` — accepted.

---

## 14. Seamless — No freezes or visual glitches

- **No Error Boundary** — confirmed, see §1.
- **Permanent spinner on fetch failure** — confirmed, see §1.
- `LoadingSplash` is well designed: 0.15s delay avoids flash on fast loads.
- SSE connections closed on unmount; alive-guard prevents post-unmount state updates.
- `beforeunload` listeners cleaned up properly.

---

## 15. Consistent — Uniform patterns and conventions

| Severity | Finding | Location |
|----------|---------|----------|
| **Medium** | Cycle detection implemented twice, differently. | `api/router.py:490` vs `api/component_routes.py:27` |
| **Medium** | Bulk endpoints accept raw `dict` while everything else uses typed models. | `api/extra_routes.py` |
| **Low** | `noUnusedLocals: false` lets dead imports accumulate. | `frontend/tsconfig.json:16` |
| **Low** | Inconsistent underscore conventions for module-level names in `main.py`. | `main.py:220-234` |

---

## Priority Recommendations

### Tier 1 — Real bugs, cheap to fix

1. **Add a React Error Boundary.** Confirmed absent; one crash white-screens the app.
2. **Move `setLoading(false)` into `.finally()`** in `RequirementDetailPage.tsx:255`.
3. **[ADDED] Fix rationale publishing.** Sanitize-and-emit it like `description`, and add `rationale` to `_HTML_FIELDS`. Rich text in rationale currently publishes as raw tags in every HTML report.
4. **Sanitize email notification bodies** — `html.escape()` user text in templates.
5. **Cap `data:image` size** in the sanitizer.
6. **Add WebSocket connection limits** mirroring the SSE ones.
7. **Delete or wire up the dead config** — `csrf_secret` and the three `rate_limit_*` strings are read by nothing, so operators setting them get silence.

> Deliberately *not* on this list: the original's Tier 1 item 1, "fix corrupted
> file silent failure". The behaviour it describes does not occur — see §1.
> Changing `_read_yaml` to return `None` or raise would alter the structural-file
> paths (`_meta.yaml`, traces, history) that legitimately rely on the `{}`
> fallback, in exchange for fixing nothing. If anything is done here, narrow it
> to `get_item`.

### Tier 2 — Architectural

8. Split `extra_routes.py` by concern.
9. Split `publisher.py` into per-format modules — this is also the prerequisite for testing it, which is how the rationale bug would have been caught.
10. Extract git autocommit from `main.py`.
11. Decompose `GraphPane.tsx`.
12. Add `/api/v1/` versioning and a deprecation policy.
13. Introduce protocols for email, storage, import/export and auth backends.

### Tier 3 — Performance and scalability

14. Per-file cache invalidation instead of dropping the collection.
15. Build a search index at collection-cache time.
16. Paginate the analysis endpoints.
17. `React.lazy()` + `<Suspense>` for route-level splitting.
18. Cache `_identity_for()` git identity lookups.

### Tier 4 — Quality

19. Generic bulk-update/bulk-delete utility.
20. Single `paginate()` helper.
21. `_safe_notify(fn, *args)` wrapper for the repeated email try/except.
22. Split `models/risk.py`.
23. Contributor and maintainer test fixtures.
24. Replace catch-block `any` with `unknown`.
