# reqmesh — Roadmap & Refinement Tracking

The single source of truth for reqmesh's delivered feature phases, the active
refinement backlog, and design records for completed initiatives.

**Status legend:** ✅ done · 🔨 proposed · ⚡ quick win

---

## Feature phases

All eleven planned phases are delivered.

- [x] **Phase 1** — Core CRUD, YAML storage, React UI
- [x] **Phase 2** — Traceability & verification enhancements
- [x] **Phase 3** — ReqIF / SysML import & export
- [x] **Phase 4** — Git integration (auto-commit, history, hooks)
- [x] **Phase 5** — Real-time collaboration (SSE + presence)
- [x] **Phase 6** — Code & test traceability (coverage tag scanning, staleness)
- [x] **Phase 7** — Deep coverage & tracing (needs, shallow/deep, cycle detection)
- [x] **Phase 8** — Fingerprint-based review & change control
- [x] **Phase 9** — Requirement quality linting
- [x] **Phase 10** — Planning & estimation (effort, per-stakeholder priority, backlog)
- [x] **Phase 11** — CSV / TSV / XLSX interchange + custom attribute schema

---

## Refinement backlog

Every refinement opportunity identified in the comprehensive codebase review,
grouped by priority with clear ownership (backend service, API route, frontend
component, config, or auth).

### CRITICAL — Security & Correctness

| # | What | Where | Effort |
|---|------|-------|--------|
| 1 | SSE auth — extract user/role from JWT, not query params | `extra_routes.py:project_events` | S |
| 2 | Default admin password must not be literal `"admin"` | `core/auth.py:load_users` | S |
| 3 | Rate limiting on `POST /auth/login` (5/min/IP) | `auth_routes.py` + `config.py` | S |
| 4 | Fix undefined `store` variable in `update_change_request` email block | `extra_routes.py:~59` | S |
| 5 | File upload size limit on `import_project` | `extra_routes.py` + `config.py` | S |
| 6 | Token revocation — add `token_version` per user | `auth.py` + `config.py` | M |
| 7 | Validate `code_root` in `scan_code` — restrict to project tree | `extra_routes.py:scan_code` | S |
| 8 | Auth audit trail — log logins, failures, role changes | `auth_routes.py` + `history.py` | M |
| 9 | User existence check in `get_user_from_token` | `core/auth.py` | S |
| 10 | Atomic `save_users` (mkstemp + os.replace) | `core/auth.py` | S |
| 11 | `smtp_password` → `SecretStr` to prevent log leakage | `core/config.py` | S |

### HIGH — Missing Features & Robustness

| # | What | Where | Effort |
|---|------|-------|--------|
| 12 | Password reset flow (forgot/reset via email) | `auth_routes.py` + `email_service.py` | M |
| 13 | Self-service password change (`PUT /auth/password`) | `auth_routes.py` | S |
| 14 | Email verification on registration | `auth_routes.py` + `config.py` | M |
| 15 | Stronger password policy (mixed case + digit + special) | `auth_routes.py` + `core/auth.py` | S |
| 16 | Concurrent write safety — advisory file locking on update | `yaml_store.py` | M |
| 17 | Corrupt YAML — log and skip instead of crashing list | `yaml_store.py` | S |
| 18 | `_write_yaml` exception handler `UnboundLocalError` fix | `yaml_store.py` | S |
| 19 | Pagination on all list endpoints (`?offset=&limit=`) | `router.py`, `extra_routes.py`, `component_routes.py` | M |
| 20 | Audit trail for components, specs, VCs, CRs, risks, decisions | `component_routes.py`, `extra_routes.py`, `router.py` | M |
| 21 | Pydantic models for raw `dict` inputs (4 endpoints) | `router.py` | M |
| 22 | Comment resolution — `PATCH /comments/{id}` | `extra_routes.py` | S |
| 23 | Coverage type namespace — normalize needs vs coverage types | `tracing.py` | M |
| 24 | Unify suspect-link systems — remove orphaned `_suspect.yaml` | `integrity.py` + `fingerprint.py` | S |
| 25 | CSV import column alias mapping | `table_io.py` | S |
| 26 | `import_table` replace-mode dry-run + warning | `table_io.py` + `extra_routes.py` | S |
| 27 | `deep_status` recursion depth guard (max 1000) | `tracing.py` | S |
| 28 | Surface `needs` and `priorities` fields in RequirementDetailPage | `RequirementDetailPage.tsx` | S |
| 29 | Metrics dashboard drill-down (EntityLinks on all IDs) | `MetricsPage.tsx` | S |
| 30 | Error feedback on failed saves (toast/red flash) | `RequirementDetailPage.tsx` | S |
| 31 | ComponentsPage dirty-state detection + unsaved-changes warning | `ComponentsPage.tsx` | S |
| 32 | Auto-fill measurement unit from selected parameter | `VerificationPage.tsx` | S |
| 33 | Comments + Decisions sections in RequirementDetailPage | `RequirementDetailPage.tsx` | M |
| 34 | Save-on-keystroke → debounce or save-on-blur for free-text fields | `RequirementDetailPage.tsx` | S |
| 35 | Paste sanitization in RichTextEditor (Word/Google Docs) | `RichTextEditor.tsx` | S |

### MEDIUM — Polish & Completeness

| # | What | Where | Effort |
|---|------|-------|--------|
| 36 | Fingerprint `_canonical` normalize missing vs empty lists | `fingerprint.py` | S |
| 37 | NORMATIVE_FIELDS make configurable via `_meta.yaml` | `fingerprint.py` + `yaml_store.py` | S |
| 38 | Weak-word regexes pre-compile at module load | `quality.py` | S |
| 39 | HTML entity decoding in quality linter (`html.unescape`) | `quality.py` | S |
| 40 | Coverage API — remove duplicate endpoint or differentiate | `extra_routes.py` | S |
| 41 | `project_metrics` deduplicate effort keys | `extra_routes.py` | S |
| 42 | `ParametricsGuide` font size too small (text-[9px] → text-[10px]) | `ParametricsGuide.tsx` | S |
| 43 | Command palette fuzzy matching (tolerate missing spaces) | `entityIndex.ts` | M |
| 44 | Command palette body scroll lock when open | `CommandPalette.tsx` | S |
| 45 | Missing config settings (max_upload_size, token TTL, log level) | `core/config.py` | S |
| 46 | Consistent Pydantic models for all inputs (Baseline, ProjectCreate) | `router.py` + `models/` | M |
| 47 | Component-to-component relations and trace links | `component.py` + routes | L |
| 48 | Extract shared `_build_tree` to `core/tree_utils.py` | `router.py` + `component_routes.py` | S |
| 49 | Global exception handler (no stack traces in prod) | `main.py` | S |
| 50 | Request logging middleware (method, path, status, duration) | `main.py` | S |
| 51 | GZip compression middleware | `main.py` | S |
| 52 | Security headers middleware | `main.py` | S |
| 53 | SPA dotfile exclusion | `main.py` | S |
| 54 | No `[[entity-id]]` TipTap extension for in-editor linking | `RichTextEditor.tsx` | M |
| 55 | XLSX import (currently export-only) | `table_io.py` | M |
| 56 | Bulk status change on verification cases | `VerificationPage.tsx` | S |
| 57 | "Run Test" loading state + feedback | `VerificationPage.tsx` | S |

### LOW — Nice-to-Have

| # | What | Where | Effort |
|---|------|-------|--------|
| 58 | WebSocket as SSE alternative | `extra_routes.py` | M |
| 59 | Burndown/time-trend charts on metrics | `MetricsPage.tsx` | M |
| 60 | Image support in RichTextEditor | `RichTextEditor.tsx` | S |
| 61 | Keyboard navigation in component tree | `ComponentsPage.tsx` | S |
| 62 | Search highlighting in command palette results | `CommandPalette.tsx` | S |
| 63 | Recently-visited boost in command palette ranking | `entityIndex.ts` | S |
| 64 | Word/character counter in RichTextEditor footer | `RichTextEditor.tsx` | S |
| 65 | Constraint reordering in parametrics card | `parametrics.tsx` | S |
| 66 | API key support for CI/CD automation | `auth.py` + `auth_routes.py` | M |
| 67 | OpenAPI docs enrichment (contact, license, tags) | `main.py` | S |
| 68 | Component export (bill of materials, indented parts list) | `component_routes.py` | M |
| 69 | Add `Baseline` Pydantic model + schema generation | `models/` + `gen_schemas.py` | S |
| 70 | Dependency pinning — exact versions + hashes | `requirements.txt` | S |
| 71 | Dependency pinning — split `requirements-dev.txt` | `requirements-dev.txt` | S |

### Suggested sequencing

1. **CRITICAL #1–5, #7** — security fixes (S effort, immediate)
2. **CRITICAL #10** — atomic user file writes (S effort)
3. **HIGH #19, #28–29, #34, #39** — pagination + UI fixes + quality linter (M/S effort)
4. **CRITICAL #6, #8** — token revocation + auth audit (M effort)
5. **HIGH #12, #14, #22, #25–27, #32** — auth flows + CSV + tracing (S/M effort)
6. **HIGH #20–21, #30, #35** — audit trail + input validation + editor sanitization (M effort)
7. **MEDIUM #36–55** — polish pass (S/M effort, spread across sprints)
8. **LOW #58–71** — backlog

---

## Completed initiatives

Design records for delivered multi-slice initiatives. Full implementation-level
detail lives in git history; the summaries below capture intent and outcome.

### Parametrics → SysML v2 alignment — ✅ IMPLEMENTED (2026-07-21)

All four slices, the GUI data-entry updates, the Cessna demo examples, and
documentation shipped and were verified (backend + frontend suites, typecheck,
build, e2e).

**Context.** reqmesh's parametric modelling was SysML v2-*inspired* but not
conformant: a bespoke, accessible engine (`backend/app/services/evaluation.py`)
evaluates free-text expressions over a flat `ENTITY.param` namespace and produces
rich verdicts (pass/fail/unknown/not_applicable/error), margins, rollups, and
verification-measured verdicts. The chosen direction was **"keep the engine,
SysML-ify the representation"** — deliberately additive, removing no computed
capability. "Nothing is lost" guarantees: unknown/free-text units skip checking;
inline `expr` constraints stay valid alongside definition-based ones; `MeasureKind`
(MOE/MOP/TPM) preserved as SysML `metadata`; `rollup()`, cross-entity refs, verdict
taxonomy, and measured verdicts untouched; all new model fields `Optional` with
defaults, so existing YAML loads unchanged with no data migration.

- **Slice 1 — Round-trip parametrics in the SysML v2 interchange.** `sysml_export.py`
  now emits parameters (`attribute name = value [unit]` / derived exprs),
  constraints (`require`/`assume constraint { … }`), `MeasureKind` metadata, and
  components as `part def` blocks with `satisfy requirement`; `sysml_import.py`
  parses them back. Verified via byte-equivalent export→import→re-evaluate.
- **Slice 2 — Value types + units with dimensional checking.** New
  `backend/app/services/units.py` (SI 7-dim registry, `dimension_of`, `compatible`,
  `combine`, `to_base`); optional `value_type` on `Parameter`; a separate,
  non-fatal dimension pass in the evaluator that attaches `unit_warning` without
  changing verdicts; frontend surfaces warnings + unit autocomplete.
- **Slice 3 — Reusable constraint def / calc def (with binding).** New
  `models/definition.py` (`ConstraintDef`, `CalcDef`); `Constraint`/`Parameter`
  gain optional `def`/`calc` + `bindings`; a `definitions` collection with CRUD
  under `/projects/{id}/definitions`; evaluator resolves bound formals reusing
  existing cycle protection; a small Definitions manager in the UI.
- **Slice 4 — Analysis cases + assume/require formalization.** `subject` on
  `Requirement` (exported/imported); `AnalysisCase{ scope, overrides }` evaluated
  by reusing `Evaluator(overrides=…)`, exposed at `GET /projects/{id}/analysis/{caseId}`
  and stored in an `analysis_cases` collection; a scoped analysis-case runner in
  the UI.

**Cross-cutting.** Every new field optional/defaulted; evaluator changes additive;
no data migration required; `demo_seed.py` (Cessna) extended with typed-unit
parameters, a shared `ConstraintDef`, and an analysis case as living examples.
