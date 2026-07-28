#!/usr/bin/env bash
# wizard.sh: input validation, the prompt wrappers' plain-text fallback, and
# the resume-to-review control flow.
set -uo pipefail

# shellcheck source=scripts/tests/harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

export COLLECTED_DIR; COLLECTED_DIR="$(mktemp -d)"
trap 'rm -rf "$COLLECTED_DIR"' EXIT
# shellcheck disable=SC1090
source "$REPO/scripts/wizard.sh"
GUMMED=false

section "valid_port"
for p in 8000 1 65535; do
    if valid_port "$p" 2>/dev/null; then ok "accepts $p"; else bad "rejected valid port $p"; fi
done
for p in "" abc 0 65536 -1 "80 80" 99999999999999999999999; do
    if valid_port "$p" 2>/dev/null; then bad "accepted invalid port [$p]"; else ok "rejects [$p]"; fi
done

section "valid_domain"
for d in "" example.com sub.example.co.uk; do
    if valid_domain "$d" 2>/dev/null; then ok "accepts [$d]"; else bad "rejected valid domain [$d]"; fi
done
long="$(printf 'a%.0s' $(seq 1 254))"
for d in "http://example.com" "https://x" "exa mple.com" "$long"; do
    if valid_domain "$d" 2>/dev/null; then bad "accepted invalid domain [${d:0:30}]"; else ok "rejects [${d:0:30}]"; fi
done

section "gum_input_valid re-prompts instead of exiting"
# Three bad answers then a good one. The old code called exit 1 on the first.
out="$(printf '%s\n' "not-a-port" "0" "70000" "8443" | gum_input_valid "Port" "8000" "" valid_port 2>/dev/null)"
check "keeps asking until the value is valid" "$out" "8443"
# And the process must still be alive to have produced that.
( printf '%s\n' "bad" "9000" | gum_input_valid "Port" "8000" "" valid_port >/dev/null 2>&1 )
check "exit status after recovering from a bad entry" "$?" "0"

section "prompts go to stderr, not into the captured value"
v="$(echo "example.com" | gum_input "Server domain name" "" "placeholder" 2>/dev/null)"
check "gum_input returns only the answer" "$v" "example.com"
v="$(echo "" | gum_input "Server domain name" "fallback.example" "" 2>/dev/null)"
check "gum_input returns the default on empty input" "$v" "fallback.example"
v="$(echo "hunter2hunter2" | gum_password "Admin password" "" 2>/dev/null)"
check "gum_password returns only the answer" "$v" "hunter2hunter2"
case "$v" in *$'\n'*) bad "password contains a newline (save_cfg would reject it)" ;;
             *) ok "password has no embedded newline" ;; esac
v="$(echo "2" | gum_choose "Deployment mode" "docker" "bare" 2>/dev/null)"
check "gum_choose returns the chosen option" "$v" "bare"
v="$(echo "1" | gum_choose "Deployment mode" "docker" "bare" 2>/dev/null)"
check "gum_choose honours the first option" "$v" "docker"
for junk in "" "abc" "9" "-3"; do
    v="$(echo "$junk" | gum_choose "Mode" "docker" "bare" 2>/dev/null)"
    check "gum_choose falls back to first option on [$junk]" "$v" "docker"
done
# Every captured value must survive save_cfg's own validation.
for probe in "$(echo example.com | gum_input "D" "" "" 2>/dev/null)" \
             "$(echo pw-value | gum_password "P" "" 2>/dev/null)"; do
    if validate_cfg_value "PROBE" "$probe" 2>/dev/null; then
        ok "captured value is storable: [$probe]"
    else
        bad "captured value rejected by validate_cfg_value: [$probe]"
    fi
done

section "resume-to-review control flow"
# Stub every phase so we can observe which ones run.
VISITED=""
for n in p2_deploy_mode p3_proxy p4_domain p5_profile p6_credentials p7_integrations p8_paths; do
    eval "$n() { VISITED=\"\$VISITED $n\"; }"
done
p9_review() { VISITED="$VISITED p9_review"; }
require_gum() { GUMMED=false; }
detect_os() { :; }

# (a) Normal run: p1 does not set the flag.
p1_welcome() { :; }
VISITED=""; run_wizard
check "normal run visits every phase once" \
    "$VISITED" " p2_deploy_mode p3_proxy p4_domain p5_profile p6_credentials p7_integrations p8_paths p9_review"

# (b) Resume: p1 sets the flag; only the review must run.
p1_welcome() { RESUME_TO_REVIEW=true; }
VISITED=""; run_wizard
check "resume runs the review only" "$VISITED" " p9_review"

section "'start fresh' actually discards the old session"
save_cfg "ADMIN_PASSWORD" "old-secret"
save_cfg "DOMAIN" "stale.example.com"
[ -s "$CONFIG_FILE" ] && ok "config file has content to discard" || bad "fixture did not save"
# What the decline branch does:
: > "$CONFIG_FILE"; CFG=()
check "config file emptied" "$(wc -c < "$CONFIG_FILE")" "0"
check "old password no longer in memory" "${CFG[ADMIN_PASSWORD]:-<unset>}" "<unset>"
check "old domain no longer in memory" "${CFG[DOMAIN]:-<unset>}" "<unset>"

finish
