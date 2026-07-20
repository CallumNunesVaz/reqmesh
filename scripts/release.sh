#!/usr/bin/env bash
#
# Cut a reqmesh release.
#
#   scripts/release.sh patch|minor|major|X.Y.Z [options]
#
# Steps: bump the version everywhere, regenerate release notes, build the bundle
# locally as a smoke test, commit, create an annotated tag, and push. Pushing the
# tag triggers the GitHub Actions release workflow, which builds the artifacts,
# publishes the GitHub Release, and pushes the Docker image to ghcr.io.
#
# Options:
#   --dry-run     Do everything except commit/tag/push (leaves version files bumped).
#   --no-push     Commit and tag locally but don't push.
#   --no-verify   Skip the local bundle build smoke test.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET=""
DRY_RUN=0
NO_PUSH=0
NO_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=1 ;;
    --no-push)   NO_PUSH=1 ;;
    --no-verify) NO_VERIFY=1 ;;
    -*)          echo "unknown option: $arg" >&2; exit 2 ;;
    *)           TARGET="$arg" ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "usage: scripts/release.sh patch|minor|major|X.Y.Z [--dry-run] [--no-push] [--no-verify]" >&2
  exit 2
fi

# ── Preconditions ────────────────────────────────────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" != "main" ] && [ "$DRY_RUN" != "1" ]; then
  echo "error: releases are cut from 'main' (on '$BRANCH'). Use --dry-run to test elsewhere." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is dirty — commit or stash first." >&2
  git status --short
  exit 1
fi

CURRENT="$(cat VERSION)"
NEW="$(/usr/bin/python3 scripts/set_version.py "$TARGET")"
TAG="v${NEW}"
echo "==> Releasing ${CURRENT} -> ${NEW} (${TAG})"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists." >&2
  git checkout -- VERSION backend/app/core/_version.py frontend/package.json desktop/package.json
  exit 1
fi

# ── Release notes: commits since the last tag ────────────────────────────────
LAST_TAG="$(git describe --tags --abbrev=0 2>/dev/null || true)"
NOTES_FILE="$(mktemp)"
{
  echo "# reqmesh ${TAG}"
  echo
  if [ -n "$LAST_TAG" ]; then
    echo "Changes since ${LAST_TAG}:"
    echo
    git log "${LAST_TAG}..HEAD" --pretty="- %s (%h)" --no-merges
  else
    echo "Initial tracked release."
    echo
    git log -20 --pretty="- %s (%h)" --no-merges
  fi
} > "$NOTES_FILE"
echo "==> Release notes:"
sed 's/^/    /' "$NOTES_FILE"

# ── Local smoke build ────────────────────────────────────────────────────────
if [ "$NO_VERIFY" != "1" ]; then
  echo "==> Verifying bundle builds"
  RELEASE_NOTES_FILE="$NOTES_FILE" bash scripts/build_bundle.sh
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "==> Dry run: version files bumped to ${NEW}, no commit/tag made."
  echo "    Revert with: git checkout -- VERSION backend/app/core/_version.py frontend/package.json desktop/package.json"
  rm -f "$NOTES_FILE"
  exit 0
fi

# ── Commit, tag, push ────────────────────────────────────────────────────────
git add VERSION backend/app/core/_version.py frontend/package.json desktop/package.json
git commit -m "release: ${TAG}"
git tag -a "$TAG" -F "$NOTES_FILE"
rm -f "$NOTES_FILE"

if [ "$NO_PUSH" = "1" ]; then
  echo "==> Committed and tagged ${TAG} locally (not pushed)."
  echo "    Push with: git push origin ${BRANCH} && git push origin ${TAG}"
  exit 0
fi

git push origin "$BRANCH"
git push origin "$TAG"
echo "==> Pushed ${TAG}. GitHub Actions will build artifacts and publish the release."
