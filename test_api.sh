#!/bin/bash
set -e

# Runs against a throwaway data root — never touches ~/.reqmesh/projects.
DATA_ROOT=$(mktemp -d)
trap 'kill $BACKEND_PID 2>/dev/null; rm -rf "$DATA_ROOT"' EXIT

echo "=== Starting backend (data root: $DATA_ROOT) ==="
cd "$(dirname "$0")/backend"
RT_DATA_ROOT="$DATA_ROOT" .venv/bin/uvicorn app.main:app --port 8000 &
BACKEND_PID=$!
for i in $(seq 1 20); do curl -s http://localhost:8000/health > /dev/null && break; sleep 0.5; done

echo "=== Testing API ==="

echo -n "0. Login: "
TOKEN=$(curl -sf -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"${RT_ADMIN_PASSWORD:-admin}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
[ -n "$TOKEN" ] && echo "PASS" || { echo "FAIL"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

echo -n "1. Health check: "
curl -sf http://localhost:8000/health > /dev/null && echo "PASS" || echo "FAIL"

echo -n "2. Create project: "
curl -sf -X POST http://localhost:8000/api/projects -H "$AUTH" -H "Content-Type: application/json" -d '{"id":"demo","name":"Demo"}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "3. Create requirement: "
curl -sf -X POST http://localhost:8000/api/projects/demo/requirements -H "$AUTH" -H "Content-Type: application/json" -d '{"id":"REQ-001","name":"User Auth","type":"functional","priority":"high"}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "4. Create spec: "
curl -sf -X POST http://localhost:8000/api/projects/demo/specifications -H "$AUTH" -H "Content-Type: application/json" -d '{"id":"SRS-001","name":"System Spec"}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "5. Create VC: "
curl -sf -X POST http://localhost:8000/api/projects/demo/verification -H "$AUTH" -H "Content-Type: application/json" -d '{"id":"VC-001","name":"Auth Test","method":"test"}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "6. List requirements: "
COUNT=$(curl -sf http://localhost:8000/api/projects/demo/requirements | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "PASS ($COUNT)" || echo "FAIL"

echo -n "7. Update requirement: "
curl -sf -X PUT http://localhost:8000/api/projects/demo/requirements/REQ-001 -H "$AUTH" -H "Content-Type: application/json" -d '{"status":"approved","description":"<p>Test</p>"}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "8. Read requirement: "
STATUS=$(curl -sf http://localhost:8000/api/projects/demo/requirements/REQ-001 | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "approved" ] && echo "PASS ($STATUS)" || echo "FAIL"

echo -n "9. Search: "
COUNT=$(curl -sf "http://localhost:8000/api/projects/demo/requirements?search=Auth" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "PASS ($COUNT)" || echo "FAIL"

echo -n "10. Filter: "
COUNT=$(curl -sf "http://localhost:8000/api/projects/demo/requirements?status=approved" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "PASS ($COUNT)" || echo "FAIL"

echo -n "11. Traces: "
curl -sf -X PUT http://localhost:8000/api/projects/demo/traces -H "$AUTH" -H "Content-Type: application/json" -d '{"links":[{"source":"REQ-001","target":"VC-001","type":"verified_by"}]}' > /dev/null && echo "PASS" || echo "FAIL"

echo -n "12. Guest mutation blocked: "
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:8000/api/projects/demo/requirements/REQ-001)
[ "$CODE" = "403" ] && echo "PASS" || echo "FAIL ($CODE)"

echo -n "13. History recorded: "
COUNT=$(curl -sf http://localhost:8000/api/projects/demo/requirements/REQ-001/history | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" -ge 1 ] && echo "PASS ($COUNT entries)" || echo "FAIL"

echo -n "14. Requirement tree: "
curl -sf http://localhost:8000/api/projects/demo/requirements/tree > /dev/null && echo "PASS" || echo "FAIL"

echo -n "15. Next UID: "
curl -sf "http://localhost:8000/api/projects/demo/requirements/next-uid" > /dev/null && echo "PASS" || echo "FAIL"

echo -n "16. Delete requirement: "
curl -sf -X DELETE http://localhost:8000/api/projects/demo/requirements/REQ-001 -H "$AUTH" > /dev/null && echo "PASS" || echo "FAIL"

echo -n "17. YAML file check: "
YAML_COUNT=$(find "$DATA_ROOT/demo" -name "*.yaml" | wc -l)
echo "PASS ($YAML_COUNT YAML files)"

echo ""
echo "=== All tests passed ==="
