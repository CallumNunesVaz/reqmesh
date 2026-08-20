#!/usr/bin/env bash
# CI configuration invariants that only break at run time, hours later.
#
# The e2e job runs inside the official Playwright container so no `apt-get`
# runs — the v0.3.4 release hung for 5h59m25s in `playwright install
# --with-deps` against an Ubuntu mirror. That fix trades an apt dependency for
# a version coupling: the browser bundle baked into the image and the
# `@playwright/test` client installed by `npm ci` must be the same version.
# Nothing enforces that but a comment, and `package.json` declares a caret
# range, so a lockfile refresh can drift them apart silently.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

# ══════════════════════════════════════════════════════════════════════════════
section "playwright container tag matches the installed client"
# ══════════════════════════════════════════════════════════════════════════════

# e.g. "        image: mcr.microsoft.com/playwright:v1.62.1-noble"
image_tag="$(grep -oP 'mcr\.microsoft\.com/playwright:v\K[0-9]+\.[0-9]+\.[0-9]+' \
             "$REPO/.github/workflows/ci.yml" | head -1)"

# The version `npm ci` will actually install, from the lockfile — not the caret
# range in package.json, which is what makes this drift possible.
lock_version="$(python3 -c "
import json, sys
lock = json.load(open('$REPO/frontend/package-lock.json'))
for k, v in (lock.get('packages') or {}).items():
    if k.endswith('node_modules/@playwright/test'):
        print(v.get('version', '')); break
" 2>/dev/null)"

check "ci.yml pins a playwright container tag" \
      "$([ -n "$image_tag" ] && echo yes || echo no)" "yes"

check "package-lock resolves @playwright/test" \
      "$([ -n "$lock_version" ] && echo yes || echo no)" "yes"

check "container tag == locked client version ($image_tag vs $lock_version)" \
      "$image_tag" "$lock_version"

# ══════════════════════════════════════════════════════════════════════════════
section "every CI job is bounded"
# ══════════════════════════════════════════════════════════════════════════════
# GitHub's default job timeout is 360 minutes. One unbounded job burned a full
# six-hour runner slot on a stalled apt mirror and blocked the v0.3.4 release.

missing="$(python3 -c "
import yaml, pathlib
bad = []
for f in sorted(pathlib.Path('$REPO/.github/workflows').glob('*.yml')):
    doc = yaml.safe_load(f.read_text()) or {}
    for name, job in (doc.get('jobs') or {}).items():
        if 'timeout-minutes' not in job:
            bad.append(f'{f.name}:{name}')
print(','.join(bad))
" 2>/dev/null)"

check "no workflow job is missing timeout-minutes" "$missing" ""
