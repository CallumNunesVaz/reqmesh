#!/usr/bin/env bash
#
# Launch the packaged desktop app headless and wait for its backend /health to
# answer. Exits non-zero if the app dies first or health does not come up within
# HEALTH_TIMEOUT seconds — the boot step of the CI desktop-package job, factored
# out so it can be run identically there and from a developer machine.
#
#   APP            path to the packaged binary (default: detected under release/linux-unpacked)
#   PORT           RT_PORT the shell passes through (default: 8787)
#   HEALTH_TIMEOUT seconds to wait (default: 60)
#
# Electron needs a display to create its window, so the app is launched under a
# virtual X server: xvfb-run is required. Chromium's `--headless=new` was tried
# as a dependency-free fallback and removed — Electron segfaults in that mode
# here, and the crash surfaces as "app exited before the backend became
# healthy", which blames the app for a missing display and sends you looking in
# entirely the wrong place.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8787}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"

if [ -z "${APP:-}" ]; then
  # The unpacked dir carries one main executable (reqmesh / reqmesh-desktop)
  # plus Chromium helpers (chrome_crashpad_handler, chrome-sandbox) — match the
  # product's own binary, not the helpers.
  APP="$(find "$ROOT/desktop/release/linux-unpacked" -maxdepth 1 -type f -perm -u+x \
    -name 'reqmesh*' ! -name 'chrome*' -print -quit)"
fi
if [ -z "$APP" ] || [ ! -x "$APP" ]; then
  echo "error: packaged app not found (run: cd desktop && npm run build)" >&2
  exit 1
fi

export RT_PORT="$PORT"
export RT_PROFILE="${RT_PROFILE:-personal}"

# setsid puts the shell in its own process group so cleanup can reap the whole
# tree (Electron + the backend binary it spawns) in one kill.
if ! command -v xvfb-run >/dev/null 2>&1; then
  echo "error: xvfb-run not found — this check needs a virtual display." >&2
  echo "  Debian/Ubuntu: sudo apt-get install -y xvfb" >&2
  echo "  Fedora/RHEL:   sudo dnf install -y xorg-x11-server-Xvfb" >&2
  exit 1
fi
setsid xvfb-run -a "$APP" --no-sandbox --disable-gpu </dev/null &
APP_PID=$!

cleanup() {
  # SIGTERM first so the backend can flush its git autocommit queue, then
  # SIGKILL the group after a grace period in case Electron's GPU/network
  # processes refuse the polite shutdown (they do, under headless mode).
  kill -TERM -- -"$APP_PID" 2>/dev/null || true
  pkill -TERM -f 'reqmesh[-]backend' 2>/dev/null || true
  sleep 1
  kill -KILL -- -"$APP_PID" 2>/dev/null || true
  pkill -KILL -f 'reqmesh[-]backend' 2>/dev/null || true
}
trap cleanup EXIT

URL="http://127.0.0.1:$PORT/health"
echo "waiting for backend health at $URL (timeout ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "error: app exited before the backend became healthy" >&2
    exit 1
  fi
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "backend healthy"
    exit 0
  fi
  sleep 1
done

echo "error: backend did not become healthy within ${HEALTH_TIMEOUT}s" >&2
exit 1
