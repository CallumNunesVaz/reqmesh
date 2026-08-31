#!/usr/bin/env bash
#
# Produce the release notes for a tag, on stdout.
#
#   scripts/release_notes.sh v0.6.0 [options]
#
# Notes reach users in two places, which is why this is a script of its own
# rather than a heredoc inside release.sh: the annotated tag message, and — via
# the GitHub release body that updater.py fetches — a <pre> block inside the
# in-app updater on the System page. Whatever comes out of here is read by
# someone deciding whether to apply an update.
#
# Sources, in precedence order:
#   1. --notes-file FILE   verbatim, for notes written by hand
#   2. CHANGELOG.md        the body of the `## [Unreleased]` section
#   3. the commit log      grouped by conventional-commit type, deduplicated
#
# Options:
#   --notes-file FILE  Use FILE verbatim and ignore every other source.
#   --changelog FILE   CHANGELOG path (default: CHANGELOG.md at the repo root).
#   --from TAG         Range start for the commit-log fallback (default: the
#                      most recent tag reachable from HEAD).
#   --no-changelog     Skip the CHANGELOG and go straight to the commit log.
#   --promote X.Y.Z    Rewrite the CHANGELOG in place instead of printing notes:
#                      retitle `## [Unreleased]` as `## [X.Y.Z] - <today>` and
#                      open a fresh empty `## [Unreleased]` above it. Lives here
#                      rather than in its own script so the code that *reads*
#                      the Unreleased section and the code that *rewrites* it
#                      cannot drift apart. No-op when the section is empty.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TAG=""
NOTES_FILE=""
CHANGELOG="$ROOT/CHANGELOG.md"
FROM=""
USE_CHANGELOG=1
PROMOTE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --notes-file)   NOTES_FILE="${2:-}"; shift 2 ;;
    --changelog)    CHANGELOG="${2:-}"; shift 2 ;;
    --from)         FROM="${2:-}"; shift 2 ;;
    --no-changelog) USE_CHANGELOG=0; shift ;;
    --promote)      PROMOTE="${2:-}"; shift 2 ;;
    -*)             echo "release_notes: unknown option: $1" >&2; exit 2 ;;
    *)              TAG="$1"; shift ;;
  esac
done

if [ -z "$TAG" ] && [ -z "$PROMOTE" ]; then
  echo "usage: release_notes.sh <tag> [--notes-file F] [--changelog F] [--from TAG] [--no-changelog]" >&2
  echo "       release_notes.sh --promote X.Y.Z [--changelog F]" >&2
  exit 2
fi

# ── Promotion mode ───────────────────────────────────────────────────────────
if [ -n "$PROMOTE" ]; then
  [ -f "$CHANGELOG" ] || { echo "release_notes: no changelog at $CHANGELOG" >&2; exit 1; }
  CHANGELOG="$CHANGELOG" VERSION="$PROMOTE" /usr/bin/python3 - <<'PYEOF'
import datetime, os, re, sys

path = os.environ["CHANGELOG"]
version = os.environ["VERSION"]
text = open(path, encoding="utf-8").read()

m = re.search(r"^## \[Unreleased\]\s*$", text, re.M)
if not m:
    sys.exit(f"release_notes: no '## [Unreleased]' heading in {path}")

nxt = re.search(r"^## ", text[m.end():], re.M)
end = m.end() + (nxt.start() if nxt else len(text) - m.end())
body = text[m.end():end]

# An untouched skeleton is not a release entry; leave the file alone so the
# caller falls back to the commit log rather than publishing empty headings.
if not re.sub(r"^### .*$", "", body, flags=re.M).strip():
    sys.exit(0)

today = datetime.date.today().isoformat()
replacement = f"## [Unreleased]\n\n## [{version}] - {today}\n{body.rstrip()}\n\n"
open(path, "w", encoding="utf-8").write(text[:m.start()] + replacement + text[end:])
PYEOF
  exit 0
fi

# ── 1. An explicit file wins outright ────────────────────────────────────────
if [ -n "$NOTES_FILE" ]; then
  if [ ! -f "$NOTES_FILE" ]; then
    echo "release_notes: notes file not found: $NOTES_FILE" >&2
    exit 1
  fi
  cat "$NOTES_FILE"
  exit 0
fi

# ── 2. The curated CHANGELOG entry ───────────────────────────────────────────
#
# Reads the body between `## [Unreleased]` and the next `## ` heading. Emitted
# only when it holds something other than blank lines and empty Keep a Changelog
# subheadings — an untouched skeleton is not curation, and silently shipping
# "### Added" with nothing under it is worse than the commit log.
changelog_body() {
  [ -f "$CHANGELOG" ] || return 1
  awk '
    /^## \[Unreleased\]/ { inside = 1; next }
    inside && /^## /     { exit }
    inside               { print }
  ' "$CHANGELOG"
}

if [ "$USE_CHANGELOG" = "1" ]; then
  body="$(changelog_body || true)"
  # Strip blank lines and bare `### Heading` lines; whatever survives is real
  # content written by a person.
  substance="$(printf '%s\n' "$body" | sed -e 's/^[[:space:]]*$//' -e '/^### /d' | tr -d '[:space:]')"
  if [ -n "$substance" ]; then
    printf '# reqmesh %s\n\n' "$TAG"
    # Trim leading and trailing blank lines, keeping the interior intact.
    printf '%s\n' "$body" | awk 'NF {p = 1} p' | awk '{ lines[NR] = $0 } END { last = NR; while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--; for (i = 1; i <= last; i++) print lines[i] }'
    exit 0
  fi
fi

# ── 3. Commit-log fallback, grouped and deduplicated ─────────────────────────
#
# The raw `git log --pretty` list this replaces had three problems, all of them
# visible to users in the updater: the same subject appeared twice when a change
# landed on two integration branches before merging, conventional-commit
# prefixes read as noise, and there was no ordering by relevance — a docs commit
# sat above a security fix.
if [ -z "$FROM" ]; then
  FROM="$(git -C "$ROOT" describe --tags --abbrev=0 2>/dev/null || true)"
fi

if [ -n "$FROM" ]; then
  RANGE="${FROM}..HEAD"
  HEADER="Changes since ${FROM}:"
else
  RANGE="HEAD"
  HEADER="Initial tracked release."
fi

# Hash first, then subject, separated by US (0x1f) — a subject can contain any
# punctuation, and NUL cannot be used because command substitution strips it
# (which silently emptied every hash the first time round).
raw="$(git -C "$ROOT" log "$RANGE" --no-merges --pretty=$'%h\x1f%s')"

printf '# reqmesh %s\n\n%s\n' "$TAG" "$HEADER"

emit_group() {
  local label="$1" types="$2" section=""
  section="$(printf '%s\n' "$raw" | awk -F'\037' -v types="$types" '
    BEGIN { n = split(types, t, ","); for (i = 1; i <= n; i++) want[t[i]] = 1 }
    {
      hash = $1; subject = $2
      # Split a conventional-commit prefix: type(scope)!: description
      if (match(subject, /^[a-z]+(\([^)]*\))?!?: /)) {
        prefix = substr(subject, 1, RLENGTH)
        rest   = substr(subject, RLENGTH + 1)
        type   = prefix; sub(/[(!:].*$/, "", type)
        scope  = ""
        if (match(prefix, /\(([^)]*)\)/)) scope = substr(prefix, RSTART + 1, RLENGTH - 2)
      } else {
        type = "other"; rest = subject; scope = ""
      }
      if (!(type in want)) next
      key = type "\037" scope "\037" rest
      if (key in seen) next          # same change landed twice — show it once
      seen[key] = 1
      print (scope == "" ? "- " rest " (" hash ")" : "- **" scope "**: " rest " (" hash ")")
    }
  ')"
  [ -n "$section" ] || return 0
  printf '\n### %s\n\n%s\n' "$label" "$section"
}

# Ordered by what a user upgrading actually needs to know first.
emit_group "Security"     "security"
emit_group "Features"     "feat"
emit_group "Fixes"        "fix"
emit_group "Performance"  "perf"
emit_group "Build & CI"   "build,ci,chore"
emit_group "Documentation" "docs"
emit_group "Tests"        "test,refactor,style,other"
