#!/usr/bin/env bash
# End-to-end: drive the whole wizard through its plain-text fallback with
# scripted answers, then inspect the config it produced and the Caddyfile the
# deploy scripts would render from it.
set -uo pipefail

# shellcheck source=scripts/tests/harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

TMPDIRS=()
cleanup() { [ ${#TMPDIRS[@]} -gt 0 ] && rm -rf "${TMPDIRS[@]}"; }
trap cleanup EXIT

run_wizard_with() {
    local answers="$1"
    export COLLECTED_DIR; COLLECTED_DIR="$(mktemp -d)"; TMPDIRS+=("$COLLECTED_DIR")
    printf '%s' "$answers" | bash -c '
        source '"$REPO"'/scripts/wizard.sh
        GUMMED=false
        detect_os() { :; }
        require_gum() { GUMMED=false; }
        clear() { :; }
        check_docker() { DOCKER_OK=true; }
        has_cmd() { case "$1" in docker) return 1 ;; *) command -v "$1" >/dev/null 2>&1 ;; esac; }
        check_firewall() { :; }
        run_wizard
    ' >/dev/null 2>&1
    cat "$COLLECTED_DIR/config.env"
}

cfg_get() { grep "^$1=" <<<"$2" | tail -1 | cut -d= -f2-; }

section "Scenario A: nginx + TLS none (the broken-login case)"
# p1 Enter | p2 (docker unavailable -> bare, no prompt) | p3 proxy=2 nginx,
# tls=3 none | p4 domain/host/port | p5 profile=1 team | p6 secret=1, pw=1,
# self-reg=n | p7 all no + git identity | p8 paths | p9 confirm
A="$(run_wizard_with '
2
3

0.0.0.0
8000
1
1
1
n
n
n

reqmesh
reqmesh@localhost
n
n
/opt/reqmesh
/opt/reqmesh/data/projects
reqmesh
reqmesh
y
')"
check "PROXY"         "$(cfg_get PROXY "$A")"         "nginx"
check "TLS"           "$(cfg_get TLS "$A")"           "none"
# nginx owns port 80, so no port suffix — but the scheme must follow TLS=none.
# This is the case the old code got wrong, emitting https:// for an HTTP site.
base_a="$(cfg_get BASE_URL "$A")"
case "$base_a" in
    http://*)  ok "BASE_URL uses http for a TLS-less proxy ($base_a)" ;;
    https://*) bad "BASE_URL claims https on a plain-HTTP deployment ($base_a)" ;;
    *)         bad "BASE_URL malformed: [$base_a]" ;;
esac
case "$base_a" in *:8000) bad "BASE_URL carries the app port past a proxy" ;;
                  *) ok "BASE_URL omits the app port (nginx listens on 80)" ;; esac
check "COOKIE_SECURE off for plain HTTP" "$(cfg_get COOKIE_SECURE "$A")" "false"
if grep -qP '\x1b\[' <<<"$A"; then bad "config contains ANSI escapes from prompts"; else ok "config is free of prompt text"; fi
if grep -qE '^[A-Z_]+=$|^[A-Z_]+=[^ ]*$' <<<"$(cfg_get DOMAIN "$A")x"; then :; fi
check "DOMAIN captured cleanly" "$(cfg_get DOMAIN "$A")" ""

section "Scenario B: caddy + internal TLS, no domain (the LAN case)"
B="$(run_wizard_with '
1
2

0.0.0.0
8000
1
1
1
n
n
n

reqmesh
reqmesh@localhost
n
n
/opt/reqmesh
/opt/reqmesh/data/projects
reqmesh
reqmesh
y
')"
check "PROXY"  "$(cfg_get PROXY "$B")"  "caddy"
check "TLS"    "$(cfg_get TLS "$B")"    "internal"
lan="$(cfg_get LAN_IP "$B")"
check "BASE_URL is https on the LAN IP" "$(cfg_get BASE_URL "$B")" "https://$lan"
check "COOKIE_SECURE on for TLS" "$(cfg_get COOKIE_SECURE "$B")" "true"
if [[ "$lan" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then ok "LAN_IP is an address ($lan)"; else bad "LAN_IP bogus: [$lan]"; fi

section "the Caddyfile this config actually produces"
export COLLECTED_DIR; COLLECTED_DIR="$(mktemp -d)"; TMPDIRS+=("$COLLECTED_DIR")
printf '%s' "$B" > "$COLLECTED_DIR/config.env"
# shellcheck disable=SC1090
source "$REPO/scripts/lib.sh"
load_cfg
caddy="$(render_caddyfile reqmesh:8000)"
o="$(grep -o '{' <<<"$caddy" | wc -l)"; c="$(grep -o '}' <<<"$caddy" | wc -l)"
check "braces balanced" "$o" "$c"
grep -q '%_' <<<"$caddy" && bad "unsubstituted placeholder" || ok "no placeholders left"
# This used to assert `^:443 {` on the grounds that it "answers on the LAN IP".
# It answers there at the TCP level and cannot complete a TLS handshake: an
# unnamed site gives the internal CA nothing to sign. Verified on a real host —
# https://<ip> returned "tlsv1 alert internal error" until the site was named.
grep -q '^:443 {' <<<"$caddy" && bad "unnamed :443 site cannot serve TLS" \
    || ok "no unnamed :443 site"
grep -q 'https://localhost' <<<"$caddy" && ok "serves a named site" \
    || bad "no named site to issue a certificate for"
echo
echo "  --- rendered Caddyfile ---"
sed 's/^/  | /' <<<"$caddy"

finish
