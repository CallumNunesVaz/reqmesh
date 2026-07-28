#!/usr/bin/env bash
#
# Run the installer test suite.
#
#   scripts/tests/run.sh            # all suites
#   scripts/tests/run.sh test_e2e   # one suite
#
# These cover scripts/lib.sh and scripts/wizard.sh: Caddyfile rendering, the
# summary box, credential writing, port and LAN-address detection, input
# validation, the plain-text prompt fallback, and the wizard's phase flow.
#
# Safe to run anywhere — nothing installs packages, writes outside a temp
# directory, binds a port, or calls sudo. Requires bash, awk, sed and ss.
#
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

SUITES=(test_wizard.sh test_flow.sh test_e2e.sh)
if [ $# -gt 0 ]; then
    SUITES=()
    for arg in "$@"; do
        SUITES+=("${arg%.sh}.sh")
    done
fi

failed=()
for suite in "${SUITES[@]}"; do
    printf '\n\033[1;36m═══ %s ═══\033[0m\n' "$suite"
    # stdin closed: a suite that regressed into waiting for input should fail,
    # not hang a CI job.
    if ! bash "$suite" </dev/null; then
        failed+=("$suite")
    fi
done

echo
if [ ${#failed[@]} -eq 0 ]; then
    printf '\033[0;32m✓ all suites passed\033[0m\n'
    exit 0
fi
printf '\033[0;31m✗ failing suites: %s\033[0m\n' "${failed[*]}"
exit 1
