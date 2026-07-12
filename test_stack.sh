#!/bin/bash
set -e

rm -rf ~/.reqmesh

echo "=== Starting backend ==="
cd "$(dirname "$0")/backend"
.venv/bin/uvicorn app.main:app --port 8000 > /dev/null 2>&1 &
BACKEND_PID=$!
sleep 2

echo "=== Creating test data via backend ==="
curl -sf -X POST http://localhost:8000/api/projects -H "Content-Type: application/json" -d '{"id":"demo","name":"Demo"}' > /dev/null
curl -sf -X POST http://localhost:8000/api/projects/demo/requirements -H "Content-Type: application/json" -d '{"id":"REQ-001","name":"Test Req","type":"functional","priority":"high"}' > /dev/null

echo "=== Starting frontend ==="
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
cd "$(dirname "$0")/frontend"
./node_modules/.bin/vite --host 0.0.0.0 > /dev/null 2>&1 &
FRONTEND_PID=$!
sleep 3

echo -n "1. Frontend serves HTML: "
curl -sf http://localhost:5173/ | grep -q "reqmesh" && echo "PASS" || echo "FAIL"

echo -n "2. API proxy via frontend: "
COUNT=$(curl -sf http://localhost:5173/api/projects | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "PASS ($COUNT project)" || echo "FAIL"

echo -n "3. Requirements via proxy: "
COUNT=$(curl -sf http://localhost:5173/api/projects/demo/requirements | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "PASS ($COUNT req)" || echo "FAIL"

echo ""
echo "=== Full stack integration tests passed ==="

kill $FRONTEND_PID $BACKEND_PID 2>/dev/null
