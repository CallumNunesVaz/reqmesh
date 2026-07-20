# Releasing reqmesh

A **release** is a version-controlled `vX.Y.Z` build of reqmesh, bundled for
deployment on a server. Each release ships:

- the backend + the built frontend (single-origin serve),
- the **Cessna 172S example project**, pre-seeded,
- deployment configs (`Dockerfile.prod`, `docker-compose.prod.yml`, `Caddyfile`, `nginx.conf`),
- an `install.sh` and a `manifest.json` (version, git sha, build time, checksums).

Two artifacts are produced per release:

| Artifact | Where | Install with |
|----------|-------|--------------|
| `reqmesh-vX.Y.Z.tar.gz` | GitHub Release assets | unpack, run `./install.sh` |
| `ghcr.io/<owner>/reqmesh:X.Y.Z` (+ `:latest`) | GitHub Container Registry | `docker compose -f docker-compose.prod.yml up -d` |

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

`release.sh` bumps the version everywhere, regenerates release notes from the
commits since the last tag, builds the bundle locally as a smoke test, commits
(`release: v0.5.0`), creates an annotated tag, and pushes the branch and tag.

Pushing the tag triggers `.github/workflows/release.yml`, which:

1. rebuilds the bundle and publishes a **GitHub Release** with the tarball +
   `.sha256` attached and the tag message as notes;
2. builds and pushes the **Docker image** to `ghcr.io`.

Useful flags:

```bash
scripts/release.sh patch --dry-run     # bump + build bundle, no commit/tag/push
scripts/release.sh patch --no-push     # commit + tag locally, push yourself
scripts/release.sh patch --no-verify   # skip the local bundle smoke build
```

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
