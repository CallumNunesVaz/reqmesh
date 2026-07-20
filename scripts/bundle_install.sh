#!/usr/bin/env bash
#
# reqmesh installer — ships inside every release bundle as install.sh.
#
# Two install paths, auto-detected:
#   * Docker (preferred): builds the image and runs docker compose.
#   * Bare-metal fallback: Python venv + uvicorn serving the bundled frontend.
#
# The bundled Cessna 172S example project is copied into the data directory on
# a fresh install so the instance comes up populated.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VERSION="$(cat VERSION 2>/dev/null || echo unknown)"
echo "reqmesh installer — version ${VERSION}"

gen_secret() { openssl rand -hex 32 2>/dev/null || head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
gen_pw()     { openssl rand -base64 12 2>/dev/null || head -c12 /dev/urandom | base64; }

use_docker=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  use_docker=1
fi

if [ "${REQMESH_INSTALL_MODE:-auto}" = "bare" ]; then
  use_docker=0
fi

if [ "$use_docker" = "1" ]; then
  echo "==> Docker detected — deploying with docker compose"
  if [ ! -f .env ]; then
    echo "==> Generating secrets into .env"
    {
      echo "RT_SECRET=$(gen_secret)"
      echo "RT_ADMIN_PASSWORD=$(gen_pw)"
      echo "RT_BIND=${RT_BIND:-127.0.0.1}"
      echo "RT_SEED_DEMO=true"
    } > .env
    echo "    Wrote .env — admin password:"
    grep RT_ADMIN_PASSWORD .env
  fi
  docker compose --env-file .env -f docker-compose.prod.yml up -d --build
  echo "==> reqmesh is starting on http://127.0.0.1:8000 (health: /health)"
  exit 0
fi

echo "==> No Docker — installing bare-metal (Python venv)"
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: python3 not found; install Python 3.11+ or Docker" >&2
  exit 1
fi

VENV="${VENV:-.venv}"
if [ ! -d "$VENV" ]; then
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

DATA_ROOT="${RT_DATA_ROOT:-$HERE/data/projects}"
mkdir -p "$DATA_ROOT"
# Seed the bundled Cessna example on a fresh install (don't clobber existing data).
if [ -d "data/projects" ] && [ -z "$(ls -A "$DATA_ROOT" 2>/dev/null)" ]; then
  echo "==> Installing bundled example project into $DATA_ROOT"
  cp -a data/projects/. "$DATA_ROOT/"
fi

export RT_STATIC_DIR="$HERE/frontend/dist"
export RT_DATA_ROOT="$DATA_ROOT"
export RT_SECRET="${RT_SECRET:-$(gen_secret)}"
export RT_ADMIN_PASSWORD="${RT_ADMIN_PASSWORD:-$(gen_pw)}"
echo "==> Admin password: $RT_ADMIN_PASSWORD"
echo "==> Serving on http://0.0.0.0:${RT_PORT:-8000}"
cd backend
exec "$HERE/$VENV/bin/uvicorn" app.main:app --host "${RT_HOST:-0.0.0.0}" --port "${RT_PORT:-8000}"
