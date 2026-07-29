#!/usr/bin/env bash
# Regressions from the first real end-to-end install on a clean Ubuntu 24.04 box.
#
# Every case here corresponds to a defect that made a `--non-interactive` Docker
# deployment fail on that machine. The existing suites stub apt/docker/systemctl
# and so never exercised these paths: the failures were all in the seam between
# the installer and a real host — an unbound variable under `curl | bash`, writes
# to a root-owned directory, and a health check aimed at an address the container
# does not bind.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ══════════════════════════════════════════════════════════════════════════════
section "install.sh under \`curl | bash\` (no BASH_SOURCE)"
# ══════════════════════════════════════════════════════════════════════════════
# The documented install is `curl … | bash`, where BASH_SOURCE[0] is unbound.
# Under `set -u` that printed "BASH_SOURCE[0]: unbound variable" as the very
# first line of output, before the installer had said anything at all.

# Take just the prologue: the full script would try to deploy.
sed -n '1,/^# Standalone mode/p' "$REPO/scripts/install.sh" > "$TMP/prologue.sh"
echo 'echo "SCRIPT_DIR=[$SCRIPT_DIR]"' >> "$TMP/prologue.sh"

piped_err="$(cd "$TMP" && bash < "$TMP/prologue.sh" 2>&1 >/dev/null)"
check "piped: no unbound-variable error" \
      "$(printf '%s' "$piped_err" | grep -c 'unbound variable')" "0"

piped_out="$(cd "$TMP" && bash < "$TMP/prologue.sh" 2>/dev/null)"
check "piped: SCRIPT_DIR falls back to \$PWD" \
      "$piped_out" "SCRIPT_DIR=[$TMP]"

# The normal path must keep working: run as a file, SCRIPT_DIR is the file's dir.
file_out="$(bash "$TMP/prologue.sh" 2>/dev/null)"
check "as a file: SCRIPT_DIR is the script's directory" "$file_out" "SCRIPT_DIR=[$TMP]"

# ══════════════════════════════════════════════════════════════════════════════
section "write_root_file / ensure_dir"
# ══════════════════════════════════════════════════════════════════════════════
declare -A CFG=()
INSTALL_DIR="$TMP/opt"
# shellcheck disable=SC1091
source "$REPO/scripts/lib.sh" >/dev/null 2>&1
# lib.sh sets -e for the installer's benefit. Sourcing it here would make the
# first missing function abort the run, hiding every later section — so a tree
# lacking one helper reports one failure rather than a truncated log.
set +e

ensure_dir "$TMP/opt/nested/deep"
check "ensure_dir creates nested directories" "$([ -d "$TMP/opt/nested/deep" ] && echo yes)" "yes"
ensure_dir "$TMP/opt/nested/deep"
check "ensure_dir on an existing dir succeeds" "$?" "0"

# The bug this guards: `tee f || sudo tee f` drains stdin in the first tee, so
# the fallback writes an empty file. Content must survive whichever writer runs.
printf 'line one\nline two\n' | write_root_file "$TMP/opt/plain.txt"
check "write_root_file writes all content" "$(wc -l < "$TMP/opt/plain.txt")" "2"
check "write_root_file content is exact" "$(head -1 "$TMP/opt/plain.txt")" "line one"

printf 'secret\n' | write_root_file "$TMP/opt/secret.env" 600
check "write_root_file honours the mode" "$(stat -c '%a' "$TMP/opt/secret.env")" "600"
check "mode-restricted write keeps content" "$(cat "$TMP/opt/secret.env")" "secret"

# A heredoc is how generate_env calls it.
write_root_file "$TMP/opt/here.env" 600 <<'HD'
RT_PROFILE=team
RT_SECRET=abc
HD
check "heredoc write lands both lines" "$(wc -l < "$TMP/opt/here.env")" "2"

# Rewriting must not widen the mode.
printf 'again\n' | write_root_file "$TMP/opt/secret.env" 600
check "rewrite keeps mode 0600" "$(stat -c '%a' "$TMP/opt/secret.env")" "600"

# ══════════════════════════════════════════════════════════════════════════════
section "effective_bind"
# ══════════════════════════════════════════════════════════════════════════════
# With no proxy the app is the only listener, so binding loopback makes the
# install unreachable from anywhere — including its own health check.
CFG=([PROXY]="none"); check "no proxy binds all interfaces" "$(effective_bind)" "0.0.0.0"
CFG=([PROXY]="caddy"); check "caddy keeps the app on loopback" "$(effective_bind)" "127.0.0.1"
CFG=([PROXY]="nginx"); check "nginx keeps the app on loopback" "$(effective_bind)" "127.0.0.1"
CFG=(); check "unset proxy defaults to loopback" "$(effective_bind)" "127.0.0.1"
CFG=([PROXY]="none" [BIND]="10.0.0.5")
check "an explicit BIND overrides the derivation" "$(effective_bind)" "10.0.0.5"

# ══════════════════════════════════════════════════════════════════════════════
section "deploy-docker.sh writes are privilege-aware"
# ══════════════════════════════════════════════════════════════════════════════
# Guard against a new unelevated write reintroducing the /opt permission failure.
raw_writes="$(grep -cE '^\s*(echo|cat|printf)[^|]*> *"\$(out|env_file)"' \
              "$REPO/scripts/deploy-docker.sh" || true)"
check "no direct redirects into INSTALL_DIR" "$raw_writes" "0"
check "compose file goes through write_root_file" \
      "$(grep -c 'write_root_file "$out"' "$REPO/scripts/deploy-docker.sh")" "3"
check "bare mkdir replaced by ensure_dir" \
      "$(grep -cE '^\s*mkdir -p "\$dir"' "$REPO/scripts/deploy-docker.sh")" "0"
check ".env is written with mode 600" \
      "$(grep -c 'write_root_file "$env_file" 600' "$REPO/scripts/deploy-docker.sh")" "1"
check "RT_BIND is written into .env" \
      "$(grep -c 'RT_BIND=\$(effective_bind)' "$REPO/scripts/deploy-docker.sh")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "health check targets the app, not BASE_URL"
# ══════════════════════════════════════════════════════════════════════════════
# BASE_URL is the user-facing address: a domain without DNS yet, an HTTPS
# endpoint mid-issuance, or a LAN IP the container never binds. Probing it made
# a healthy install report failure.
check "probes loopback" \
      "$(grep -c 'healthcheck "http://127.0.0.1:${CFG\[PORT\]:-8000}/health"' \
         "$REPO/scripts/deploy-docker.sh")" "1"
check "no longer probes BASE_URL as the gate" \
      "$(grep -c 'healthcheck "${CFG\[BASE_URL\]}/health"' "$REPO/scripts/deploy-docker.sh")" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "auth state lands on the durable volume"
# ══════════════════════════════════════════════════════════════════════════════
# The container runs as uid 999 with HOME=/app under a read-only rootfs, and the
# compose file used to cover /app/.reqmesh with a root-owned tmpfs. Login failed
# with PermissionError on users.yaml; anything that had been written would have
# been lost on restart anyway.
TMPL="$REPO/scripts/templates/docker-compose.prod.yml.tmpl"
check "RT_STATE_DIR points at the data volume" \
      "$(grep -c 'RT_STATE_DIR=/data/.reqmesh' "$TMPL")" "1"
check "no tmpfs over the auth state dir" \
      "$(grep -c '^\s*- /app/.reqmesh\s*$' "$TMPL")" "0"
check "/tmp is still tmpfs" "$(grep -c '^\s*- /tmp\s*$' "$TMPL")" "1"
check "the data volume is still mounted" "$(grep -c 'reqmesh-data:/data' "$TMPL")" "1"
check "rootfs stays read-only" "$(grep -c 'read_only: true' "$TMPL")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "cookie Secure flag follows actual TLS"
# ══════════════════════════════════════════════════════════════════════════════
# A Secure cookie is not sent over plain HTTP, so an HTTP deployment that set it
# logged the user in and then rejected every following request with 401. The
# wizard already derived this; --non-interactive hardcoded true.
cookie_secure_for() {   # <tls> <proxy>
    ( unset RT_COOKIE_SECURE
      export REQMESH_TLS="$1" REQMESH_PROXY="$2"
      _tls_active=false
      case "${REQMESH_TLS:-letsencrypt}" in
          ""|none) ;;
          *) [ "${REQMESH_PROXY:-caddy}" != "none" ] && _tls_active=true ;;
      esac
      printf '%s' "$_tls_active" )
}
check "no proxy, no TLS -> insecure cookie" "$(cookie_secure_for none none)" "false"
check "caddy + letsencrypt -> secure cookie" "$(cookie_secure_for letsencrypt caddy)" "true"
check "caddy + selfsigned -> secure cookie" "$(cookie_secure_for selfsigned caddy)" "true"
check "TLS set but no proxy -> insecure cookie" "$(cookie_secure_for letsencrypt none)" "false"
check "install.sh no longer hardcodes true" \
      "$(grep -c 'save_cfg "COOKIE_SECURE" "${RT_COOKIE_SECURE:-true}"' "$REPO/scripts/install.sh")" "0"
check "an explicit RT_COOKIE_SECURE still wins" \
      "$(grep -c 'if \[ -n "${RT_COOKIE_SECURE:-}" \]' "$REPO/scripts/install.sh")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "domainless TLS can actually complete a handshake"
# ══════════════════════════════════════════════════════════════════════════════
# `:443 { tls internal }` routes correctly and cannot serve TLS: with no site
# name there is nothing for the internal CA to sign, and a client connecting to
# a bare IP sends no SNI, so Caddy aborts with "tlsv1 alert internal error".
# Verified against Caddy 2 on the test host — https://IP went 000 -> 200.
render_domainless() {
    ( declare -A CFG=([TLS]=selfsigned [LAN_IP]="${1-}")
      TEMPLATES_DIR="$REPO/scripts/templates"
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      render_caddyfile "reqmesh:8000" )
}
out="$(render_domainless 192.168.0.163)"

check "no bare :443 site" "$(printf '%s' "$out" | grep -cE '^:443 \{')" "0"
check "the LAN IP is a named site" \
      "$(printf '%s' "$out" | grep -c 'https://192.168.0.163')" "1"
check "localhost is served too" "$(printf '%s' "$out" | grep -c 'https://localhost')" "1"
check "default_sni is set for SNI-less clients" \
      "$(printf '%s' "$out" | grep -c 'default_sni 192.168.0.163')" "1"
check "global block is the first line" \
      "$(printf '%s' "$out" | head -1)" "{"
check "global block is closed before the comments" \
      "$(printf '%s' "$out" | sed -n '3p')" "}"
check "blank line separates the block from the body" \
      "$(printf '%s' "$out" | sed -n '4p')" ""
check "http still redirects" "$(printf '%s' "$out" | grep -c 'redir https://{host}{uri} permanent')" "1"
check "tls internal retained" "$(printf '%s' "$out" | grep -c 'tls internal')" "1"

# With no LAN IP there is no name to pin, and default_sni must not be emitted
# with an empty value — Caddy rejects that outright.
out_nolan="$(render_domainless "")"
check "no default_sni without a LAN IP" "$(printf '%s' "$out_nolan" | grep -c 'default_sni')" "0"
check "still serves localhost" "$(printf '%s' "$out_nolan" | grep -c 'https://localhost')" "1"
check "no empty global block" "$(printf '%s' "$out_nolan" | head -1)" "### reqmesh Caddy reverse proxy — generated by install wizard"

# A real domain must be untouched by all of this: Let's Encrypt needs the plain
# name, no default_sni, and no localhost aliases.
out_domain="$( declare -A CFG=([TLS]=letsencrypt [DOMAIN]=reqs.example.com)
               TEMPLATES_DIR="$REPO/scripts/templates"
               source "$REPO/scripts/lib.sh" >/dev/null 2>&1
               render_caddyfile "reqmesh:8000" )"
check "domain site is the bare name" "$(printf '%s' "$out_domain" | grep -c '^reqs.example.com {')" "1"
check "no default_sni for a domain" "$(printf '%s' "$out_domain" | grep -c 'default_sni')" "0"
check "no tls directive for Let's Encrypt" "$(printf '%s' "$out_domain" | grep -c 'tls internal')" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "lib.sh sources completely under set -e"
# ══════════════════════════════════════════════════════════════════════════════
# lib.sh runs under `set -e`, so a top-level `[ -n "$x" ] && cmd` whose test is
# false returns non-zero and aborts the source on the spot — every function
# below it then silently does not exist. That is exactly what a debug-flag
# one-liner did here, and the symptom was a wizard that mis-parsed its answers.
missing=""
for fn in load_installed_env prev_env backup_file start_transcript report_failure \
          healthcheck summary_box effective_bind set_docker_cmd write_root_file \
          ensure_dir render_caddyfile write_admin_credential save_cfg load_cfg; do
    bash -c "declare -A CFG=(); source '$REPO/scripts/lib.sh' >/dev/null 2>&1
             declare -F $fn >/dev/null" || missing="$missing $fn"
done
check "every function survives the source" "$missing" ""

# The same trap, stated directly: sourcing must reach the end of the file.
bash -c "declare -A CFG=(); source '$REPO/scripts/lib.sh' >/dev/null 2>&1; echo REACHED" \
    > "$TMP/src.out" 2>/dev/null
check "source reaches the last line" "$(cat "$TMP/src.out")" "REACHED"

# And with the debug flag actually set.
REQMESH_DEBUG=1 bash -c "declare -A CFG=(); source '$REPO/scripts/lib.sh' >/dev/null 2>&1
                         declare -F healthcheck >/dev/null && echo OK" \
    > "$TMP/src2.out" 2>/dev/null
check "source survives REQMESH_DEBUG=1" "$(cat "$TMP/src2.out")" "OK"

# ══════════════════════════════════════════════════════════════════════════════
section "existing settings survive a re-install"
# ══════════════════════════════════════════════════════════════════════════════
# Re-running the installer regenerated every setting from defaults, because
# nothing read the deployed .env back. On the test host an upgrade turned
# RT_PROFILE=hardened into team, blanked the SMTP host and reset the commit
# schedule — silently, exit 0.
mkdir -p "$TMP/inst"
cat > "$TMP/inst/.env" <<'HD'
# comment line must be ignored
RT_PROFILE=hardened
RT_SECRET=keep-this-secret
RT_ADMIN_PASSWORD=original-password
RT_SMTP_HOST=smtp.example.com
RT_GIT_COMMIT_SCHEDULE=interval
REQMESH_PROXY=nginx
REQMESH_TLS=selfsigned
REQMESH_DOMAIN=reqs.example.com
HD

read_prev() {   # <key> <fallback>
    ( declare -A CFG=(); INSTALL_DIR="$TMP/inst"
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      load_installed_env "$TMP/inst" >/dev/null 2>&1
      prev_env "$1" "$2" )
}
check "profile is read back" "$(read_prev RT_PROFILE team)" "hardened"
check "signing secret is read back" "$(read_prev RT_SECRET '')" "keep-this-secret"
check "smtp host is read back" "$(read_prev RT_SMTP_HOST '')" "smtp.example.com"
check "commit schedule is read back" "$(read_prev RT_GIT_COMMIT_SCHEDULE every_change)" "interval"
check "deployment shape is recorded" "$(read_prev REQMESH_PROXY caddy)" "nginx"
check "domain is recorded" "$(read_prev REQMESH_DOMAIN '')" "reqs.example.com"
check "comments are skipped" "$(read_prev '#' 'none')" "none"
check "an unknown key falls back" "$(read_prev RT_NOT_SET 'fallback')" "fallback"

# No install at all: everything must fall back cleanly rather than error.
no_install() {
    ( declare -A CFG=(); INSTALL_DIR="$TMP/empty"
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      if load_installed_env "$TMP/empty" >/dev/null 2>&1; then echo FOUND; else echo NONE; fi )
}
check "absent install reports none" "$(no_install)" "NONE"

check "the deployment shape is written into .env" \
      "$(grep -c 'REQMESH_PROXY=${CFG\[PROXY\]' "$REPO/scripts/deploy-docker.sh")" "1"
check "install.sh prefers the existing profile" \
      "$(grep -c 'save_cfg "PROFILE" "${RT_PROFILE:-$(prev_env RT_PROFILE' "$REPO/scripts/install.sh")" "1"
check "install.sh no longer always mints a secret" \
      "$(grep -c 'save_cfg "RT_SECRET" "${RT_SECRET:-$(rand_secret 32)}"' "$REPO/scripts/install.sh")" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "the wizard does not fake a resumable session"
# ══════════════════════════════════════════════════════════════════════════════
# p1_welcome offers to resume when CONFIG_FILE is non-empty. Writing anything to
# it before that point made every run look resumable, so the wizard asked an
# extra question and every scripted answer afterwards landed one prompt early.
# Comments are stripped first: the explanation of this very bug mentions
# save_cfg, and matching prose instead of code made the check fail on itself.
check "no save_cfg before p1_welcome in run_wizard" \
      "$(sed -n '/^run_wizard()/,/p1_welcome$/p' "$REPO/scripts/wizard.sh" \
         | grep -v '^[[:space:]]*#' | grep -c 'save_cfg')" "0"
check "the flag is saved after p1_welcome" \
      "$(grep -c 'save_cfg "EXISTING_INSTALL" "\$_had_install"' "$REPO/scripts/wizard.sh")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "no invented password on an upgrade"
# ══════════════════════════════════════════════════════════════════════════════
# The app seeds an admin only when users.yaml is absent, so a password generated
# for an existing install simply does not work — verified on the host, where the
# reported credential returned 401 and the original still returned 200.
cred_for() {   # <existing_install>
    ( declare -A CFG=([INSTALL_DIR]="$TMP/cred" [ADMIN_PASSWORD]="pw" [EXISTING_INSTALL]="$1")
      INSTALL_DIR="$TMP/cred"
      mkdir -p "$TMP/cred"
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      write_admin_credential )
}
check "fresh install writes a credential file" "$(cred_for false)" "$TMP/cred/.initial-admin"
check "fresh install file exists" "$([ -f "$TMP/cred/.initial-admin" ] && echo yes)" "yes"
rm -f "$TMP/cred/.initial-admin"
check "upgrade writes no credential file" "$(cred_for true)" ""
check "upgrade leaves no stale file" "$([ -f "$TMP/cred/.initial-admin" ] && echo yes || echo no)" "no"

# ══════════════════════════════════════════════════════════════════════════════
section "backups are actually taken"
# ══════════════════════════════════════════════════════════════════════════════
# The Docker path announced "existing files will be backed up" and then ran an
# unprivileged cp into a root-owned directory with the error discarded, so it
# reliably backed nothing up.
mkdir -p "$TMP/bk"; printf 'original\n' > "$TMP/bk/.env"
dest="$( declare -A CFG=(); source "$REPO/scripts/lib.sh" >/dev/null 2>&1
         backup_file "$TMP/bk/.env" 1234 )"
check "backup_file returns the destination" "$dest" "$TMP/bk/.env.bak.1234"
check "the backup exists" "$([ -f "$TMP/bk/.env.bak.1234" ] && echo yes)" "yes"
check "the backup has the original content" "$(cat "$TMP/bk/.env.bak.1234" 2>/dev/null)" "original"
missing_ok="$( declare -A CFG=(); source "$REPO/scripts/lib.sh" >/dev/null 2>&1
               backup_file "$TMP/bk/nope" 1234 && echo rc0 )"
check "a missing file is not an error" "$missing_ok" "rc0"
check "deploy-docker no longer swallows the failure" \
      "$(grep -c 'cp "\$f" "\${f}.bak' "$REPO/scripts/deploy-docker.sh")" "0"
check "both deploy scripts report the backup" \
      "$(grep -ch 'Backed up \$f' "$REPO/scripts/deploy-docker.sh" "$REPO/scripts/deploy-bare.sh" | paste -sd+ | bc)" "2"

# ══════════════════════════════════════════════════════════════════════════════
section "transcript"
# ══════════════════════════════════════════════════════════════════════════════
# All output went to the terminal and nowhere else, so a `curl | bash` failure
# left nothing to send anyone once the scrollback was gone.
log="$TMP/transcript.log"
( declare -A CFG=(); REQMESH_LOG="$log"
  source "$REPO/scripts/lib.sh" >/dev/null 2>&1
  start_transcript
  echo "hello from the installer" ) >/dev/null 2>&1
check "the transcript is created" "$([ -f "$log" ] && echo yes)" "yes"
check "it is mode 0600 (it can contain secrets)" "$(stat -c '%a' "$log" 2>/dev/null)" "600"
check "it captures output" "$(grep -c 'hello from the installer' "$log" 2>/dev/null)" "1"

log2="$TMP/nolog.log"
( declare -A CFG=(); REQMESH_LOG="$log2" REQMESH_NO_LOG=1
  source "$REPO/scripts/lib.sh" >/dev/null 2>&1
  start_transcript ) >/dev/null 2>&1
check "--no-log suppresses it" "$([ -f "$log2" ] && echo yes || echo no)" "no"

check "install.sh accepts --debug" "$(grep -c '\-\-debug|--verbose' "$REPO/scripts/install.sh")" "1"
check "install.sh accepts --no-log" "$(grep -c '\-\-no-log)' "$REPO/scripts/install.sh")" "1"
check "failure reports the transcript path" \
      "$(grep -c 'Full transcript: \$REQMESH_LOG_FILE' "$REPO/scripts/lib.sh")" "1"
check "the failure trap is installed" \
      "$(grep -c "trap 'report_failure \$?' EXIT" "$REPO/scripts/install.sh")" "2"

# ══════════════════════════════════════════════════════════════════════════════
section "health-check failure is diagnosable"
# ══════════════════════════════════════════════════════════════════════════════
# The old message was "timed out, check the logs" plus a command that is itself
# permission-denied for the operator — while the container was healthy and the
# probe address was simply wrong.
check "it prints container state" \
      "$(grep -c 'Container state:' "$REPO/scripts/lib.sh")" "1"
check "it prints a log tail" "$(grep -c 'Last 20 log lines:' "$REPO/scripts/lib.sh")" "2"
check "the suggested command carries the sudo prefix" \
      "$(grep -c 'local dc="\${DOCKER\[\*\]:-docker} compose' "$REPO/scripts/lib.sh")" "1"
check "it distinguishes 'healthy but wrong address'" \
      "$(grep -c 'the app is running and this address is wrong' "$REPO/scripts/lib.sh")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "switching between HTTP and HTTPS"
# ══════════════════════════════════════════════════════════════════════════════
# Turning TLS on or off changes the correct base URL: the proxy takes 80/443 and
# the app loses its published port, or the reverse. Carrying the old value over
# with the other settings left an HTTPS deployment advertising a dead
# http://host:8000 — and the installer's own post-deploy check then failed
# against the URL it had just invented.
base_for() {   # <proxy> <tls> [domain]
    ( declare -A CFG=([PROXY]="$1" [TLS]="$2" [PORT]=8000 [LAN_IP]=10.1.1.5 [DOMAIN]="${3-}")
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      derive_base_url )
}
check "no proxy keeps the app port" "$(base_for none none)" "http://10.1.1.5:8000"
check "caddy + TLS drops the port"  "$(base_for caddy selfsigned)" "https://10.1.1.5"
check "a domain wins over the LAN IP" \
      "$(base_for caddy letsencrypt reqs.example.com)" "https://reqs.example.com"
# A proxy that terminates plain HTTP must not advertise https.
check "proxy without TLS stays http" "$(base_for nginx none)" "http://10.1.1.5"

fits() {   # <proxy> <tls> <url>
    ( declare -A CFG=([PROXY]="$1" [TLS]="$2" [PORT]=8000 [LAN_IP]=10.1.1.5)
      source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      base_url_fits_shape "$3" && echo keep || echo rederive )
}
check "http URL is rejected once TLS is on"  "$(fits caddy selfsigned http://10.1.1.5:8000)" "rederive"
check "the app port is rejected behind a proxy" "$(fits caddy selfsigned https://10.1.1.5:8000)" "rederive"
check "a matching https URL is kept"          "$(fits caddy selfsigned https://10.1.1.5)" "keep"
# A deliberately customised host — an external load balancer, a CNAME — must
# survive a re-run that changes nothing about the scheme.
check "a custom host survives"                "$(fits caddy selfsigned https://reqs.example.com)" "keep"
check "https URL is rejected once TLS is off" "$(fits none none https://10.1.1.5)" "rederive"
check "a matching http URL is kept"           "$(fits none none http://10.1.1.5:8000)" "keep"

check "an explicit RT_BASE_URL still wins" \
      "$(grep -c 'if \[ -n "${RT_BASE_URL:-}" \]' "$REPO/scripts/install.sh")" "1"
check "BASE_URL is not blindly carried over" \
      "$(grep -c 'save_cfg "BASE_URL" "${RT_BASE_URL:-\$(prev_env' "$REPO/scripts/install.sh")" "0"
check "LAN_IP is resolved before BASE_URL uses it" \
      "$([ "$(grep -n 'save_cfg "LAN_IP"' "$REPO/scripts/install.sh" | cut -d: -f1)" -lt \
          "$(grep -n 'save_cfg "BASE_URL" "\$RT_BASE_URL"' "$REPO/scripts/install.sh" | cut -d: -f1)" ] \
        && echo yes)" "yes"
check "LAN_IP is set exactly once" \
      "$(grep -c 'save_cfg "LAN_IP"' "$REPO/scripts/install.sh")" "1"

# Disabling the proxy rewrites the compose file without it; without
# --remove-orphans the old container kept running, kept holding 80/443, and kept
# serving HTTPS from a Caddyfile the installer no longer manages.
check "up -d removes orphaned services" \
      "$(grep -c 'up -d --remove-orphans' "$REPO/scripts/deploy-docker.sh")" "1"
check "the build path removes them too" \
      "$(grep -c 'up -d --build --remove-orphans' "$REPO/scripts/deploy-docker.sh")" "1"
check "no bare 'up -d' remains" \
      "$(grep -cE 'compose -f "\$COMPOSE_FILE" up -d$' "$REPO/scripts/deploy-docker.sh")" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "nginx works at all in Docker mode"
# ══════════════════════════════════════════════════════════════════════════════
# nginx had never worked in a container. Compose rejected the whole project with
# "service nginx refers to undefined volume nginx-certs" — the volume was
# referenced but never declared — so the deploy exited 1 before starting.
TMPL="$REPO/scripts/templates/docker-compose.prod.yml.tmpl"
# Comments stripped: the note explaining this very bug names the old volume.
check "no reference to an undeclared named volume" \
      "$(cat "$REPO/scripts/deploy-docker.sh" "$TMPL" \
         | grep -v '^[[:space:]]*#' | grep -c 'nginx-certs')" "0"
check "certs reach nginx via a bind mount" \
      "$(grep -c './certs:/etc/nginx/certs:ro' "$REPO/scripts/deploy-docker.sh")" "1"

# The template carries 127.0.0.1 for the bare-metal path, where the app is on
# the host. In a container that is nginx pointing at itself — a guaranteed 502.
NTMPL="$REPO/scripts/templates/nginx.conf.tmpl"
check "the upstream is templated, not hardcoded" \
      "$(grep -c '%_NGINX_UPSTREAM_%' "$NTMPL")" "1"
check "no hardcoded loopback upstream remains" \
      "$(grep -c 'server 127.0.0.1:\${PORT}' "$NTMPL")" "0"
check "docker resolves it to the service name" \
      "$(grep -c '%_NGINX_UPSTREAM_%/reqmesh:8000' "$REPO/scripts/deploy-docker.sh")" "1"
check "bare metal still uses loopback" \
      "$(grep -c 's/%_NGINX_UPSTREAM_%/127.0.0.1:\$port/g' "$REPO/scripts/deploy-bare.sh")" "1"

# ssl_certificate pointed at $INSTALL_DIR/certs — a *host* path the container
# cannot see — and nothing ever created the files it named.
check "cert paths are container paths" \
      "$(grep -c 'ssl_certificate     /etc/nginx/certs/server.crt' "$REPO/scripts/deploy-docker.sh")" "2"
check "no host cert path leaks into the config" \
      "$(grep -c 'ssl_certificate     \$certdir' "$REPO/scripts/deploy-docker.sh")" "0"

# ══════════════════════════════════════════════════════════════════════════════
section "self-signed certificate generation"
# ══════════════════════════════════════════════════════════════════════════════
# Caddy mints its own; nginx does not, and nothing in the installer ever created
# one, so TLS=selfsigned named files that had never existed.
if command -v openssl >/dev/null 2>&1; then
    certdir="$TMP/certs"
    ( declare -A CFG=(); source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      ensure_selfsigned_cert "$certdir" 10.9.8.7 ) >/dev/null 2>&1
    check "certificate created" "$([ -f "$certdir/server.crt" ] && echo yes)" "yes"
    check "key created" "$([ -f "$certdir/server.key" ] && echo yes)" "yes"
    check "the private key is not world-readable" "$(stat -c '%a' "$certdir/server.key" 2>/dev/null)" "600"
    # A certificate with only a CN is rejected by every current browser, which
    # would turn a startup failure into an unfixable warning page.
    sans="$(openssl x509 -in "$certdir/server.crt" -noout -ext subjectAltName 2>/dev/null)"
    check "the address is a SAN, not just a CN" \
          "$(printf '%s' "$sans" | grep -c 'IP Address:10.9.8.7')" "1"
    check "localhost is covered too" "$(printf '%s' "$sans" | grep -c 'DNS:localhost')" "1"
    # A hostname must get a DNS SAN rather than an IP one.
    ( declare -A CFG=(); source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      ensure_selfsigned_cert "$TMP/certs2" reqs.example.com ) >/dev/null 2>&1
    check "a hostname gets a DNS SAN" \
          "$(openssl x509 -in "$TMP/certs2/server.crt" -noout -ext subjectAltName 2>/dev/null \
             | grep -c 'DNS:reqs.example.com')" "1"
    # Re-running must not churn the certificate — that would break every client
    # that had accepted it.
    before="$(cat "$certdir/server.crt")"
    ( declare -A CFG=(); source "$REPO/scripts/lib.sh" >/dev/null 2>&1
      ensure_selfsigned_cert "$certdir" 10.9.8.7 ) >/dev/null 2>&1
    check "an existing certificate is reused" "$(cat "$certdir/server.crt")" "$before"
else
    ok "openssl absent — certificate generation not exercised"
fi

# ══════════════════════════════════════════════════════════════════════════════
section "a reconfigured proxy actually reloads"
# ══════════════════════════════════════════════════════════════════════════════
# The proxy config is a bind-mounted file, and `up -d` only recreates a
# container when its *service definition* changes. Rewriting Caddyfile or
# nginx.conf does not, so a proxy that was already running kept serving its
# startup config: switching nginx to HTTPS regenerated the config and the
# certificate, reported success, and left 443 closed.
check "the proxy is restarted after deploy" \
      "$(grep -c 'compose -f "\$COMPOSE_FILE" restart "\$proxy_svc"' "$REPO/scripts/deploy-docker.sh")" "1"
check "it is skipped when there is no proxy" \
      "$(grep -c 'if \[ "\$proxy_svc" != "none" \]' "$REPO/scripts/deploy-docker.sh")" "1"
check "a failed restart warns rather than passing silently" \
      "$(grep -c 'may still be serving the previous configuration' "$REPO/scripts/deploy-docker.sh")" "1"

# ══════════════════════════════════════════════════════════════════════════════
section "release staging cannot drop a versioned file"
# ══════════════════════════════════════════════════════════════════════════════
# v0.1.2 shipped an install.sh still pinned to v0.1.1 because release.sh kept its
# own hardcoded file list that had gone stale.
files="$(/usr/bin/python3 "$REPO/scripts/set_version.py" --files)"
check "--files includes install.sh" "$(printf '%s' "$files" | grep -c 'scripts/install.sh')" "1"
check "--files includes VERSION" "$(printf '%s' "$files" | grep -cx 'VERSION')" "1"
check "release.sh has no hardcoded list" \
      "$(grep -c 'VERSION backend/app/core/_version.py frontend/package.json' "$REPO/scripts/release.sh")" "0"
check "release.sh stages the derived list" \
      "$(grep -c 'git add "\${VERSIONED_FILES\[@\]}"' "$REPO/scripts/release.sh")" "1"

# The pin must match the version being released.
ver="$(cat "$REPO/VERSION")"
pin="$(grep -o 'REQMESH_REF:-v[0-9.]*' "$REPO/scripts/install.sh" | cut -d- -f2)"
check "install.sh ref pin matches VERSION" "$pin" "v$ver"

finish
