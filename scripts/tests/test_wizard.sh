#!/usr/bin/env bash
# lib.sh helpers: Caddyfile rendering, the summary box, credential writing,
# port detection and LAN-address detection.
set -uo pipefail

# shellcheck source=scripts/tests/harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

export COLLECTED_DIR
COLLECTED_DIR="$(mktemp -d)"
trap 'rm -rf "$COLLECTED_DIR"' EXIT
# shellcheck disable=SC1090
source "$REPO/scripts/lib.sh"

section "render_caddyfile"
# Structural validation: brace balance, no leftover placeholders, and a
# non-empty site address on the first directive line.
validate_caddy() {
    local text="$1" label="$2"
    local opens closes
    opens="$(grep -o '{' <<<"$text" | wc -l)"
    closes="$(grep -o '}' <<<"$text" | wc -l)"
    check "$label: braces balanced" "$opens" "$closes"
    if grep -q '%_' <<<"$text"; then bad "$label: unsubstituted placeholder"; else ok "$label: no placeholders left"; fi
    if grep -qE '^\s*\{' <<<"$text"; then bad "$label: empty site address"; else ok "$label: site address present"; fi
    # every site block header must have a non-space token before '{'
    if grep -E '\{\s*$' <<<"$text" | grep -qE '^\s*\{\s*$'; then
        bad "$label: bare opening brace line"
    else
        ok "$label: no bare opening brace"
    fi
}

CFG[DOMAIN]="example.com"; CFG[TLS]="letsencrypt"
out="$(render_caddyfile reqmesh:8000)"
validate_caddy "$out" "domain+letsencrypt"
grep -q '^example.com {' <<<"$out" && ok "domain+letsencrypt: address is the domain" || bad "domain+letsencrypt: address wrong"
grep -q 'tls internal' <<<"$out" && bad "domain+letsencrypt: should not force internal TLS" || ok "domain+letsencrypt: uses ACME default"

CFG[DOMAIN]="example.com"; CFG[TLS]="internal"
out="$(render_caddyfile reqmesh:8000)"
validate_caddy "$out" "domain+internal"
grep -q 'tls internal' <<<"$out" && ok "domain+internal: tls internal present" || bad "domain+internal: missing tls internal"

CFG[DOMAIN]=""; CFG[TLS]="internal"
out="$(render_caddyfile reqmesh:8000)"
validate_caddy "$out" "no-domain (the LAN case)"
# Previously asserted a bare `^:443 {`. That site routes but cannot serve TLS —
# nothing is named, so the internal CA has no certificate to issue and the
# handshake fails. The domainless case must name its addresses instead.
grep -q '^:443 {' <<<"$out" && bad "no-domain: unnamed :443 cannot serve TLS" \
    || ok "no-domain: no unnamed :443 site"
grep -q 'https://localhost' <<<"$out" && ok "no-domain: named site present" \
    || bad "no-domain: no named site"
grep -q 'redir https://{host}{uri} permanent' <<<"$out" && ok "no-domain: http->https redirect" || bad "no-domain: no redirect"
grep -q 'reverse_proxy reqmesh:8000' <<<"$out" && ok "no-domain: docker backend target" || bad "no-domain: backend wrong"

CFG[DOMAIN]="localserver.reqmesh.com"; CFG[TLS]="internal"
out="$(render_caddyfile 127.0.0.1:8000)"
validate_caddy "$out" "placeholder-domain (bare metal)"
grep -q 'reverse_proxy 127.0.0.1:8000' <<<"$out" && ok "bare metal: backend is localhost" || bad "bare metal: backend wrong"

section "summary_box alignment"
CFG[BASE_URL]="https://192.168.0.162"; CFG[LAN_IP]="192.168.0.162"
CFG[DOMAIN]=""; CFG[PROXY]="caddy"; CFG[TLS]="internal"
box="$(summary_box "/opt/reqmesh/.initial-admin" "Manage:  systemctl status reqmesh" "Logs:    journalctl -u reqmesh -f")"
# Strip ANSI, then confirm every line is the same width. Counted in characters,
# not bytes: the border glyphs are multibyte, so awk's length() would call a
# perfectly aligned box ragged.
box_widths() {
    sed 's/\x1b\[[0-9;]*m//g' | while IFS= read -r l; do
        printf '%s\n' "$(printf '%s' "$l" | LC_ALL=en_US.UTF-8 wc -m)"
    done | sort -u
}
widths="$(box_widths <<<"$box")"
if [ "$(wc -l <<<"$widths")" -eq 1 ]; then
    ok "every box line is $widths columns wide"
else
    bad "ragged box, widths seen: $(tr '\n' ' ' <<<"$widths")"
fi
# Under LC_ALL=C, ${#text} counts bytes — any non-ASCII in the box content
# silently shortens that line. This is the locale an installer run from CI or
# systemd actually gets.
c_box="$(LC_ALL=C summary_box "/opt/reqmesh/.initial-admin" "Manage:  systemctl status reqmesh")"
c_widths="$(box_widths <<<"$c_box")"
if [ "$(wc -l <<<"$c_widths")" -eq 1 ]; then
    ok "box stays aligned under LC_ALL=C ($c_widths columns)"
else
    bad "box is ragged under LC_ALL=C, widths seen: $(tr '\n' ' ' <<<"$c_widths")"
fi
plain="$(sed 's/\x1b\[[0-9;]*m//g' <<<"$box")"
grep -q '^╭─*╮$' <<<"$plain" && ok "top border closed" || bad "top border not closed"
grep -q '^╰─*╯$' <<<"$plain" && ok "bottom border closed" || bad "bottom border not closed"
if [ "$(grep -c '│$' <<<"$plain")" -eq "$(grep -c '^│' <<<"$plain")" ]; then
    ok "every content line closed on the right"
else
    bad "content lines left open: $(grep -c '^│' <<<"$plain") opened, $(grep -c '│$' <<<"$plain") closed"
fi
grep -q 'self-signed certificate' <<<"$plain" && ok "self-signed caveat shown for internal TLS" || bad "missing self-signed caveat"

CFG[PROXY]="nginx"; CFG[TLS]="none"
box="$(summary_box "/opt/reqmesh/.initial-admin" "x")"
grep -q 'TLS is not enabled' <<<"$box" && ok "plain-HTTP caveat shown for nginx+tls=none" || bad "missing plain-HTTP caveat"

section "write_admin_credential"
tmp_install="$(mktemp -d)"
CFG[INSTALL_DIR]="$tmp_install"
CFG[ADMIN_PASSWORD]='p@ss w0rd-with |pipe& and $dollar'
path="$(write_admin_credential)"
check "returns the credential path" "$path" "$tmp_install/.initial-admin"
check "file contains the exact password" "$(cat "$path")" "${CFG[ADMIN_PASSWORD]}"
check "file is mode 0600" "$(stat -c '%a' "$path")" "600"
[ -s "$path" ] && ok "file is non-empty" || bad "file is EMPTY (the tee-fallback bug)"

section "check_port"
# A port that is genuinely listening, found independently of check_port.
listening="$(ss -tln | awk 'NR>1{n=split($4,a,":"); print a[n]}' | sort -u | head -1)"
if [ -n "$listening" ]; then
    if check_port "$listening"; then ok "detects listening port $listening"; else bad "missed listening port $listening"; fi
fi
# A port nothing can be listening on.
if check_port 65533; then bad "false positive on unused port 65533"; else ok "unused port 65533 reported free"; fi
# Prefix collision: :80 must not match :8080.
if ss -tln | awk 'NR>1{n=split($4,a,":"); print a[n]}' | grep -qx 80; then
    echo "  (skipping prefix test: 80 is actually listening)"
else
    if check_port 80; then bad "port 80 falsely reported busy (prefix match bug)"; else ok "no prefix collision on :80"; fi
fi

section "detect_lan_ip"
ip_out="$(detect_lan_ip)"
if [[ "$ip_out" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ok "returns a dotted-quad ($ip_out)"
else
    bad "returned non-IP: [$ip_out]"
fi
# The on-link route shape that used to yield the uid.
onlink='192.168.0.1 dev enp4s0 src 192.168.0.162 uid 1000 \    cache'
parsed="$(awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}' <<<"$onlink")"
check "parses on-link route (no 'via')" "$parsed" "192.168.0.162"
viaroute='1.1.1.1 via 192.168.0.1 dev enp4s0 src 192.168.0.162 uid 1000 \    cache'
parsed="$(awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}' <<<"$viaroute")"
check "parses gateway route (with 'via')" "$parsed" "192.168.0.162"

rm -rf "$tmp_install"
finish
