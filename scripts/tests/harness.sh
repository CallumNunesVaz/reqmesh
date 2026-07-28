#!/usr/bin/env bash
# Shared assertions for the installer test scripts.
#
# Sourced, never run directly. Each test script sources this, then defines its
# own cases; run.sh executes them all and aggregates the result.
#
# These scripts exercise scripts/lib.sh and scripts/wizard.sh directly by
# sourcing them and calling their functions — there is no separate test
# framework, and none is needed for shell. They must be safe to run on a
# developer machine: nothing here installs packages, touches /opt, binds a
# port, or calls sudo.

# shellcheck disable=SC2034  # REPO is used by the sourcing script
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

PASS=0
FAIL=0

ok()   { printf '  \033[0;32mPASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  \033[0;31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }

# check <label> <actual> <expected>
check() {
    if [ "$2" = "$3" ]; then
        ok "$1"
    else
        bad "$1 (expected [$3] got [$2])"
    fi
}

section() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

# Print the tally and exit non-zero if anything failed. Used as the last line
# of every test script.
finish() {
    printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
    [ "$FAIL" -eq 0 ]
}
