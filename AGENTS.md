# reqmesh — agent conventions

FastAPI backend (`backend/`) + React/Vite SPA (`frontend/`), shipped as a web app
and an Electron desktop shell (`desktop/`). Requirements data is YAML on disk,
git-versioned, validated against the JSON Schemas in `schemas/`.

## Environment (read this before running anything)

- **There is no system python.** Always use `backend/.venv/bin/python` and
  `backend/.venv/bin/pytest`. `python`/`python3` on PATH is not the project env.
- **npm runs from `frontend/`** (or `desktop/`), never from the repo root.
- **Rebuild `frontend/dist` before any end-to-end run** — the backend and the
  Electron shell serve the built bundle, not the dev server.

## Commands

```bash
# backend  (cwd: backend/)
.venv/bin/pytest -q                     # fast suite; contract tests excluded by pytest.ini
.venv/bin/pytest -m contract -q         # slow OpenAPI-generated contract suite
.venv/bin/python gen_schemas.py         # regenerate schemas/*.json from the Pydantic models
ruff check app tests                    # lint (also in CI — cannot ship a lint failure)

# frontend (cwd: frontend/)
npm run typecheck                       # tsc --noEmit
npm test                                # vitest run
npm run lint                            # oxlint (also in CI)
npm run build                           # tsc -b && vite build && check:selfcontained
npm run e2e                             # playwright; requires a fresh `npm run build`

# deploy scripts (cwd: repo root)
bash scripts/tests/run.sh               # discover & run all test_*.sh suites
```

A change is "done" only when the suites covering it pass. Run them yourself;
do not report completion on the strength of reading the code.

## Layout

| Path | Holds |
| --- | --- |
| `backend/app/models/` | Pydantic models — the contract. `*Create` / `*Update` pairs per entity. |
| `backend/app/api/` | Thin routers, split by area (`router.py`, `publish_routes.py`, …). Parse, authorize, delegate. |
| `backend/app/services/` | Business logic. Pure where possible; no FastAPI imports. |
| `backend/app/storage/`, `app/core/` | YAML persistence; ids, auth, dependencies. |
| `schemas/` | JSON Schemas **generated** from the Pydantic models — never hand-edit. |
| `frontend/src/api/` | Typed client mirroring the backend routes. |
| `frontend/src/{components,pages,hooks,store,lib}/` | UI, routed views, state. |

## Rules

1. **The Pydantic model is the source of truth.** Change `backend/app/models/`
   first, regenerate schemas with `gen_schemas.py`, then update the TS types in
   `frontend/src/api/` to match. Never let the three drift.
2. **Routers stay thin.** Anything more than validation + a service call belongs
   in `backend/app/services/`.
3. **Services stay importable without FastAPI.** That is what makes them unit
   testable and what makes a task safely delegable.
4. **Never hand-edit `schemas/*.json`** or anything in `dist/`.
5. **Follow the surrounding code.** Match existing naming, error handling, and
   comment density in the file you are editing rather than importing a new style.
6. **Stay inside the task's stated scope.** Do not opportunistically refactor
   neighbouring code; note it instead and move on.
