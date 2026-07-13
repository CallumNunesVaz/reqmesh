#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-server}"

usage() {
  cat <<'EOF'
reqmesh launcher

Usage: ./start.sh [server|desktop] [--rebuild]

  server   (default) Web version — FastAPI backend + Vite dev server.
           Open http://localhost:5173 in a browser. No Electron wrapper, so
           nothing extra sits between you and the app.

  desktop  Native desktop app via an Electron wrapper. Builds the frontend to
           static files, then the Electron shell boots the backend (which also
           serves the UI) and shows it in a native window.

Options:
  --rebuild   (desktop) Force a fresh frontend production build.
  -h, --help  Show this help.
EOF
}

load_nvm() {
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
}

ensure_backend_venv() {
  cd "$DIR/backend"
  if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install -q -r requirements.txt
  fi
}

# ── Server (web) version ──────────────────────────────────────────────────────
run_server() {
  cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo "Done."
  }
  trap cleanup EXIT INT TERM

  echo "=================================="
  echo "  reqmesh v0.4.0  (server)"
  echo "=================================="
  echo ""

  echo "[1/2] Starting backend..."
  ensure_backend_venv
  # `python -m uvicorn` (not the uvicorn entry-point script): the script's
  # shebang hardcodes the venv's absolute path and breaks if the repo is
  # moved or renamed, while the python symlink keeps working.
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  BACKEND_PID=$!

  echo "[2/2] Starting frontend..."
  load_nvm
  cd "$DIR/frontend"
  if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install --silent
  fi
  ./node_modules/.bin/vite --host 0.0.0.0 --port 5173 &
  FRONTEND_PID=$!

  echo ""
  echo "Waiting for servers..."
  BACKEND_UP=0
  for _ in $(seq 1 15); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
      BACKEND_UP=1
      break
    fi
    # Fail fast if the backend process already died.
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if [ "$BACKEND_UP" != "1" ]; then
    echo ""
    echo "ERROR: backend failed to start on port 8000." >&2
    echo "If dependencies changed or the repo was moved, recreate the venv:" >&2
    echo "  rm -rf backend/.venv && ./start.sh" >&2
    exit 1
  fi
  for _ in $(seq 1 15); do
    if curl -s http://localhost:5173/ > /dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  echo ""
  echo "=================================="
  echo "  Backend  -> http://localhost:8000"
  echo "  Frontend -> http://localhost:5173"
  echo "=================================="
  echo ""
  echo "Press Ctrl+C to stop."

  wait
}

# ── Desktop (Electron) version ────────────────────────────────────────────────
run_desktop() {
  echo "=================================="
  echo "  reqmesh v0.4.0  (desktop)"
  echo "=================================="
  echo ""

  echo "[1/3] Ensuring backend environment..."
  ensure_backend_venv

  load_nvm

  echo "[2/3] Building frontend..."
  cd "$DIR/frontend"
  if [ ! -d "node_modules" ]; then
    echo "  Installing frontend dependencies..."
    npm install --silent
  fi
  if [ "$REBUILD" = "1" ] || [ ! -f "dist/index.html" ]; then
    npm run build
  else
    echo "  Reusing existing build in frontend/dist (pass --rebuild to refresh)."
  fi

  echo "[3/3] Launching desktop app..."
  cd "$DIR/desktop"
  if [ ! -d "node_modules" ]; then
    echo "  Installing Electron (first run may take a minute)..."
    npm install --silent
  fi
  # Electron owns the backend lifecycle from here (spawns and tears it down).
  exec npm start --silent
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
REBUILD=0
for arg in "$@"; do
  [ "$arg" = "--rebuild" ] && REBUILD=1
done

case "$MODE" in
  server|web) run_server ;;
  desktop|app) run_desktop ;;
  -h|--help|help) usage ;;
  *) echo "Unknown mode: $MODE" >&2; echo ""; usage; exit 1 ;;
esac
