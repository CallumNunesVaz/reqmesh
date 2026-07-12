# reqmesh

An open-source, web-based requirements management tool with:

- **Git-friendly storage** — Requirements, specifications, and verification cases stored as human-readable YAML files; no databases or binary artifacts inside your project directory
- **Version control native** — Each project is a self-contained directory; if it's a git repository, every change made through the API is automatically committed
- **Change history** — Field-level audit trail for every requirement (who changed what, when), plus the full git log
- **Standards support** — Import/export ReqIF 1.2, SysML v1.x, and SysML v2 (Phase 3)
- **Verification tracking** — Link requirements to verification cases and track pass/fail status
- **Rich text editing** — Full TipTap editor for requirement descriptions (XHTML compatible with ReqIF)
- **Responsive UI** — React frontend with TailwindCSS and Framer Motion animations

## Architecture

```
reqmesh/          # THE TOOL (this repo)
├── backend/               # Python FastAPI
├── frontend/              # React + TypeScript + Vite
└── schemas/               # JSON Schemas for the project YAML formats

<your-project>/            # YOUR DATA (separate, git-tracked)
├── _meta.yaml
├── requirements/
├── specifications/
├── verification_cases/
├── traces/
├── baselines/             # frozen snapshots
├── history/               # field-level audit trail per requirement
├── change_requests/  risks/  comments/  decisions/
```

The tool is installed separately from your project data. Point it at a project directory to get started.

Storage design notes:

- Every entity is one YAML file; all writes are atomic (temp file + rename), so a crash never leaves a truncated file in your working tree.
- Search and filtering run in memory over the YAML store — there is no index to rebuild and nothing derived to accidentally commit.
- All entity IDs are validated (they become filenames), which also blocks path traversal through the API.

## Quick Start

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
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
docker-compose up
```

### Tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

## Authentication

A default `admin` user is created on first run (password `admin`, or set
`RT_ADMIN_PASSWORD` before first launch). **Change it for anything beyond
local use.** Roles:

- `viewer` — read-only (unauthenticated guests get this)
- `editor` — create/update/delete entities; self-registration creates editors
- `admin` — everything, including deleting projects and assigning roles

Tokens are JWTs signed with `RT_SECRET` if set, otherwise a random secret is
generated and persisted to `~/.reqmesh/secret`.

## Git Integration

If a project directory is a git repository (`git init` inside it), every
mutation through the API is committed automatically with a descriptive
message (`rt: put requirements/SYST0001`). Disable with `RT_GIT_AUTOCOMMIT=false`.

- `GET /api/projects/{id}/git/log` — recent commits
- `POST /api/projects/{id}/hooks/install` — pre-commit hook that validates requirement YAML
- `GET /api/projects/{id}/requirements/{rid}/history` — field-level change history (works with or without git)

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{id}/requirements` | List/search requirements (`?search=&type=&status=&priority=`) |
| POST | `/api/projects/{id}/requirements` | Create requirement |
| GET | `/api/projects/{id}/requirements/tree` | Requirement hierarchy |
| GET | `/api/projects/{id}/requirements/next-uid` | Next free UID (`?parent=`) |
| GET/PUT/DELETE | `/api/projects/{id}/requirements/{req_id}` | Get/update/delete requirement |
| GET | `/api/projects/{id}/requirements/{req_id}/history` | Change history |
| GET | `/api/projects/{id}/requirements/{req_id}/impact` | Impact analysis |
| GET/POST | `/api/projects/{id}/specifications` | Specifications |
| GET/POST | `/api/projects/{id}/verification` | Verification cases |
| GET/PUT | `/api/projects/{id}/traces` | Traceability matrix |
| GET | `/api/projects/{id}/validate` | Integrity checks |
| GET | `/api/projects/{id}/metrics` · `/coverage` · `/gap-analysis` · `/conflicts` | Analysis |
| POST | `/api/projects/{id}/baselines/{name}/freeze` | Freeze a baseline snapshot |
| GET | `/api/projects/{id}/baselines/{name}/diff` | Diff current state against a baseline |
| GET | `/api/projects/{id}/git/log` | Git commit log |
| POST | `/api/projects/{id}/publish` | Publish report (html/md/latex; pdf via `/publish/download`) |

PUT endpoints apply partial updates: only fields present in the body change,
and explicitly sending `null` clears a nullable field (e.g. `parent`).

## Project Data Format

Each project is a directory of YAML files — one file per entity. JSON Schemas
for every format are in [`schemas/`](schemas/) (regenerate with
`python backend/gen_schemas.py`).

### Example Requirement YAML

```yaml
id: REQ-001
type: functional
name: "User Authentication"
description: "<p>The system shall authenticate users via OAuth2.</p>"
priority: high
status: approved
verification_method: test
attributes:
  - key: author
    value: alice
relations:
  - type: verified_by
    target: VC-001
verification_cases: [VC-001]
verification_status: pending
created: "2026-07-08T12:00:00Z"
modified: "2026-07-08T14:30:00Z"
```

## CLI

```bash
cd backend
.venv/bin/python -m app.cli create my-project
.venv/bin/python -m app.cli validate <project-path>   # integrity checks (CI-friendly exit code)
.venv/bin/python -m app.cli publish <project-path> -f pdf
.venv/bin/python -m app.cli serve <project-path>
```

## Roadmap

- [x] Phase 1: Core CRUD, YAML storage, React UI
- [x] Phase 2: Traceability & verification enhancements
- [x] Phase 4: Git integration (auto-commit, history, hooks)
- [ ] Phase 3: ReqIF/SysML import/export
- [ ] Phase 5: Real-time collaboration

## License

MIT
