# reqmesh

<p align="center">
  <img src="media/reqmesh-logo.svg" alt="Reqmesh Logo" width="500">
</p>

An open-source, web-based requirements management tool with:

- **Git-native storage** — every entity is one human-readable YAML file; no databases or binary artifacts in your project directory
- **Version control native** — each project is a self-contained directory; auto-committed to git on every change, with optional push to a remote
- **Full audit trail** — field-level change history for requirements, components, specifications, and verification cases
- **Standards interchange** — import/export ReqIF 1.2, SysML v2, CSV, TSV, and XLSX (round-trips through all formats)
- **Real-time collaboration** — live change streaming over SSE with a presence roster of who's viewing each project
- **Design/function split** — components (the synthesised design) mapped onto the requirements they satisfy, with hierarchical budget rollups
- **SysML-style parametrics** — typed parameters, evaluable constraints, measured verdicts, margin computation — no SysML knowledge required
- **Deep traceability** — shallow and deep coverage analysis, code-to-requirement tag scanning, cycle detection via Tarjan's SCC
- **Fingerprint-based review** — content-hash auto-invalidates reviews when normative content changes; no manual bookkeeping
- **Quality linting** — inline requirement writing feedback (weak words, placeholders, measurability checks) based on INCOSE / EARS / ISO 29148
- **Planning & estimation** — per-stakeholder priority, story points, prioritized backlog
- **Rich text editing** — TipTap editor with image support, paste sanitization, and live word count
- **Guided mode** — toggleable contextual help for every section of the application

## Architecture

```
reqmesh/                    # THE TOOL (this repo)
├── backend/               # Python FastAPI (uvicorn)
│   ├── app/api/           # REST routes (auth, CRUD, analysis, publishing, import/export, SSE)
│   ├── app/core/          # Config, auth, dependencies, rate limiting, ID validation
│   ├── app/models/        # Pydantic models for all 10 entity types
│   ├── app/services/      # YAML store, integrity, tracing, fingerprint, evaluation,
│   │                      # code_scan, quality, table_io, email, publisher, workflow…
│   ├── tests/             # 163 integration + unit tests (pytest)
│   ├── gen_schemas.py     # JSON Schema generator
│   └── requirements.txt   # All deps pinned to exact versions
├── frontend/              # React 18 + TypeScript + Vite + TailwindCSS
│   ├── src/
│   │   ├── api/           # Typed API client
│   │   ├── components/    # Layout, nav, graph, editor, parametrics, helpers, palette…
│   │   ├── pages/         # 12 route pages (projects, requirements, components, metrics…)
│   │   └── store/         # Zustand state (auth, data, helpers toggle)
│   └── tests/             # 59 unit tests (vitest)
├── schemas/               # JSON Schemas for all project YAML formats
├── desktop/               # Electron shell for native desktop app
├── Dockerfile.prod        # Multi-stage production build
├── docker-compose.prod.yml # Single-origin production deployment
├── Caddyfile / nginx.conf # Reverse proxy configs with TLS
├── DEPLOYMENT.md          # Full server deployment guide
├── REFINEMENT_ROADMAP.md  # Comprehensive refinement tracking
└── ROADMAP.md             # Feature roadmap (phases 6–11)

<your-project>/            # YOUR DATA (separate, git-tracked)
├── _meta.yaml             # Project identity + workflow + quality config
├── requirements/          # One YAML per requirement
├── components/            # The synthesised design (hierarchical)
├── specifications/
├── verification_cases/
├── change_requests/
├── risks/
├── comments/
├── decisions/
├── traces/                # Traceability matrix
├── baselines/             # Frozen snapshots
└── history/               # Field-level audit trail per entity
```

The tool is installed separately from your project data. Point it at a project directory to get started.

Storage design notes:

- Every entity is one YAML file; writes are atomic (temp file + rename) — a crash never leaves a truncated file.
- Search and filtering run in memory over the YAML store — no index to rebuild and nothing derived to accidentally commit.
- Entity IDs are validated (they become filenames), which also blocks path traversal through the API.
- Corrupt YAML files are logged and skipped rather than breaking the entire collection.

## Quick Start

The `start.sh` launcher runs reqmesh in one of two modes:

```bash
./start.sh            # server (default) — web version
./start.sh server     # same as above
./start.sh desktop    # native desktop app (Electron)
./start.sh desktop --rebuild   # force a fresh frontend build first
```

- **server** — FastAPI backend on `:8000` + Vite dev server on `:5173`; open `http://localhost:5173`.
- **desktop** — builds the frontend to static files, then an Electron shell boots the backend (single origin, no CORS).

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

API available at `http://localhost:8000`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI available at `http://localhost:5173`

### Docker

```bash
# Development
docker compose up

# Production (single origin, TLS-ready)
export RT_SECRET=$(openssl rand -hex 32)
export RT_ADMIN_PASSWORD=$(openssl rand -base64 16)
docker compose -f docker-compose.prod.yml up -d
```

### Example project

On first launch the backend seeds a **Cessna 172S Skyhawk SP** example — 57 requirements with 15 verification cases, 16 components (with mass/current parameters for budget rollups), 2 specifications, 44 relations, traces, risks, change requests, comments, and decisions. Disable with `RT_SEED_DEMO=false`, or re-seed manually:

```bash
backend/.venv/bin/python seed_cessna.py --force
```

### Tests

**Backend** — 163 tests covering API, storage, auth, integrity, quality, tracing, code scan, fingerprint, table I/O, evaluation, and deployment:

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

**Frontend** — 59 tests covering stores, API client, entities, and auto-linking:

```bash
cd frontend
npm test
npm run typecheck
```

## Authentication

A default `admin` user is created on first run with a password from `RT_ADMIN_PASSWORD`. If the env var is unset or `"admin"`, a random 16-character password is generated and logged. **Set `RT_ADMIN_PASSWORD` before first launch.**

Roles:

- `viewer` — read-only (unauthenticated guests get this)
- `editor` — standard user: create/update/delete entities; self-registration creates editors
- `admin` — administrator: everything, including deleting projects and managing users

Passwords must be at least 12 characters and contain an uppercase letter, lowercase letter, digit, and special character.

### Token management

Tokens are JWTs signed with `RT_SECRET` (randomly generated and persisted if not set). Access tokens carry a per-user `token_version` that increments on password change — this invalidates all existing sessions for that user (no token blacklist needed).

### Rate limiting

Login (`POST /auth/login`) and password reset (`POST /auth/forgot-password`, `POST /auth/reset-password`) are rate-limited to 5 and 3 requests per minute per IP respectively.

### Password reset & email verification

- `POST /auth/forgot-password` — sends a time-limited (1 hour) reset link via email if SMTP is configured
- `POST /auth/reset-password` — consumes the token and sets a new password
- `POST /auth/verify-email` — verifies an email address via token
- `POST /auth/resend-verification` — re-sends the verification email

Both features require SMTP to be configured (`RT_SMTP_HOST`, `RT_SMTP_PORT`, etc.).

### User management

Administrators get a **Users** page (`/users`) to create accounts, manage roles, reset passwords, set email addresses, and delete users. Guardrails prevent locking yourself out (can't demote/delete the last admin, can't delete your own account).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/users` | List accounts (admin only; never returns password hashes) |
| POST | `/api/auth/users` | Create a user (`username`, `password`, `role`, `email`) |
| PATCH | `/api/auth/users/{username}` | Change `role`, `email`, and/or reset `password` |
| DELETE | `/api/auth/users/{username}` | Delete a user |

## Git Integration

If a project directory is a git repository, every mutation is auto-committed with a descriptive message (`rt: put requirements/SYST0001`). Disable with `RT_GIT_AUTOCOMMIT=false`.

- **Push to remote** — set `RT_GIT_REMOTE_URL` and `RT_GIT_PUSH_ON_COMMIT=true` to push after every auto-commit.
- **Offline mode** — `RT_OFFLINE_MODE=true` suppresses all outbound network calls (git push, SMTP).
- `GET /api/projects/{id}/git/log` — recent commits
- `POST /api/projects/{id}/hooks/install` — pre-commit hook
- `GET /api/projects/{id}/requirements/{rid}/history` — field-level change history (works with or without git)

## Interchange

Requirements round-trip through **ReqIF 1.2**, **SysML v2**, **CSV**, **TSV**, and **XLSX**:

- **Export** — from the Export dialog, `POST /api/projects/{id}/publish/download?format=reqif|sysml|csv|tsv|xlsx`, or CLI `export -f reqif`.
- **Import** — from the Import dialog, `POST /api/projects/{id}/import`, or CLI `import -i <file>`. Format is auto-detected; `mode=merge` (default) creates/updates; `mode=replace` wipes existing first. CSV import supports column aliases (e.g. `"Requirement ID"` → `id`).

## Components (the synthesised design)

Requirements describe what the system must **do**. Components describe what the system **is** — the design synthesised to meet those requirements. They form a hierarchy (`system → subsystem → assembly → part`, plus `software` and `interface`) and connect to the functional side three ways:

- **`satisfies`** — the requirements a component exists to deliver
- **`verification_cases`** — the cases that exercise the component
- **`relations`** — links to other components in the design tree

Components carry numeric `parameters` (mass, current draw, cost…) that feed budget rollups in the parametric evaluation engine. Each parameter's value is multiplied by the component's `quantity` during rollups.

Deleting a component promotes its children to the deleted component's parent, so the tree never dangles. Reparenting detects and rejects cycles. All component mutations produce an audit trail.

## Computable Requirements (SysML-style parametrics)

Requirements can carry typed numeric **parameters** and boolean **constraints** over them, so a requirement isn't just prose — it's evaluable:

```yaml
parameters:
  - {name: mtow, value: 1157, unit: kg}
  - {name: useful_load, unit: kg, expr: "mtow - AFRM0000.empty_mass"}
constraints:
  - {expr: "useful_load >= 380", assume: "OAT >= -20"}
```

- **Bounds between requirements** — an expression can reference another requirement's parameter as `ID.param`.
- **Budget rollups** — `rollup('WING', 'mass')` sums a parameter over a component subtree, multiplying by quantity.
- **Verdicts and margins** — pass / fail / unknown / error, with signed margin (absolute + %). An `assume` clause gates applicability.
- **Measured verdicts** — verification cases record measurements against parameters; the engine substitutes measured values and reports separate "design" and "measured" verdicts.
- **Safe evaluation** — expressions are parsed against a strict whitelist; YAML content can never execute arbitrary code. Derivation chains resolve across requirements with cycle detection.

Evaluate via `GET /api/projects/{id}/evaluation`. In the UI: the **Parameters & Constraints** card on a requirement shows live verdicts and margins; components carry their parameters; verification cases record measurements; a **Parametrics Guide** (togglable via the Guided button) explains everything in plain English.

## Deep Traceability & Coverage

Beyond simple binary coverage, reqmesh implements **shallow** and **deep** coverage tracing:

- **Shallow** — for each `needs` type (e.g. `["design", "test"]`), is there at least one covering item?
- **Deep** — are all coverers themselves fully covered transitively? A "broken chain" is flagged when an item is shallow-covered but its coverers are not deep-covered.
- **Terminating items** — items with empty `needs` are automatically deep-covered (leaf of the chain).
- **Cycle detection** — Tarjan's SCC algorithm detects circular relations, with depth guard (max 1000) to prevent stack overflow.
- **Code-to-requirement tags** — `POST /api/projects/{id}/scan` scans source files for `[impl->REQ-ID]` and `@covers REQ-ID` tags, linking them to requirements with SHA-based staleness detection.

See `GET /api/projects/{id}/coverage` and `/trace` (supports `?format=text` for CLI-friendly output). The CLI `trace` command produces an OFT-style plaintext report and exits non-zero on incomplete deep coverage.

## Review & Change Control

Fingerprint-based review (inspired by Doorstop):

- **`reviewed`** — SHA-256 of normative fields. A requirement is "reviewed" when its fingerprint matches the stored baseline.
- **`reviewed_fingerprint`** on each relation — captures the target's fingerprint at review time. If the target changes, the link becomes suspect.
- **Automatic staleness** — computed on read via the integrity checker. No imperative bookkeeping, no drift.
- **`derived`** items — requirements that don't need a parent link (e.g., external regulatory mandates).
- **`normative`** flag — non-normative items are excluded from coverage and gap analysis, rendered as section headings in published output.

`POST /api/projects/{id}/requirements/{req_id}/review` baselines a single requirement. `POST /api/projects/{id}/review-all` baselines all. `GET /api/projects/{id}/unreviewed` lists items whose content has changed since review.

## Quality Linting

Inline requirement writing feedback based on INCOSE, EARS, and ISO 29148 guidelines:

- **Weak words** — "should", "may", "appropriate", "user-friendly", etc.
- **Vague quantifiers** — "several", "minimal", "a lot of"
- **Placeholders** — "TODO", "TBD", "FIXME", "???"
- **Non-atomic** — multiple conjunctions suggesting split
- **Untestable** — test-verified requirements with no measurable criteria
- **Word count** — too short (< 5 words) or too long (> 200 words)
- **HTML-aware** — strips tags and decodes entities before analysis

Configurable per project via `_meta.yaml` (`quality.rules`, `quality.weights`, `quality.min_words`, `quality.max_words`). The **Description Helper** (togglable via the Guided button) provides live client-side feedback as you type, with guideline explanations for each rule.

## Planning & Estimation

- **`effort`** — story points (integer)
- **`priorities`** — per-stakeholder scores (`{"development": 5, "customers": 8, "safety": 10}`)
- **Prioritized backlog** — `GET /api/projects/{id}/backlog` returns requirements ordered by combined priority scores
- **Effort rollup** — total and completed effort by status shown on the metrics dashboard

## Cross-linking

Every entity reference is a hyperlink to that entity, wherever it appears. Each kind carries its own colour-coded icon.

- **Ctrl/Cmd+K command palette** — word-based fuzzy search across every entity; tolerates missing spaces (e.g. `fuelpump` matches `Fuel Pump`)
- **Hover previews** — pause on any reference to see a peek card with kind, status, and description
- **Copy link** — copies an absolute deep-link URL for commits, chat, or tickets
- **Backlinks** — relations render in both directions
- **Breadcrumbs** — ancestor chain with "Show in graph" shortcut
- **Auto-linking** — entity IDs in descriptions become links automatically in both read and edit modes

## Guided Mode (Helpers)

A `GUIDED` toggle in the header bar switches on contextual help across the application:

- **Section descriptions** — small italic text explaining what each UI section does
- **Parametrics Guide** — expandable Q&A covering parameters, budget rollups, constraints, measured verdicts, and expression language — no SysML knowledge required
- **Description Helper** — live inline feedback on requirement writing quality with expandable guideline reference

## Real-time Collaboration

Every project exposes an SSE stream at `GET /api/projects/{id}/events`. The web UI subscribes automatically:

- **Live updates** — lists, the navigation tree, and the graph refresh the moment anyone mutates the project.
- **Presence** — the header shows who is currently viewing the project; `GET /api/projects/{id}/presence` returns the roster as JSON.

User identity is extracted from the JWT token (not from query parameters). The event bus is in-memory (single process); clients auto-reconnect if the stream drops.

## Deployment

For production deployment on a local server with **TLS**, **multiple concurrent users**, **email notifications**, **git push to remote**, and **air-gapped offline mode**, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

Quick-start for Docker:

```bash
export RT_SECRET=$(openssl rand -hex 32)
export RT_ADMIN_PASSWORD=$(openssl rand -base64 16)
docker compose -f docker-compose.prod.yml up -d
```

Then open `http://<server-ip>:8000` and log in with `admin` / `$RT_ADMIN_PASSWORD`.

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RT_SECRET` | (generated) | JWT signing key |
| `RT_ADMIN_PASSWORD` | (generated) | Initial admin password |
| `RT_DATA_ROOT` | `~/.reqmesh/projects` | Project storage directory |
| `RT_GIT_AUTOCOMMIT` | `true` | Auto-commit changes |
| `RT_GIT_REMOTE_URL` | `""` | Remote to push commits to |
| `RT_GIT_PUSH_ON_COMMIT` | `false` | Push after each auto-commit |
| `RT_OFFLINE_MODE` | `false` | Suppress all outbound network calls |
| `RT_SMTP_HOST` | `""` | SMTP server (empty disables email) |
| `RT_BASE_URL` | `http://localhost:8000` | Public URL for email links |
| `RT_SEED_DEMO` | `true` | Seed Cessna example on first launch |
| `RT_LOG_LEVEL` | `INFO` | Python log level |
| `RT_DEBUG` | `false` | Show stack traces in errors |

## API

### Core CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/projects` | List/create projects |
| GET/DELETE | `/api/projects/{id}` | Get/delete project |
| GET | `/api/projects/{id}/requirements` | List/search (`?search=&type=&status=&priority=&offset=&limit=`) |
| POST | `/api/projects/{id}/requirements` | Create requirement |
| GET | `/api/projects/{id}/requirements/tree` | Requirement hierarchy |
| GET | `/api/projects/{id}/requirements/next-uid` | Next free UID |
| GET/PUT/DELETE | `/api/projects/{id}/requirements/{req_id}` | Get/update/delete |
| POST | `/api/projects/{id}/requirements/{req_id}/cascade` | Cascade to children |
| POST | `/api/projects/{id}/requirements/{req_id}/break-cascade` | Break cascade link |
| GET/POST/PUT/DELETE | `/api/projects/{id}/components` | Component CRUD |
| GET | `/api/projects/{id}/components/tree` | Component hierarchy |

### Analysis & Validation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/{id}/validate` | Integrity checks (dangling links, cycles, unreviewed, cascades…) |
| GET | `/api/projects/{id}/coverage` | Shallow + deep coverage analysis |
| GET | `/api/projects/{id}/trace` | Coverage trace (`?format=text` for plaintext) |
| GET | `/api/projects/{id}/metrics` | Quality, traceability, effort, status distribution |
| GET | `/api/projects/{id}/gap-analysis` | Missing descriptions, rationales, sources, links |
| GET | `/api/projects/{id}/conflicts` | Explicit conflicts + duplicate names |
| GET | `/api/projects/{id}/quality` | Per-requirement quality scores and findings |
| GET | `/api/projects/{id}/backlog` | Prioritized backlog with effort rollup |
| GET | `/api/projects/{id}/evaluation` | Parametric constraint evaluation (design + measured) |
| GET | `/api/projects/{id}/requirements/{rid}/impact` | Impact analysis (dependents + cascades) |
| GET | `/api/projects/{id}/requirements/{rid}/history` | Field-level change history |

### Review & Traceability

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects/{id}/requirements/{rid}/review` | Fingerprint baseline a requirement |
| POST | `/api/projects/{id}/review-all` | Baseline all requirements |
| GET | `/api/projects/{id}/unreviewed` | Requirements whose content changed since review |
| GET | `/api/projects/{id}/suspect-links` | Links whose target changed since review |
| POST | `/api/projects/{id}/scan` | Scan source files for `[impl->REQ-ID]` coverage tags |
| GET | `/api/projects/{id}/references/freshness` | Stale reference file detection |

### Publishing & Interchange

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects/{id}/publish` | Generate report (html, md, latex, pdf, csv, tsv, xlsx) |
| GET | `/api/projects/{id}/publish/download` | Download report or export file |
| POST | `/api/projects/{id}/import` | Import ReqIF, SysML, CSV, TSV, or XLSX (`mode=merge/replace`) |
| POST | `/api/projects/{id}/baselines/{name}/freeze` | Freeze a baseline snapshot |
| GET | `/api/projects/{id}/baselines/{name}/diff` | Diff current state against baseline |

### Real-time & Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/{id}/events` | SSE stream of live changes + presence |
| GET | `/api/projects/{id}/presence` | Current project viewers |
| POST | `/auth/login` | Authenticate (rate-limited 5/min) |
| POST | `/auth/register` | Self-registration |
| POST | `/auth/forgot-password` | Request password reset email |
| POST | `/auth/reset-password` | Reset password with token |
| POST | `/auth/verify-email` | Verify email address |
| POST | `/auth/resend-verification` | Re-send verification email |

PUT/PATCH endpoints apply partial updates: only fields present in the body change, and explicitly sending `null` clears a nullable field. PATCH on `/comments` supports `{"resolved": true}`. List endpoints return `{"items": [...], "total": N, "offset": O, "limit": L}` for pagination.

## Project Data Format

Each project is a directory of YAML files — one file per entity. JSON Schemas for every format are in [`schemas/`](schemas/) (regenerate with `python backend/gen_schemas.py`).

### Example Requirement YAML

```yaml
id: REQ-001
type: functional
name: "User Authentication"
description: "<p>The system shall authenticate users via OAuth2 within 500 ms.</p>"
priority: high
status: approved
verification_method: test
rationale: "OAuth2 is the industry standard for delegated authentication."
source: "ISO 27001"
allocated_to: "auth-module"
attributes:
  - {key: author, value: alice}
  - {key: standard, value: DO-178C}
relations:
  - {type: verified_by, target: VC-001, reviewed_fingerprint: "abc123…"}
verification_cases: [VC-001]
verification_status: pending
parent: FEAT-001
needs: [design, verification_case]
effort: 5
priorities: {development: 5, customers: 8, safety: 10}
derived: false
normative: true
reviewed: "xyz789…"
references:
  - {path: "src/auth/login.py", kind: impl, sha256: "9f2c…", lines: "L20-L45"}
parameters:
  - {name: max_response_time, value: 500, unit: ms}
constraints:
  - {expr: "max_response_time <= 500", assume: "load <= 1000"}
created: "2026-07-08T12:00:00Z"
modified: "2026-07-08T14:30:00Z"
```

## CLI

```bash
cd backend
.venv/bin/python -m app.cli create my-project
.venv/bin/python -m app.cli validate <path>              # integrity checks
.venv/bin/python -m app.cli validate <path> --quality    # + requirement quality linting
.venv/bin/python -m app.cli publish <path> -f pdf
.venv/bin/python -m app.cli export <path> -f reqif       # or -f sysml
.venv/bin/python -m app.cli import <path> -i model.reqif
.venv/bin/python -m app.cli review <path>                # fingerprint all
.venv/bin/python -m app.cli review <path> --item REQ-001
.venv/bin/python -m app.cli scan <path> --code ../src    # scan for coverage tags
.venv/bin/python -m app.cli trace <path>                 # coverage report (exits non-zero on gaps)
.venv/bin/python -m app.cli serve <path>
```

## Roadmap

- [x] Phase 1: Core CRUD, YAML storage, React UI
- [x] Phase 2: Traceability & verification enhancements
- [x] Phase 3: ReqIF/SysML import & export
- [x] Phase 4: Git integration (auto-commit, history, hooks)
- [x] Phase 5: Real-time collaboration (SSE + presence)
- [x] Phase 6: Code & test traceability (coverage tag scanning, staleness)
- [x] Phase 7: Deep coverage & tracing (needs, shallow/deep, cycle detection)
- [x] Phase 8: Fingerprint-based review & change control
- [x] Phase 9: Requirement quality linting
- [x] Phase 10: Planning & estimation (effort, per-stakeholder priority, backlog)
- [x] Phase 11: CSV/TSV/XLSX interchange + custom attribute schema

Detailed design notes and inspiration sources are in [ROADMAP.md](ROADMAP.md). Ongoing refinements are tracked in [REFINEMENT_ROADMAP.md](REFINEMENT_ROADMAP.md).

## License

reqmesh is licensed under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later) — see [LICENSE](LICENSE). GPLv3 is required for compatibility
with the project's dependencies: elkjs is offered under `GPL-3.0-or-later`, and
the Apache-2.0 components (bcrypt, python-multipart) are GPLv3-compatible but not
GPLv2-compatible.

Bundled/adjacent third-party software (e.g. the tectonic LaTeX engine) is listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
