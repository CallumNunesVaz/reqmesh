#!/usr/bin/env bash
#
# Drop stale Docker image archives from published GitHub Releases.
#
#   scripts/prune_release_images.sh [--keep=N] [--suffix=SFX] [--dry-run]
#
# The release workflow attaches a `docker save | gzip` archive
# (`reqmesh-vX.Y.Z-image.tar.gz`, ~150 MB and growing) to every release. Only
# the newest ones are useful: the in-app updater reads release *metadata* only,
# the online update path pulls from ghcr.io, and the offline path loads an
# archive the operator uploads by hand. Old archives are never fetched.
#
# This removes that one asset from releases outside the keep-window. Releases,
# tags, notes, install tarballs and .sha256 files are left alone, so every
# version stays installable and `releases/latest` is unaffected.
#
# Options:
#   --keep=N     Retain the archive on the N most recent releases (default 2:
#                the current release plus one rollback target).
#   --suffix=SFX Asset suffix to prune (default `-image.tar.gz`). The desktop
#                AppImage is ~157 MB per release and is pruned on the same
#                terms — an old release's AppImage is never fetched, because
#                the desktop app has no in-place updater.
#   --dry-run    List what would be deleted; delete nothing.
#
# Needs `gh` on PATH and GH_TOKEN in the environment (both are already true on
# a GitHub Actions runner).
#
set -euo pipefail

KEEP=2
DRY_RUN=0
# The suffix the release workflow gives the archive (release.yml, "Save image
# archive for offline updates"). Matching on it is what keeps the install
# tarball and its .sha256 out of scope.
SUFFIX="-image.tar.gz"
for arg in "$@"; do
  case "$arg" in
    --keep=*)   KEEP="${arg#*=}" ;;
    --keep)     echo "usage: --keep=N (not '--keep N')" >&2; exit 2 ;;
    --suffix=*) SUFFIX="${arg#*=}" ;;
    --suffix)   echo "usage: --suffix=SFX (not '--suffix SFX')" >&2; exit 2 ;;
    --dry-run)  DRY_RUN=1 ;;
    *)          echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -z "$SUFFIX" ]; then
  echo "error: --suffix must not be empty (it would match every asset)" >&2
  exit 2
fi

case "$KEEP" in
  ''|*[!0-9]*) echo "error: --keep must be a non-negative integer, got '$KEEP'" >&2; exit 2 ;;
esac

command -v gh >/dev/null || { echo "error: gh is not on PATH" >&2; exit 1; }
[ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ] || { echo "error: GH_TOKEN is not set" >&2; exit 1; }

# Newest first. Drafts have no published date and are not something we prune.
mapfile -t TAGS < <(
  gh release list --limit 200 --json tagName,publishedAt,isDraft \
    | jq -r '[.[] | select(.isDraft | not)]
             | sort_by(.publishedAt) | reverse | .[].tagName'
)

if [ "${#TAGS[@]}" -eq 0 ]; then
  echo "==> No published releases found; nothing to do."
  exit 0
fi

echo "==> ${#TAGS[@]} published releases; keeping the archive on the newest $KEEP"
if [ "$DRY_RUN" = "1" ]; then
  echo "==> DRY RUN — nothing will be deleted"
fi

for tag in "${TAGS[@]:0:$KEEP}"; do
  echo "    keep   $tag"
done

deleted=0
freed=0
failed=0

for tag in "${TAGS[@]:$KEEP}"; do
  # Re-read per tag rather than trusting a cached list: another run (or the
  # release workflow) may have removed these already, and this script is called
  # on every release.
  mapfile -t assets < <(
    gh release view "$tag" --json assets \
      | jq -r --arg sfx "$SUFFIX" '.assets[] | select(.name | endswith($sfx)) | "\(.name)\t\(.size)"'
  )
  for row in "${assets[@]}"; do
    [ -n "$row" ] || continue
    name="${row%%$'\t'*}"
    size="${row##*$'\t'}"
    mb=$(( size / 1048576 ))
    if [ "$DRY_RUN" = "1" ]; then
      echo "    would delete  $tag  $name  (${mb} MB)"
      deleted=$(( deleted + 1 ))
      freed=$(( freed + size ))
      continue
    fi
    # A missing asset is success, not failure — the point is that it is gone.
    if gh release delete-asset "$tag" "$name" --yes 2>/dev/null; then
      echo "    deleted  $tag  $name  (${mb} MB)"
      deleted=$(( deleted + 1 ))
      freed=$(( freed + size ))
    else
      echo "    FAILED   $tag  $name" >&2
      failed=$(( failed + 1 ))
    fi
  done
done

if [ "$DRY_RUN" = "1" ]; then
  echo "==> would free $(( freed / 1048576 )) MB across $deleted asset(s)"
else
  echo "==> freed $(( freed / 1048576 )) MB across $deleted asset(s)"
fi
if [ "$failed" -gt 0 ]; then
  echo "==> $failed deletion(s) failed" >&2
  exit 1
fi
