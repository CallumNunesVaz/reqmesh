
# reqmesh — Refinement Roadmap

This document captures every refinement opportunity identified in the
comprehensive codebase review. Items are grouped by priority with clear
ownership (backend service, API route, frontend component, config, or auth).

**Status legend:** ✅ done · 🔨 proposed · ⚡ quick win

---

## CRITICAL — Security & Correctness

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

---

## HIGH — Missing Features & Robustness

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

---

## MEDIUM — Polish & Completeness

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

---

## LOW — Nice-to-Have

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

---

## Suggested sequencing

1. **CRITICAL #1–5, #7** — security fixes (S effort, immediate)
2. **CRITICAL #10** — atomic user file writes (S effort)
3. **HIGH #19, #28–29, #34, #39** — pagination + UI fixes + quality linter (M/S effort)
4. **CRITICAL #6, #8** — token revocation + auth audit (M effort)
5. **HIGH #12, #14, #22, #25–27, #32** — auth flows + CSV + tracing (S/M effort)
6. **HIGH #20–21, #30, #35** — audit trail + input validation + editor sanitization (M effort)
7. **MEDIUM #36–55** — polish pass (S/M effort, spread across sprints)
8. **LOW #58–71** — backlog
