# Releasing reqmesh

A **release** is a version-controlled `vX.Y.Z` build of reqmesh, bundled for
deployment on a server. Each release ships:

- the backend + the built frontend (single-origin serve),
- the **Cessna 172S example project**, pre-seeded,
- deployment configs (`Dockerfile.prod`, `docker-compose.prod.yml`, `Caddyfile`, `nginx.conf`),
- an `install.sh` and a `manifest.json` (version, git sha, build time, checksums).

Three artifacts are produced per release:

| Artifact | Where | Install with |
|----------|-------|--------------|
| `reqmesh-vX.Y.Z.tar.gz` | GitHub Release assets | unpack, run `./install.sh` |
| `ghcr.io/<owner>/reqmesh:X.Y.Z` (+ `:latest`) | GitHub Container Registry | `docker compose -f docker-compose.prod.yml up -d` |
| `reqmesh-vX.Y.Z-linux-x86_64.AppImage` | GitHub Release assets | `chmod +x` and run — no install, no root |

The AppImage bundles a PyInstaller-frozen backend and the built SPA, so it needs
no system Python and no server. It is built and boot-checked on **every push**
by CI's `desktop-package` job as well as at release time — a packaging path that
only ran during a release would be one CI could never fail on.

## Version source of truth

The repo-root **`VERSION`** file is authoritative. `scripts/set_version.py`
propagates it to `backend/app/core/_version.py`, `frontend/package.json`, and
`desktop/package.json`. The backend serves it at `/version` and `/api/version`
(and includes it in `/health`); the UI shows it beside the logo.

```bash
python3 scripts/set_version.py --get     # print current version
```

## Cutting a release

From a clean `main`:

```bash
scripts/release.sh minor        # 0.4.0 -> 0.5.0   (also: patch | major | X.Y.Z)
```

`release.sh` bumps the version everywhere, resolves the release notes (below),
builds the bundle locally as a smoke test, commits (`release: v0.5.0`), creates
an annotated tag, and pushes the branch and tag.

Pushing the tag triggers `.github/workflows/release.yml`, which:

1. runs the full CI suite (`.github/workflows/ci.yml` via `workflow_call`);
   **all CI jobs must pass** or the release stops before publishing;
2. rebuilds the bundle and publishes a **GitHub Release** with the tarball +
   `.sha256` attached and the tag message as notes;
3. builds and pushes the **Docker image** to `ghcr.io`.

Useful flags:

```bash
scripts/release.sh patch --dry-run     # bump + build bundle, no commit/tag/push
scripts/release.sh patch --no-push     # commit + tag locally, push yourself
scripts/release.sh patch --no-verify   # skip the local bundle smoke build
scripts/release.sh patch --notes-file NOTES.md   # use NOTES.md verbatim
```

## Release notes

Notes are not an internal artifact. `updater.py` fetches the GitHub release body
and the System page renders it to whoever is deciding whether to apply an
update, so write them for that reader.

`scripts/release_notes.sh` resolves them from the first source that has content:

1. **`--notes-file FILE`** — used verbatim.
2. **`CHANGELOG.md`** — the body of the `## [Unreleased]` section. This is the
   normal path: add entries as you merge, and the release picks them up. An
   untouched Keep a Changelog skeleton (headings with nothing under them) does
   not count as content and falls through.
3. **The commit log** — grouped by conventional-commit type, deduplicated, with
   security and features ordered above build noise. A safety net, not a
   substitute: v0.5.0 shipped a raw `git log` dump that named an internal review
   file and listed one change twice.

On release, `[Unreleased]` is retitled `## [X.Y.Z] - <date>` and a fresh empty
`[Unreleased]` is opened above it. The rewritten `CHANGELOG.md` is staged into
the same `release:` commit as the version bump. A `--dry-run` never touches it.

The behaviour is covered by `scripts/tests/test_release_notes.sh`.

## Building a bundle without releasing

```bash
scripts/build_bundle.sh                 # -> dist/reqmesh-v<VERSION>.tar.gz (+ .sha256)
```

Set `PYTHON` to choose the interpreter that seeds the example project
(default: `backend/.venv/bin/python`; CI passes its own).

## Installing a release on a server

```bash
tar -xzf reqmesh-v0.5.0.tar.gz && cd reqmesh-v0.5.0
./install.sh
```

`install.sh` uses Docker if it's available (generating secrets into `.env` and
running `docker compose`), otherwise falls back to a Python venv + uvicorn
serving the bundled frontend. On a fresh install it seeds the bundled Cessna
example into the data directory.
