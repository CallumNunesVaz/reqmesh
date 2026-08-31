#!/usr/bin/env bash
# Release-notes generation and CHANGELOG promotion.
#
# These notes are not an internal artifact: updater.py fetches the GitHub
# release body and SystemPage.tsx renders it in a <pre> to whoever is deciding
# whether to apply an update. v0.5.0 shipped a raw `git log` dump that named an
# internal review file, carried conventional-commit prefixes and bare SHAs, and
# listed one change twice because it landed on two integration branches. Each
# case below pins one property of the replacement.
#
# Everything runs against throwaway fixtures in a temp dir — no repo state is
# read for the CHANGELOG cases, and the commit-log case builds its own git repo.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

NOTES="$REPO/scripts/release_notes.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ══════════════════════════════════════════════════════════════════════════════
section "an explicit --notes-file wins outright"
# ══════════════════════════════════════════════════════════════════════════════

printf 'Hand written.\n' > "$TMP/hand.md"
cat > "$TMP/CL-full.md" <<'EOF'
# Changelog

## [Unreleased]

### Added

- Something curated.

## [0.1.0] - 2026-01-01
EOF

out="$(bash "$NOTES" v9.9.9 --notes-file "$TMP/hand.md" --changelog "$TMP/CL-full.md")"
check "uses the file verbatim" "$out" "Hand written."

bash "$NOTES" v9.9.9 --notes-file "$TMP/missing.md" >/dev/null 2>&1
check "a missing notes file is an error" "$?" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "the CHANGELOG [Unreleased] section is preferred over the commit log"
# ══════════════════════════════════════════════════════════════════════════════

out="$(bash "$NOTES" v9.9.9 --changelog "$TMP/CL-full.md")"
check "includes the curated entry" \
      "$(printf '%s\n' "$out" | grep -c 'Something curated')" "1"
check "does not leak the previous release's section" \
      "$(printf '%s\n' "$out" | grep -c '0.1.0')" "0"
check "titles the notes with the tag" \
      "$(printf '%s\n' "$out" | head -1)" "# reqmesh v9.9.9"

# An untouched Keep a Changelog skeleton is not curation. Publishing empty
# "### Added" headings would be worse than the commit log, so it must fall
# through rather than be treated as content.
cat > "$TMP/CL-skeleton.md" <<'EOF'
# Changelog

## [Unreleased]

### Added

### Fixed

## [0.1.0] - 2026-01-01
EOF

out="$(cd "$REPO" && bash "$NOTES" v9.9.9 --changelog "$TMP/CL-skeleton.md")"
check "an empty skeleton falls through to the commit log" \
      "$(printf '%s\n' "$out" | grep -c '^### Added$')" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "the commit-log fallback groups, deduplicates and strips prefixes"
# ══════════════════════════════════════════════════════════════════════════════

REPO_FIXTURE="$TMP/repo"
mkdir -p "$REPO_FIXTURE"
(
  cd "$REPO_FIXTURE" || exit 1
  git init -q .
  git config user.email t@example.com
  git config user.name Test
  git commit -q --allow-empty -m "initial"
  git tag v0.1.0
  git commit -q --allow-empty -m "feat(parametrics): margin gauges"
  git commit -q --allow-empty -m "fix(auth): stop locking the wrong account"
  # The same change landed twice, which is what produced the duplicate entry in
  # the real v0.5.0 notes.
  git commit -q --allow-empty -m "build(supply-chain): hash-pin the backend deps"
  git commit -q --allow-empty -m "build(supply-chain): hash-pin the backend deps"
  git commit -q --allow-empty -m "docs: record a review"
  git commit -q --allow-empty -m "no conventional prefix here"
) >/dev/null 2>&1

# The script resolves its repo from its own location, so run a copy from inside
# the fixture to make the fixture the repo under test.
mkdir -p "$REPO_FIXTURE/scripts"
cp "$NOTES" "$REPO_FIXTURE/scripts/release_notes.sh"
out="$(cd "$REPO_FIXTURE" && bash scripts/release_notes.sh v0.2.0 --no-changelog --from v0.1.0)"

check "groups features under a Features heading" \
      "$(printf '%s\n' "$out" | grep -c '^### Features$')" "1"
check "renders the scope, not the raw prefix" \
      "$(printf '%s\n' "$out" | grep -c '^- \*\*parametrics\*\*: margin gauges')" "1"
check "no conventional-commit prefix survives into a bullet" \
      "$(printf '%s\n' "$out" | grep -cE '^- (feat|fix|build|docs)\(')" "0"
check "a change committed twice appears once" \
      "$(printf '%s\n' "$out" | grep -c 'hash-pin the backend deps')" "1"
check "a subject with no prefix is still listed" \
      "$(printf '%s\n' "$out" | grep -c 'no conventional prefix here')" "1"
check "features are ordered above build noise" \
      "$([ "$(printf '%s\n' "$out" | grep -n '^### Features$' | cut -d: -f1)" \
          -lt "$(printf '%s\n' "$out" | grep -n '^### Build & CI$' | cut -d: -f1)" ] \
          && echo yes || echo no)" "yes"

# ══════════════════════════════════════════════════════════════════════════════
section "--promote retitles [Unreleased] and opens a fresh one"
# ══════════════════════════════════════════════════════════════════════════════

cp "$TMP/CL-full.md" "$TMP/CL-promote.md"
bash "$NOTES" --promote 0.2.0 --changelog "$TMP/CL-promote.md"

check "the promoted version gets a dated heading" \
      "$(grep -cE '^## \[0\.2\.0\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$' "$TMP/CL-promote.md")" "1"
check "a fresh empty [Unreleased] is left at the top" \
      "$(grep -c '^## \[Unreleased\]$' "$TMP/CL-promote.md")" "1"
check "[Unreleased] sits above the promoted version" \
      "$([ "$(grep -n '^## \[Unreleased\]$' "$TMP/CL-promote.md" | cut -d: -f1)" \
          -lt "$(grep -n '^## \[0\.2\.0\]' "$TMP/CL-promote.md" | cut -d: -f1)" ] \
          && echo yes || echo no)" "yes"
check "the curated content moved into the version section" \
      "$(awk '/^## \[0\.2\.0\]/{f=1;next} f&&/^## /{exit} f' "$TMP/CL-promote.md" | grep -c 'Something curated')" "1"
check "the earlier release is untouched" \
      "$(grep -c '^## \[0\.1\.0\] - 2026-01-01$' "$TMP/CL-promote.md")" "1"

# Promoting again with nothing new must not manufacture an empty release entry.
bash "$NOTES" --promote 0.3.0 --changelog "$TMP/CL-promote.md"
check "promoting an empty [Unreleased] is a no-op" \
      "$(grep -c '^## \[0\.3\.0\]' "$TMP/CL-promote.md")" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "release.sh and the workflow stay wired to all of this"
# ══════════════════════════════════════════════════════════════════════════════

# Counting occurrences would break on a comment edit; assert the behaviour
# instead — the generator is invoked, and the inline `git log` it replaced is
# gone, so notes cannot silently revert to the raw dump.
check "release.sh invokes the notes generator" \
      "$(grep -cE '^\s*bash scripts/release_notes\.sh ' "$REPO/scripts/release.sh")" "3"
check "the inline git-log generation is gone" \
      "$(grep -c 'pretty="- %s (%h)"' "$REPO/scripts/release.sh")" "0"
check "release.sh stages the CHANGELOG with the version bump" \
      "$(grep -c 'git add "\$CHANGELOG_FILE"' "$REPO/scripts/release.sh")" "1"
check "a CHANGELOG exists at the repo root" \
      "$([ -f "$REPO/CHANGELOG.md" ] && echo yes || echo no)" "yes"
check "the changelog has an [Unreleased] section to write into" \
      "$(grep -c '^## \[Unreleased\]$' "$REPO/CHANGELOG.md")" "1"

finish
