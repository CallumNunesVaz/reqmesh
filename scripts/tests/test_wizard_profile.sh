#!/usr/bin/env bash
# wizard.sh: p5_profile stops pinning the four security flags the chosen
# profile preset already implies, and the COOKIE_SECURE override / p6 prompts
# still behave.
set -uo pipefail

# shellcheck source=scripts/tests/harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

export COLLECTED_DIR; COLLECTED_DIR="$(mktemp -d)"
trap 'rm -rf "$COLLECTED_DIR"' EXIT
# shellcheck disable=SC1090
source "$REPO/scripts/wizard.sh"
GUMMED=false
clear() { :; }

# Run p5_profile for a profile chosen by its 1-based index (gum_choose order:
# team, hardened, personal) with the given TLS_ACTIVE value, then hand back the
# config it wrote. Stubs the prompt so no stdin beyond the choice is consumed.
run_profile() {
    local profile_num="$1" tls_active="$2"
    CFG=()
    : > "$CONFIG_FILE"
    CFG[TLS_ACTIVE]="$tls_active"
    printf '%s\n' "$profile_num" | p5_profile >/dev/null 2>&1
}

cfg_val() { grep "^$1=" "$CONFIG_FILE" | tail -1 | cut -d= -f2-; }
cfg_has() { grep -q "^$1=" "$CONFIG_FILE"; }

section "the profile no longer pins the flags the preset implies"
# 1=team 2=hardened 3=personal (gum_choose option order in p5_profile)
for entry in "1:team" "2:hardened" "3:personal"; do
    num="${entry%%:*}"; name="${entry##*:}"
    run_profile "$num" true
    check "$name writes PROFILE" "$(cfg_val PROFILE)" "$name"
    if cfg_has REQUIRE_AUTH; then bad "$name must not pin REQUIRE_AUTH"; else ok "$name does not pin REQUIRE_AUTH"; fi
done

section "COOKIE_SECURE override follows TLS activity, not the profile"
run_profile 2 false
check "hardened + TLS inactive writes COOKIE_SECURE=false" "$(cfg_val COOKIE_SECURE)" "false"
run_profile 2 true
if cfg_has COOKIE_SECURE; then bad "hardened + TLS active must not write COOKIE_SECURE"; else ok "hardened + TLS active does not write COOKIE_SECURE"; fi

section "declining self-registration writes no SELF_REG line"
# p6_credentials for a team profile: secret=auto (1), password=auto (1),
# self-registration declined (n). PROFILE=team skips the email-verification
# prompt, so exactly three answers are consumed.
CFG=()
: > "$CONFIG_FILE"
CFG[PROFILE]="team"
printf '%s\n' "1" "1" "n" | p6_credentials >/dev/null 2>&1
if cfg_has SELF_REG; then bad "declining self-registration must not write SELF_REG"; else ok "declining self-registration writes no SELF_REG line"; fi

finish
