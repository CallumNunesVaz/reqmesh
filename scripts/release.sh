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
#   --dry-run          Do everything except commit/tag/push (leaves version files bumped).
#   --no-push          Commit and tag locally but don't push.
#   --no-verify        Skip the local bundle build smoke test.
#   --notes-file FILE  Use FILE as the release notes verbatim, overriding both
#                      CHANGELOG.md and the commit-log fallback.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET=""
DRY_RUN=0
NO_PUSH=0
NO_VERIFY=0
NOTES_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)    DRY_RUN=1; shift ;;
    --no-push)    NO_PUSH=1; shift ;;
    --no-verify)  NO_VERIFY=1; shift ;;
    --notes-file) NOTES_OVERRIDE="${2:-}"; shift 2 ;;
    -*)           echo "unknown option: $1" >&2; exit 2 ;;
    *)            TARGET="$1"; shift ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "usage: scripts/release.sh patch|minor|major|X.Y.Z [--dry-run] [--no-push] [--no-verify] [--notes-file FILE]" >&2
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
# Ask set_version.py which files a bump touches rather than keeping a second
# list here. The hardcoded copy this replaces omitted scripts/install.sh, so the
# ref-pin bump it makes was never staged: v0.1.2 published an installer still
# pointing at v0.1.1's lib.sh/wizard.sh.
mapfile -t VERSIONED_FILES < <(/usr/bin/python3 scripts/set_version.py --files)
if [ "${#VERSIONED_FILES[@]}" -eq 0 ]; then
  echo "error: set_version.py --files returned nothing." >&2
  exit 1
fi

NEW="$(/usr/bin/python3 scripts/set_version.py "$TARGET")"
TAG="v${NEW}"
echo "==> Releasing ${CURRENT} -> ${NEW} (${TAG})"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists." >&2
  git checkout -- "${VERSIONED_FILES[@]}"
  exit 1
fi

# ── Release notes ────────────────────────────────────────────────────────────
#
# These are not just the tag message: updater.py serves the GitHub release body
# to the System page, which renders it to anyone deciding whether to update. See
# scripts/release_notes.sh for the source precedence (--notes-file, then
# CHANGELOG.md's [Unreleased], then a grouped commit log).
NOTES_FILE="$(mktemp)"
if [ -n "$NOTES_OVERRIDE" ]; then
  bash scripts/release_notes.sh "$TAG" --notes-file "$NOTES_OVERRIDE" > "$NOTES_FILE"
else
  bash scripts/release_notes.sh "$TAG" > "$NOTES_FILE"
fi
echo "==> Release notes:"
sed 's/^/    /' "$NOTES_FILE"

CHANGELOG_FILE="$ROOT/CHANGELOG.md"

# ── Local smoke build ────────────────────────────────────────────────────────
if [ "$NO_VERIFY" != "1" ]; then
  echo "==> Verifying bundle builds"
  RELEASE_NOTES_FILE="$NOTES_FILE" bash scripts/build_bundle.sh
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "==> Dry run: version files bumped to ${NEW}, no commit/tag made."
  echo "    Revert with: git checkout -- ${VERSIONED_FILES[*]}"
  rm -f "$NOTES_FILE"
  exit 0
fi

# ── Commit, tag, push ────────────────────────────────────────────────────────
#
# Retitle [Unreleased] as this version so the entry is dated and a fresh section
# is open for the next cycle. After the dry-run exit above, so a dry run never
# leaves a mutated CHANGELOG behind — and after the notes are read, since this
# renames the very heading they come from. A no-op when the section is empty.
if [ -f "$CHANGELOG_FILE" ] && [ -z "$NOTES_OVERRIDE" ]; then
  bash scripts/release_notes.sh --promote "$NEW"
fi

git add "${VERSIONED_FILES[@]}"
# Spelled as an `if` rather than `[ -f ] && git add` so the intent survives a
# later `set -e` audit: the AND-list form is safe here but reads like a trap.
if [ -f "$CHANGELOG_FILE" ]; then
  git add "$CHANGELOG_FILE"
fi
git commit -m "release: ${TAG}"

# A file set_version.py rewrote but release.sh failed to stage would ship a tag
# whose contents disagree with the release — exactly how v0.1.2's installer kept
# v0.1.1's ref pin. Refuse to tag rather than publish that.
if [ -n "$(git status --porcelain)" ]; then
  echo "error: version bump left changes unstaged — the tag would be inconsistent." >&2
  git status --short >&2
  exit 1
fi
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
