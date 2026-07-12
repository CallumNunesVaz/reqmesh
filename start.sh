#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

echo "=================================="
echo "  reqmesh v0.1.0"
echo "=================================="
echo ""

# Backend
echo "[1/2] Starting backend..."
cd "$DIR/backend"
if [ ! -d ".venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Frontend
echo "[2/2] Starting frontend..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
cd "$DIR/frontend"
if [ ! -d "node_modules" ]; then
  echo "  Installing dependencies..."
  npm install --silent
fi
./node_modules/.bin/vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

# Wait for servers
echo ""
echo "Waiting for servers..."
for i in $(seq 1 15); do
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
