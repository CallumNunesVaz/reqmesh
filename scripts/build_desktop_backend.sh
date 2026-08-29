#!/usr/bin/env bash
#
# Build the reqmesh backend into a single PyInstaller executable that the
# Electron desktop shell bundles under extraResources. Output lands in
# desktop/backend/reqmesh-backend, which desktop/package.json copies into the
# packaged app's resources.
#
# Reused by both `npm run build` (desktop) and the CI desktop-package job.
# PYTHON selects the interpreter used to run PyInstaller — defaults to the
# backend venv locally; CI passes its own (`python` from setup-python).
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/backend/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

echo "==> Building desktop backend with PyInstaller"
"$PYTHON" -m PyInstaller \
  --noconfirm --clean \
  --distpath "$ROOT/desktop/backend" \
  --workpath "$ROOT/backend/build/pyinstaller" \
  "$ROOT/backend/pyinstaller.spec"

echo "==> Desktop backend built: $ROOT/desktop/backend/reqmesh-backend"
