# reqmesh

<p align="center">
  <img src="media/reqmesh-logo.svg" alt="Reqmesh Logo" width="500">
</p>

An open-source, web-based requirements management tool with:

- **Git-friendly storage** — Requirements, specifications, and verification cases stored as human-readable YAML files; no databases or binary artifacts inside your project directory
- **Version control native** — Each project is a self-contained directory; if it's a git repository, every change made through the API is automatically committed
- **Change history** — Field-level audit trail for every requirement (who changed what, when), plus the full git log
- **Standards support** — Import **and** export ReqIF 1.2 and SysML v2 (round-trips through both formats)
- **Real-time collaboration** — Live change streaming over SSE plus a presence roster of who's viewing a project
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

The `start.sh` launcher runs reqmesh in one of two modes:

```bash
./start.sh            # server (default) — web version
./start.sh server     # same as above
./start.sh desktop    # native desktop app (Electron)
./start.sh desktop --rebuild   # force a fresh frontend build first
```

- **server** — FastAPI backend on `:8000` + Vite dev server on `:5173`; open
  `http://localhost:5173` in a browser. There is **no** Electron wrapper in this
  mode, so nothing sits between you and the app.
- **desktop** — builds the frontend to static files, then an Electron shell
  boots the backend (which also serves the UI over one origin) and shows it in a
  native window. The backend is spawned and torn down by Electron; killing the
  window stops everything.

The steps below run the pieces individually.

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
docker-compose up
```

### Desktop App (Electron)

```bash
./start.sh desktop
```

This builds the frontend, then launches the Electron shell in `desktop/`. The
shell:

- picks a free loopback port and spawns the backend
  (`python -m uvicorn app.main:app`) with `RT_STATIC_DIR` pointed at
  `frontend/dist`, so the API and UI share one origin;
- waits for `/health`, then loads the app in a native window;
- terminates the backend when the window closes.

The server/web version deliberately does **not** go through Electron — the
wrapper only exists for the desktop build. On locked-down Linux sandboxes
Electron may need `--no-sandbox` (`cd desktop && npm start -- --no-sandbox`).

An electron-builder config is included (`cd desktop && npm run build`) and
bundles the shell plus `frontend/dist`; note that a fully self-contained
installer also needs the Python backend packaged (e.g. via PyInstaller), which
is not wired up yet — the current desktop mode expects the repo's
`backend/.venv` (or a system `python3`) to be present.

### Example project

On first launch (when the data root has no projects yet) the backend seeds a
**Cessna 172S Skyhawk SP** example — 54 requirements plus verification cases,
traces, risks, change requests, and comments — so the UI opens with something
to explore. Disable with `RT_SEED_DEMO=false`, or re-seed manually:

```bash
backend/.venv/bin/python seed_cessna.py --force
```

### Tests

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

## Authentication

A default `admin` user is created on first run (password `admin`, or set
`RT_ADMIN_PASSWORD` before first launch). **Change it for anything beyond
local use.** Roles:

- `viewer` — read-only (unauthenticated guests get this)
- `editor` — **standard user**: create/update/delete entities; self-registration creates editors
- `admin` — **administrator**: everything, including deleting projects and managing users

New passwords must be at least 8 characters.

Tokens are JWTs signed with `RT_SECRET` if set, otherwise a random secret is
generated and persisted to `~/.reqmesh/secret`.

### User management

Administrators get a **Users** page (link in the top bar, or `/users`) to
create accounts, switch a user between **Standard** and **Administrator**,
reset passwords, and delete users. Role changes take effect immediately (the
role is read live from the store, not from the caller's token). Guardrails
prevent locking yourself out: you can't demote or delete the last administrator,
and you can't delete your own account.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/users` | List accounts (admin only; never returns password hashes) |
| POST | `/api/auth/users` | Create a user (`username`, `password`, `role`) |
| PATCH | `/api/auth/users/{username}` | Change `role` and/or reset `password` |
| DELETE | `/api/auth/users/{username}` | Delete a user |

## Git Integration

If a project directory is a git repository (`git init` inside it), every
mutation through the API is committed automatically with a descriptive
message (`rt: put requirements/SYST0001`). Disable with `RT_GIT_AUTOCOMMIT=false`.

- `GET /api/projects/{id}/git/log` — recent commits
- `POST /api/projects/{id}/hooks/install` — pre-commit hook that validates requirement YAML
- `GET /api/projects/{id}/requirements/{rid}/history` — field-level change history (works with or without git)

## Interchange (ReqIF / SysML)

Requirements round-trip through **ReqIF 1.2** (DOORS/Polarion/Jama) and **SysML
v2** textual notation, in both directions:

- **Export** — from the UI's Export dialog, `POST /api/projects/{id}/publish/download?format=reqif|sysml`, or `cli export -f reqif|sysml`.
- **Import** — from the UI's Import dialog, `POST /api/projects/{id}/import`, or `cli import -i <file>`. The format is auto-detected (override with `-f`), and `mode=merge` (default) creates new entities / updates matching IDs while `mode=replace` wipes existing requirements first. The ReqIF parser matches on attribute `LONG-NAME` and is namespace-agnostic, so files from other tools import too.

## Real-time Collaboration

Every project exposes a Server-Sent Events stream at
`GET /api/projects/{id}/events`. The web UI subscribes automatically and:

- **Live updates** — lists, the navigation tree and the graph refresh the moment anyone (or any API client) mutates the project.
- **Presence** — the header shows avatars of everyone currently viewing the project; `GET /api/projects/{id}/presence` returns the same roster as JSON.

The event bus is in-memory (single process); clients auto-reconnect if the
stream drops.

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
| POST | `/api/projects/{id}/import` | Import a ReqIF/SysML file (`file`, `format=auto\|reqif\|sysml`, `mode=merge\|replace`) |
| GET | `/api/projects/{id}/events` | SSE stream of live change + presence events (`?user=&role=`) |
| GET | `/api/projects/{id}/presence` | Users currently viewing the project |

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
.venv/bin/python -m app.cli export <project-path> -f reqif   # or -f sysml
.venv/bin/python -m app.cli import <project-path> -i model.reqif   # ReqIF/SysML import (auto-detected)
.venv/bin/python -m app.cli import <project-path> -i model.sysml -f sysml -m replace
.venv/bin/python -m app.cli serve <project-path>
```

## Roadmap

- [x] Phase 1: Core CRUD, YAML storage, React UI
- [x] Phase 2: Traceability & verification enhancements
- [x] Phase 3: ReqIF/SysML import & export (round-trips ReqIF 1.2 and SysML v2)
- [x] Phase 4: Git integration (auto-commit, history, hooks)
- [x] Phase 5: Real-time collaboration (live change streaming + presence)

Proposed next phases (6–11) — code/test traceability, deep coverage,
fingerprint-based review, requirement quality linting, planning/estimation, and
CSV/XLSX interchange — with detailed implementation instructions and their
inspiration sources (OpenFastTrace, Doorstop, rmtoo) are in
[ROADMAP.md](ROADMAP.md).

## License

GNU GPL-2.0
