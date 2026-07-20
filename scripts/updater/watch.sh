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
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/callumnunesvaz/reqmesh}"

TARGET_FILE="$CONTROL_DIR/update-target"
MODE_FILE="$CONTROL_DIR/update-mode"
IMAGE_FILE="$CONTROL_DIR/update-image.tar"
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

handle_pull() {
  # $1 = target version
  target="$1"
  echo "[updater] pulling reqmesh $target"
  write_status in_progress "Pulling image for $target." "$target"
  echo "REQMESH_VERSION=$target" > "$VERSION_ENV"
  if compose pull reqmesh; then
    write_status in_progress "Recreating the app on $target." "$target"
    if compose up -d reqmesh; then
      write_status in_progress "Waiting for the new version to come up." "$target"
    else
      write_status failed "Failed to recreate the container." "$target"
    fi
  else
    write_status failed "Failed to pull image for $target." "$target"
  fi
}

handle_image() {
  # Load an uploaded image archive and recreate the app on it (offline path).
  if [ ! -s "$IMAGE_FILE" ]; then
    write_status failed "No uploaded image archive found." ""
    return
  fi
  echo "[updater] loading uploaded image archive"
  write_status in_progress "Loading uploaded image…" ""
  loaded="$(docker load -i "$IMAGE_FILE" 2>&1 || true)"
  echo "[updater] $loaded"
  # Parse "Loaded image: <ref>" (or "Loaded image ID: ...").
  ref="$(echo "$loaded" | sed -n 's/^Loaded image: *//p' | head -n1)"
  rm -f "$IMAGE_FILE"
  if [ -z "$ref" ]; then
    write_status failed "Could not read image from the uploaded archive." ""
    return
  fi
  tag="${ref##*:}"
  case "$tag" in */*|"") tag="uploaded" ;; esac   # ref had no tag
  echo "[updater] loaded $ref (tag $tag); retagging to $IMAGE_REPO:$tag"
  docker tag "$ref" "$IMAGE_REPO:$tag" 2>/dev/null || true
  echo "REQMESH_VERSION=$tag" > "$VERSION_ENV"
  write_status in_progress "Recreating the app on $tag." "$tag"
  if compose up -d --force-recreate reqmesh; then
    write_status in_progress "Waiting for the new version to come up." "$tag"
  else
    write_status failed "Failed to recreate the container." "$tag"
  fi
}

echo "[updater] watching $CONTROL_DIR (compose: $DEPLOY_DIR/$COMPOSE_FILE)"

while true; do
  if [ -f "$TARGET_FILE" ]; then
    TARGET="$(head -n1 "$TARGET_FILE" | tr -d ' \t\r\n')"
    MODE="pull"
    [ -f "$MODE_FILE" ] && MODE="$(head -n1 "$MODE_FILE" | tr -d ' \t\r\n')"
    rm -f "$TARGET_FILE" "$MODE_FILE"

    if [ "$MODE" = "image" ]; then
      handle_image
    elif [ -z "$TARGET" ]; then
      write_status failed "No target version in request." ""
    else
      handle_pull "$TARGET"
    fi
  fi
  sleep "$POLL_SECONDS"
done
