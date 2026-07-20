#!/bin/sh
#
# reqmesh update sidecar.
#
# Runs in a minimal container that holds the Docker socket (which the main app
# container deliberately does NOT). It watches a control directory shared with
# the app; when the app writes an `update-target` file, this pulls the requested
# ghcr.io image tag and recreates the reqmesh service, then reports status back
# through the same directory.
#
# Expected mounts/env (see docker-compose.prod.yml, `updater` service):
#   /var/run/docker.sock   the Docker socket
#   /control               the shared control volume  (CONTROL_DIR)
#   /deploy                the deployment dir (compose file + .env, read-only)
#   COMPOSE_FILE           compose filename within /deploy
#
set -eu

CONTROL_DIR="${CONTROL_DIR:-/control}"
DEPLOY_DIR="${DEPLOY_DIR:-/deploy}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
POLL_SECONDS="${POLL_SECONDS:-5}"

TARGET_FILE="$CONTROL_DIR/update-target"
STATUS_FILE="$CONTROL_DIR/update-status.json"
VERSION_ENV="$CONTROL_DIR/version.env"

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

write_status() {
  # $1 state  $2 message  $3 target
  tmp="$STATUS_FILE.tmp"
  printf '{"state":"%s","message":"%s","target_version":"%s","updated_at":"%s"}\n' \
    "$1" "$2" "$3" "$(now)" > "$tmp"
  mv "$tmp" "$STATUS_FILE"
}

compose() {
  if [ -f "$DEPLOY_DIR/.env" ]; then
    docker compose --env-file "$DEPLOY_DIR/.env" --env-file "$VERSION_ENV" \
      -f "$DEPLOY_DIR/$COMPOSE_FILE" "$@"
  else
    docker compose --env-file "$VERSION_ENV" -f "$DEPLOY_DIR/$COMPOSE_FILE" "$@"
  fi
}

echo "[updater] watching $CONTROL_DIR (compose: $DEPLOY_DIR/$COMPOSE_FILE)"

while true; do
  if [ -f "$TARGET_FILE" ]; then
    TARGET="$(head -n1 "$TARGET_FILE" | tr -d ' \t\r\n')"
    rm -f "$TARGET_FILE"
    if [ -z "$TARGET" ]; then
      write_status failed "No target version in request." ""
    else
      echo "[updater] updating reqmesh to $TARGET"
      write_status in_progress "Pulling image for $TARGET." "$TARGET"
      echo "REQMESH_VERSION=$TARGET" > "$VERSION_ENV"
      if compose pull reqmesh; then
        write_status in_progress "Recreating the app on $TARGET." "$TARGET"
        if compose up -d reqmesh; then
          # The new app container reports the final "completed" itself, by virtue
          # of its running version matching the target.
          write_status in_progress "Waiting for the new version to come up." "$TARGET"
        else
          write_status failed "Failed to recreate the container." "$TARGET"
        fi
      else
        write_status failed "Failed to pull image for $TARGET." "$TARGET"
      fi
    fi
  fi
  sleep "$POLL_SECONDS"
done
