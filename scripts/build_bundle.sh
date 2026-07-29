#!/usr/bin/env bash
#
# Build a self-contained reqmesh release bundle:
#
#   dist/reqmesh-vX.Y.Z.tar.gz          the bundle
#   dist/reqmesh-vX.Y.Z.tar.gz.sha256   its checksum
#
# The bundle contains the backend source, the built frontend, the Cessna 172S
# example project, deployment configs, an install.sh, and a manifest.json.
#
# Reused by both scripts/release.sh (local) and the GitHub Actions workflow (CI).
# Set PYTHON to the interpreter used to seed the example project — defaults to the
# backend venv locally; CI passes its own interpreter.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(cat VERSION)"
NAME="reqmesh-v${VERSION}"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
STAGE="$(mktemp -d)"
DEST="$STAGE/$NAME"
PYTHON="${PYTHON:-$ROOT/backend/.venv/bin/python}"
SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"

trap 'rm -rf "$STAGE"' EXIT

echo "==> Building bundle $NAME"
mkdir -p "$DEST" "$OUT_DIR"

# ── 1. Frontend build ────────────────────────────────────────────────────────
if [ "$SKIP_FRONTEND_BUILD" != "1" ]; then
  echo "==> Building frontend"
  ( cd frontend && npm run build )
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "error: frontend/dist/index.html missing — build the frontend first" >&2
  exit 1
fi

# ── 2. Backend source (lean: no venv, caches, or tests) ──────────────────────
echo "==> Copying backend"
mkdir -p "$DEST/backend"
rsync -a \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.py[cod]' \
  --exclude '.pytest_cache' \
  --exclude 'tests' \
  backend/ "$DEST/backend/"

# ── 3. Built frontend ────────────────────────────────────────────────────────
echo "==> Copying frontend/dist"
mkdir -p "$DEST/frontend"
cp -a frontend/dist "$DEST/frontend/dist"

# ── 4. Bundled Cessna example project ────────────────────────────────────────
echo "==> Seeding bundled example project"
mkdir -p "$DEST/data/projects"
"$PYTHON" seed_cessna.py --force --data-root "$DEST/data/projects"

# ── 5. Deploy configs + docs ─────────────────────────────────────────────────
echo "==> Copying deploy configs and docs"
for f in Dockerfile.prod docker-compose.prod.yml Caddyfile nginx.conf DEPLOYMENT.md LICENSE README.md VERSION; do
  [ -e "$f" ] && cp -a "$f" "$DEST/" || echo "    (skip missing $f)"
done
# ── 5b. The installer ────────────────────────────────────────────────────────
# The bundle ships the real installer and its companions, not a parallel
# implementation. It used to carry two of its own: bundle_install.sh (as
# install.sh) and install-ubuntu-24.04.sh. Both duplicated the deployment logic
# and had drifted from it — neither set RT_COOKIE_SECURE, so a bundle install
# over plain HTTP let you log in and then rejected every request with 401, and
# neither had any of the fixes the maintained installer has accumulated.
#
# deploy-bare.sh takes its application source from $SCRIPT_DIR/.., which inside
# the bundle is the bundle root — so the bare path works from an unpacked
# tarball with no network at all.
echo "==> Copying the installer"
mkdir -p "$DEST/scripts"
# Only what an install needs at runtime. The release tooling (build_bundle.sh,
# release.sh, set_version.py) has no business on a deployment target, and
# shipping it invites someone to run it there.
for f in install.sh lib.sh wizard.sh deploy-docker.sh deploy-bare.sh; do
  cp "scripts/$f" "$DEST/scripts/"
done
cp -a scripts/templates "$DEST/scripts/templates"
cp -a scripts/updater "$DEST/scripts/updater"
chmod +x "$DEST/scripts"/*.sh "$DEST/scripts/updater"/*.sh

# ./install.sh at the bundle root stays the documented entry point; it has to
# live beside lib.sh or the real installer decides it is running standalone and
# tries to download its companions, which defeats an offline bundle.
cat > "$DEST/install.sh" <<'WRAPPER'
#!/usr/bin/env bash
# reqmesh bundle installer — delegates to the maintained installer in scripts/.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/scripts/install.sh" "$@"
WRAPPER
chmod +x "$DEST/install.sh"
[ -f "${RELEASE_NOTES_FILE:-}" ] && cp "$RELEASE_NOTES_FILE" "$DEST/RELEASE_NOTES.md" || true

# ── 6. Manifest ──────────────────────────────────────────────────────────────
echo "==> Writing manifest.json"
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$DEST/manifest.json" <<JSON
{
  "name": "reqmesh",
  "version": "${VERSION}",
  "tag": "v${VERSION}",
  "git_sha": "${GIT_SHA}",
  "built_at": "${BUILT_AT}",
  "bundled_projects": ["cessna-172"],
  "artifacts": { "tarball": "${NAME}.tar.gz" }
}
JSON

# ── 7. Archive + checksum ────────────────────────────────────────────────────
echo "==> Creating tarball"
TARBALL="$OUT_DIR/${NAME}.tar.gz"
tar -czf "$TARBALL" -C "$STAGE" "$NAME"
( cd "$OUT_DIR" && sha256sum "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256" )

SIZE="$(du -h "$TARBALL" | cut -f1)"
echo "==> Done: $TARBALL ($SIZE)"
cat "$OUT_DIR/${NAME}.tar.gz.sha256"
