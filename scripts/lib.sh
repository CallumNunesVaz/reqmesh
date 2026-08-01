#!/usr/bin/env bash
# lib.sh — shared utilities for the reqmesh install wizard
# shellcheck disable=SC2059

set -euo pipefail

# ── Global state ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/reqmesh}"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

# The collected config holds RT_SECRET, the admin password and the SMTP
# password in clear text. It previously lived at a fixed /tmp path created with
# the default umask, which is world-readable — and because the name was
# predictable, any local user could pre-create the directory and then both read
# the secrets and tamper with the config that gets rendered into systemd units
# and compose files running as root.
#
# So: a fresh mktemp directory by default, mode 0700, and if the caller pins
# COLLECTED_DIR we verify we own it and it isn't a symlink before writing
# secrets into it. Exported so the deploy scripts (run as child processes)
# inherit the same directory instead of minting their own.
if [ -n "${COLLECTED_DIR:-}" ]; then
    mkdir -p "$COLLECTED_DIR"
    if [ -L "$COLLECTED_DIR" ]; then
        printf 'FATAL: COLLECTED_DIR (%s) is a symlink; refusing to write secrets.\n' \
            "$COLLECTED_DIR" >&2
        exit 1
    fi
    if [ ! -O "$COLLECTED_DIR" ]; then
        printf 'FATAL: COLLECTED_DIR (%s) is not owned by the current user; refusing to write secrets.\n' \
            "$COLLECTED_DIR" >&2
        exit 1
    fi
else
    COLLECTED_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reqmesh-install.XXXXXXXXXX")"
fi
chmod 700 "$COLLECTED_DIR"
export COLLECTED_DIR
CONFIG_FILE="$COLLECTED_DIR/config.env"
( umask 077; : >> "$CONFIG_FILE" )

# Collected configuration (populated by wizard, consumed by deploy scripts)
declare -A CFG
export CFG

# ── ANSI helpers (decorative; Gum provides the heavy UI) ───────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { printf "${BLUE}→${NC} %s\n" "$*"; }
success() { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$*" >&2; }
error()   { printf "${RED}✗${NC} %s\n" "$*" >&2; }
header()  { printf "\n${BOLD}${CYAN}═══ %s ═══${NC}\n\n" "$*"; }

# ── Summary box ────────────────────────────────────────────────────────────────
# Both deploy scripts end with a framed summary. Drawn through these helpers so
# the right-hand border is actually closed: hand-written `printf "║ text\n"`
# lines left every row open, because the padding depends on the text length and
# no caller was computing it.
#
# Padding uses ${#text}, so box content must stay plain ASCII — colour codes and
# multi-column glyphs would count as characters but not as printed columns.
# Colour is applied via the second argument instead of being embedded, and text
# wider than BOX_WIDTH degrades to an unclosed line rather than a mangled one.
BOX_WIDTH=68

box_rule() {
    local left="$1" right="$2" line=""
    local i
    for ((i = 0; i < BOX_WIDTH + 2; i++)); do line+="─"; done
    printf "${GREEN}%s%s%s${NC}\n" "$left" "$line" "$right"
}
box_top()    { box_rule "╭" "╮"; }
box_bottom() { box_rule "╰" "╯"; }

box_line() {
    local text="${1:-}" colour="${2:-}"
    local pad=$(( BOX_WIDTH - ${#text} ))
    [ "$pad" -lt 0 ] && pad=0
    printf "${GREEN}│${NC} %b%s%b%*s ${GREEN}│${NC}\n" \
        "$colour" "$text" "${colour:+\033[0m}" "$pad" ""
}

# ── Spinner (wraps Gum if available, fallback to background job) ───────────────
spinner() {
    local msg="$1" pid="$2"
    if command -v gum &>/dev/null; then
        gum spin --spinner dot --title "$msg" -- sleep 0.1 &
        local sp=$!
        wait "$pid" 2>/dev/null || true
        kill "$sp" 2>/dev/null || true
    else
        local chars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
        while kill -0 "$pid" 2>/dev/null; do
            for ((i=0; i<${#chars}; i++)); do
                printf "\r${BLUE}%s${NC} %s" "${chars:$i:1}" "$msg"
                sleep 0.1
            done
        done
        printf "\r${GREEN}✓${NC} %s\n" "$msg"
    fi
}

# ── OS detection ───────────────────────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID:-}"
        OS_CODENAME="${VERSION_CODENAME:-}"
    elif [ "$(uname -s)" = "Darwin" ]; then
        OS_ID="macos"
        OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
    else
        OS_ID="unknown"
    fi
}

# ── Dependency checks ──────────────────────────────────────────────────────────
has_cmd() { command -v "$1" &>/dev/null; }

check_docker() {
    if has_cmd docker && docker info &>/dev/null 2>&1; then
        DOCKER_OK=true
        if docker compose version &>/dev/null 2>&1; then
            COMPOSE_CMD="docker compose"
        elif has_cmd docker-compose; then
            COMPOSE_CMD="docker-compose"
        fi
    else
        DOCKER_OK=false
    fi
}

check_systemd() {
    if [ -d /run/systemd/system ] && has_cmd systemctl; then
        SYSTEMD_OK=true
    else
        SYSTEMD_OK=false
    fi
}

install_docker() {
    if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        if [ "$OS_ID" = "ubuntu" ]; then
            sudo apt-get install -y docker-compose-plugin 2>/dev/null || true
        fi
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        COMPOSE_CMD="docker compose"
        DOCKER_OK=true
    else
        error "Automatic Docker install not supported on $OS_ID. Install manually: https://docs.docker.com/engine/install/"
        return 1
    fi
    if ! groups "$USER" 2>/dev/null | grep -qw docker; then
        warn "User '$USER' was added to the 'docker' group."
        warn "You must log out and back in (or run: newgrp docker) for this to take effect."
        warn "Until then, prefix docker commands with 'sudo'."
    fi
}

install_system_pkgs() {
    local pkgs="git curl ca-certificates"
    # weasyprint rendering deps
    pkgs="$pkgs libglib2.0-0 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core"
    case "$OS_ID" in
        ubuntu|debian)
            info "Installing system packages: $pkgs"
            sudo apt-get update -qq
            sudo apt-get install -y -qq $pkgs
            ;;
        fedora|rhel|centos)
            info "Installing system packages (DNF)..."
            sudo dnf install -y git curl ca-certificates glib2 pango harfbuzz dejavu-sans-fonts
            ;;
        *)
            warn "Unknown OS. Install these packages manually: $pkgs"
            ;;
    esac
}

install_caddy() {
    case "$OS_ID" in
        ubuntu|debian)
            info "Installing Caddy..."
            sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https 2>/dev/null || true
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
                sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
                sudo tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
            sudo apt-get update -qq
            sudo apt-get install -y -qq caddy
            ;;
        *)
            warn "Automatic Caddy install not supported on $OS_ID."
            warn "Install from: https://caddyserver.com/docs/install"
            ;;
    esac
}

install_nginx() {
    case "$OS_ID" in
        ubuntu|debian)
            info "Installing nginx..."
            sudo apt-get install -y -qq nginx
            ;;
        fedora|rhel|centos)
            sudo dnf install -y nginx
            ;;
        *)
            warn "Automatic nginx install not supported on $OS_ID."
            ;;
    esac
}

# Tectonic LaTeX engine (used for PDF report generation)
#
# Without it, reports silently drop to the weasyprint HTML->PDF fallback, which
# omits tables, badges and the table of contents. The degradation is invisible
# from the install log, so this reports what actually happened rather than
# assuming the download worked.
install_tectonic() {
    if has_cmd tectonic; then
        info "tectonic already installed: $(tectonic --version 2>&1 | head -1)"
        return 0
    fi
    info "Installing tectonic PDF engine..."
    # The upstream script drops the binary into the *current* directory, so run
    # it somewhere writable and known rather than wherever the installer was
    # invoked from — which may be read-only, or already hold a stale binary.
    local tmp
    tmp="$(mktemp -d)"
    ( cd "$tmp" && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh ) || true
    if [ -f "$tmp/tectonic" ]; then
        sudo install -m 0755 "$tmp/tectonic" /usr/local/bin/tectonic
        rm -rf "$tmp"
        success "tectonic installed to /usr/local/bin/tectonic"
    else
        rm -rf "$tmp"
        warn "tectonic download failed — PDF reports will use the weasyprint fallback,"
        warn "which omits tables, badges and the table of contents."
        warn "Install it from https://tectonic-typesetting.github.io and re-run to fix."
    fi
}

# Fetch the TeX packages a real report needs, so a user's first export does not
# have to do it inside the compile timeout. See backend/scripts/warm_tectonic.py
# for the full reasoning. Best-effort: failing here costs a slow first report,
# not a broken install — but it is reported, because a silent slow path is how
# this went unnoticed in the first place.
warm_tectonic_cache() {
    local backend_dir="$1" venv_python="$2" cache_dir="$3" run_as="${4:-}"
    has_cmd tectonic || return 0
    [ -x "$venv_python" ] || return 0

    info "Pre-fetching LaTeX packages (one-off, ~20MB)..."
    local -a runner=()
    [ -n "$run_as" ] && runner=(sudo -u "$run_as")
    if (cd "$backend_dir" && "${runner[@]}" env TECTONIC_CACHE_DIR="$cache_dir" \
            "$venv_python" scripts/warm_tectonic.py); then
        success "LaTeX packages cached in $cache_dir"
    else
        warn "Could not pre-fetch LaTeX packages — the first PDF export will be slower."
    fi
}

# ── Network & environment detection ─────────────────────────────────────────
# Return the primary non-loopback IPv4 address, or empty string if none found.
#
# `ip route get` prints two shapes depending on whether the destination is
# reached through a gateway:
#     1.1.1.1 via 192.168.0.1 dev eth0 src 192.168.0.162 uid 1000
#     1.1.1.1 dev eth0 src 192.168.0.162 uid 1000          (on-link default)
# A fixed field index only works for the first. Cloud images that configure
# `default dev eth0 scope link` (and point-to-point links such as WireGuard)
# print the second, where field 7 is the *uid* — so the installer would report
# `https://1000` as the LAN address. Scan for the `src` keyword instead.
detect_lan_ip() {
    local ip=""
    if has_cmd ip; then
        ip="$(ip -4 -o route get 1.1.1.1 2>/dev/null \
              | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
    fi
    if [ -z "$ip" ] && has_cmd hostname; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    if [ -z "$ip" ] && has_cmd ifconfig; then
        ip="$(ifconfig 2>/dev/null | awk '/inet / && !/127.0.0.1/ {print $2; exit}')"
    fi
    printf '%s' "${ip:-}"
}

# Check whether a TCP port is already in use. Returns 0 (true) if busy.
#
# Deliberately not `ss … | grep -q`: `grep -q` exits at the first match, `ss`
# then dies of SIGPIPE, and `set -o pipefail` reports the pipeline as *failed* —
# so a port that is in use is reported free. It only shows up once the listener
# list is long enough that ss is still writing when grep leaves, i.e. on busy
# servers and never on a test box. Match in awk, which reads to EOF.
check_port() {
    local port="$1"
    if has_cmd ss; then
        ss -tln 2>/dev/null | awk -v p=":$port" 'NR > 1 && index($4, p) == length($4) - length(p) + 1 { found = 1 } END { exit !found }'
    elif has_cmd lsof; then
        lsof -i ":$port" -sTCP:LISTEN >/dev/null 2>&1
    else
        return 1
    fi
}

# Print a warning if a system firewall is active and common ports are not open.
#
# `sudo -n` throughout: this runs mid-wizard, inside the Gum TUI, and a blocking
# password prompt there is invisible under the alternate screen buffer. A
# firewall we cannot inspect without credentials is simply not reported.
check_firewall() {
    local ports="${1:-80 443 8000}"
    local active=false out=""
    # Each probe captures first and matches after, for the same reason
    # check_port does: `… | grep -q` under pipefail loses the match whenever the
    # producer outruns grep, and `ufw status` on a host with real rules is long
    # enough to do exactly that.
    if has_cmd ufw; then
        out="$(sudo -n ufw status 2>/dev/null || true)"
        case "$out" in *"Status: active"*) active=true ;; esac
    fi
    if ! $active && has_cmd firewall-cmd; then
        out="$(sudo -n firewall-cmd --state 2>&1 || true)"
        case "$out" in *running*) active=true ;; esac
    fi
    if ! $active && has_cmd iptables; then
        out="$(sudo -n iptables -L INPUT -n 2>/dev/null || true)"
        case "$out" in *DROP*|*REJECT*) active=true ;; esac
    fi
    if $active; then
        warn "A firewall appears to be active on this system."
        warn "Make sure the following ports are open: $ports"
    fi
}

# Detect SELinux enforcing mode; print warning if it may interfere.
detect_selinux() {
    if has_cmd getenforce && [ "$(getenforce 2>/dev/null)" = "Enforcing" ]; then
        warn "SELinux is enforcing — it may block Docker socket access or network binds."
        warn "If services fail to start, try: sudo setenforce 0 (temporarily)"
    fi
}

# ── Config helpers ─────────────────────────────────────────────────────────────
# Generate a random secret string
rand_secret() {
    local len="${1:-32}"
    if has_cmd openssl; then
        openssl rand -hex "$len"
    else
        tr -dc 'A-Za-z0-9' < /dev/urandom | head -c $((len * 2))
    fi
}

# Render a template file by substituting %_VARIABLE_% patterns
# Usage: template input.tmpl > output
template() {
    local tmpl="$1"
    local out="$2"
    local content
    content="$(< "$tmpl")"
    # Substitute simple ${VAR} references from collected config
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        content="${content//\$\{${key}\}/$value}"
    done < "$CONFIG_FILE"
    # printf, not echo: echo mangles backslash sequences in some shells, and a
    # rendered config may legitimately contain them.
    printf '%s\n' "$content" > "$out"
}

# Render the Caddyfile to stdout for a given backend target ("reqmesh:8000" for
# Docker, "127.0.0.1:8000" for bare metal).
#
# Shared because the two deploy scripts previously rendered the same template by
# hand — deploy-docker.sh through `${var//…}` substitutions, deploy-bare.sh
# through a series of `sed -i` calls — and both got the no-domain case wrong in
# different ways: the Docker path emitted a truncated site block (a `}` in a
# `${var//pat/repl}` replacement ends the expansion early), while the bare-metal
# path left the address empty, producing a file starting with ` {`. Caddy
# rejected both, so the LAN install the wizard recommends never came up.
# Render one Caddy site block from the template: the shared body with a given
# site address and tls directive.
_caddy_site() {
    local address="$1" tls_directive="$2" backend="$3"
    local body
    body="$(< "$TEMPLATES_DIR/Caddyfile.tmpl")"
    # Strip the template's leading comments; the caller writes the header once.
    body="$(printf '%s' "$body" | sed '/^###/d')"
    body="${body//%_SITE_ADDRESS_%/$address}"
    body="${body//%_TLS_%/$tls_directive}"
    body="${body//reqmesh:8000/$backend}"
    printf '%s' "$body"
}

# The LAN addresses this box answers on, as Caddy site addresses.
_caddy_lan_addresses() {
    local addrs="https://localhost, https://127.0.0.1"
    local lan="${CFG[LAN_IP]:-}"
    [ -n "$lan" ] && addrs="https://$lan, $addrs"
    printf '%s' "$addrs"
}

render_caddyfile() {
    local backend="$1"
    local domain="${CFG[DOMAIN]:-}"
    local tls="${CFG[TLS]:-letsencrypt}"
    local lan="${CFG[LAN_IP]:-}"

    local has_domain=false
    [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ] && has_domain=true

    # A client connecting to a bare IP sends no SNI (RFC 6066 forbids IP literals
    # there), so Caddy has no name to match and aborts the handshake even holding a
    # valid certificate for that address. default_sni names the fallback.
    # Caddy requires the global options block first in the file.
    local out=""
    if [ -n "$lan" ]; then
        out="$(printf '{\n\tdefault_sni %s\n}' "$lan")"$'\n\n'
    fi
    out+="### reqmesh Caddy reverse proxy — generated by install wizard"$'\n'
    out+="### Re-run ./install.sh to reconfigure."$'\n'

    if $has_domain; then
        local domain_tls=""
        [ "$tls" = "letsencrypt" ] || domain_tls="    tls internal"
        out+="$(_caddy_site "$domain" "$domain_tls" "$backend")"$'\n'

        # The LAN block is served *as well as* the domain, not instead of it.
        # Replacing it locked the operator out of their own box: with only the
        # domain named, https://<lan-ip> matched no site and returned nothing,
        # so while DNS was wrong or a certificate was pending the deployment was
        # reachable from nowhere at all.
        out+="$(_caddy_site "$(_caddy_lan_addresses)" "    tls internal" "$backend")"$'\n'
    else
        out+="$(_caddy_site "$(_caddy_lan_addresses)" "    tls internal" "$backend")"$'\n'
    fi

    # Named sites get an automatic HTTP->HTTPS redirect from Caddy, but only for
    # the names listed. A catch-all keeps http:// working for any other address
    # this box answers on instead of refusing the connection outright.
    out+="
:80 {
    redir https://{host}{uri} permanent
}"
    printf '%s\n' "$out"
}

# Reject values that cannot be represented safely in the .env files this
# installer generates. Those are consumed by both docker compose `env_file` and
# systemd `EnvironmentFile=`, which disagree about quoting and expansion, so
# rather than try to escape for both we refuse the ambiguous characters and say
# why. A newline would silently truncate the value and inject a second setting.
validate_cfg_value() {
    local key="$1" value="$2"
    case "$value" in
        *$'\n'*|*$'\r'*)
            error "$key contains a line break — not representable in an env file."
            return 1 ;;
        *\'*|*\"*|*\\*|*\`*)
            error "$key contains a quote, backslash or backtick."
            error "These are parsed differently by docker compose and systemd; please choose a value without them."
            return 1 ;;
    esac
    return 0
}

# Save a config value for later template rendering.
#
# Rewrites through a temp file rather than `sed -i "s|^key=.*|key=$value|"`:
# with sed, a value containing '|' aborted the substitution (leaving the *old*
# value silently in place) and a '&' expanded to the matched text. Passwords
# routinely contain both.
save_cfg() {
    local key="$1" value="$2"
    validate_cfg_value "$key" "$value" || return 1
    CFG["$key"]="$value"

    local tmp="${CONFIG_FILE}.tmp.$$"
    (
        umask 077
        if [ -f "$CONFIG_FILE" ]; then
            grep -v "^${key}=" "$CONFIG_FILE" > "$tmp" || true
        else
            : > "$tmp"
        fi
        printf '%s=%s\n' "$key" "$value" >> "$tmp"
    )
    mv "$tmp" "$CONFIG_FILE"
}

load_cfg() {
    if [ -f "$CONFIG_FILE" ]; then
        while IFS='=' read -r key value; do
            [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
            CFG["$key"]="$value"
        done < "$CONFIG_FILE"
    fi
}

# ── Transcript ─────────────────────────────────────────────────────────────────
# Everything the installer said used to go to the terminal and nowhere else, so
# under the documented `curl … | bash` a failure left nothing to send anyone once
# the scrollback was gone. Six of the ten defects found on the first real
# deployment were invisible in the terminal output anyway.
#
# Started around the deploy phase rather than the whole run: teeing stdout makes
# it a pipe, and Gum drops to its plain-text fallback when stdout is not a tty.
# The wizard is questions; the deploy is where things break.
REQMESH_LOG_FILE="${REQMESH_LOG_FILE:-}"

start_transcript() {
    [ -n "${REQMESH_NO_LOG:-}" ] && return 0
    [ -n "$REQMESH_LOG_FILE" ] && return 0        # already running

    local candidate="${REQMESH_LOG:-${TMPDIR:-/tmp}/reqmesh-install-$(date +%Y%m%d-%H%M%S).log}"
    # Created 0600 before a byte is written: under --debug the transcript
    # contains RT_SECRET, the admin password and any SMTP password.
    if ! install -m 600 /dev/null "$candidate" 2>/dev/null; then
        warn "Could not create a transcript at $candidate — continuing without one."
        return 0
    fi

    REQMESH_LOG_FILE="$candidate"
    export REQMESH_LOG_FILE
    exec > >(tee -a "$REQMESH_LOG_FILE") 2>&1

    info "Transcript: $REQMESH_LOG_FILE"
    if [ -n "${REQMESH_DEBUG:-}" ]; then
        export REQMESH_DEBUG
        warn "--debug: the transcript will contain secrets. It is mode 0600 — treat it as one."
        set -x
    fi
}

# Print where to look when something failed. Wired to an EXIT trap so it covers
# `set -e` aborts, which is how most of these scripts stop.
report_failure() {
    local code="$1"
    [ "$code" -eq 0 ] && return 0
    error "Installation failed (exit $code)."
    if [ -n "${REQMESH_LOG_FILE:-}" ]; then
        error "Full transcript: $REQMESH_LOG_FILE"
        error "The last 20 lines are usually enough to see what went wrong:"
        error "  tail -20 $REQMESH_LOG_FILE"
    else
        error "Re-run with --debug for a full trace, or without --no-log for a transcript."
    fi
}

# Child scripts (deploy-docker.sh, deploy-bare.sh) inherit the flag, not the
# shell option, so honour it on source.
#
# Written as an `if`, not `[ -n "$x" ] && set -x`: this file runs under `set -e`,
# and a bare AND-list whose left side is false returns non-zero at top level,
# which aborts the `source` on the spot. Every function defined below this point
# then silently does not exist.
if [ -n "${REQMESH_DEBUG:-}" ]; then
    set -x
fi

# ── Reading back an existing installation ──────────────────────────────────────
# Re-running the installer used to regenerate every setting from its defaults,
# because nothing ever read the deployed .env — load_cfg only reads the wizard's
# own scratch file. Upgrading a box therefore reset RT_PROFILE from `hardened`
# to `team`, blanked the SMTP host, reverted the commit schedule and minted a
# fresh RT_SECRET (logging every session out), silently and with exit code 0.
#
# PREV_ENV holds the settings of the install already on this machine, so the
# defaults below can be "what this box is already doing" instead of "factory".
declare -A PREV_ENV
PREV_FOUND=false

load_installed_env() {
    local dir="${1:-${CFG[INSTALL_DIR]:-$INSTALL_DIR}}"
    local env_file="$dir/.env"
    local content=""

    # The file is 0600 and usually root-owned, so a plain read fails for the
    # unprivileged operator who is running the installer.
    if [ -r "$env_file" ]; then
        content="$(cat "$env_file" 2>/dev/null)" || return 1
    elif sudo test -r "$env_file" 2>/dev/null; then
        content="$(sudo cat "$env_file" 2>/dev/null)" || return 1
    else
        return 1
    fi
    [ -n "$content" ] || return 1

    local key value
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        PREV_ENV["$key"]="$value"
    done <<< "$content"

    PREV_FOUND=true

    # The verified state file wins over .env for the deployment shape.
    local state_file="$dir/$STATE_FILE_NAME"
    local state=""
    if [ -r "$state_file" ]; then
        state="$(cat "$state_file" 2>/dev/null)"
    elif sudo test -r "$state_file" 2>/dev/null; then
        state="$(sudo cat "$state_file" 2>/dev/null)"
    fi
    if [ -n "$state" ]; then
        while IFS='=' read -r key value; do
            [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
            PREV_ENV["$key"]="$value"
        done <<< "$state"
        STATE_VERIFIED=true
    fi
    return 0
}

# What is already deployed on this box, for installs made before the shape was
# recorded in .env. Guessing "docker" for those converted a running bare-metal
# machine: the compose project came up fresh while the systemd unit and nginx
# still held :8000 and :80, so the container could not bind and the upgrade died
# halfway through, having already rewritten .env.
detect_deploy_mode() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    # Running beats installed, and installed beats a leftover config file: a
    # failed conversion leaves a compose file behind on a box whose systemd
    # service is still the thing actually serving traffic.
    if systemctl is-active --quiet reqmesh 2>/dev/null; then printf 'bare'; return 0; fi
    if [ -n "$(${DOCKER[@]:-docker} ps -q --filter name=reqmesh 2>/dev/null)" ]; then
        printf 'docker'; return 0
    fi
    if [ -f /etc/systemd/system/reqmesh.service ]; then printf 'bare'; return 0; fi
    if [ -f "$dir/docker-compose.prod.yml" ]; then printf 'docker'; return 0; fi
    printf 'docker'
}

detect_proxy() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    if [ -f /etc/nginx/sites-enabled/reqmesh ] || [ -f "$dir/nginx.conf" ]; then
        printf 'nginx'; return 0
    fi
    if [ -f /etc/caddy/Caddyfile ] || [ -f "$dir/Caddyfile" ]; then
        printf 'caddy'; return 0
    fi
    printf 'none'
}

# TLS inferred from the base URL the deployment was actually advertising, which
# is the only honest signal available when REQMESH_TLS was never recorded.
detect_tls() {
    case "$(prev_env RT_BASE_URL '')" in
        https://*) [ -n "$(prev_env REQMESH_DOMAIN '')" ] && printf 'letsencrypt' || printf 'selfsigned' ;;
        http://*)  printf 'none' ;;
        *)         printf 'none' ;;
    esac
}

# ── Deployment shape reconciliation ────────────────────────────────────────────
# resolve_deploy_mode — decide the mode, or refuse and explain.
#
# Precedence: an explicit REQMESH_DEPLOY_MODE always wins; then a *verified*
# recorded mode; then whatever is actually live on the host. If an unverified
# recorded mode contradicts the live one, refuse — that combination means a
# previous run died partway and its claim cannot be trusted, and guessing
# converted a running bare-metal machine to Docker.
#
# Prints the resolved mode on stdout, or returns 1 having explained the conflict.
resolve_deploy_mode() {
    if [ -n "${REQMESH_DEPLOY_MODE:-}" ]; then
        printf '%s' "$REQMESH_DEPLOY_MODE"; return 0
    fi

    local recorded live
    recorded="$(prev_env REQMESH_DEPLOY_MODE '')"
    live="$(detect_deploy_mode)"

    if [ -z "$recorded" ]; then
        printf '%s' "$live"; return 0
    fi
    if $STATE_VERIFIED || [ "$recorded" = "$live" ]; then
        printf '%s' "$recorded"; return 0
    fi

    error "Conflicting deployment state — refusing to guess."
    error "  ${CFG[INSTALL_DIR]:-$INSTALL_DIR}/.env records: $recorded"
    error "  actually live on this host:  $live$(live_evidence)"
    error ""
    error "The recorded value was written by a run that did not finish, so it"
    error "describes a deployment that was never reached. Choose explicitly:"
    error "  REQMESH_DEPLOY_MODE=$live    keep what is running now"
    error "  REQMESH_DEPLOY_MODE=$recorded  convert (stop the current one first)"
    return 1
}

# A short parenthetical naming why we think the live mode is what it is.
live_evidence() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    if systemctl is-active --quiet reqmesh 2>/dev/null; then
        printf ' (reqmesh.service is active)'
    elif [ -f /etc/systemd/system/reqmesh.service ]; then
        printf ' (reqmesh.service is installed)'
    elif [ -n "$(${DOCKER[@]:-docker} ps -q --filter name=reqmesh 2>/dev/null)" ]; then
        printf ' (reqmesh containers are running)'
    elif [ -f "$dir/docker-compose.prod.yml" ]; then
        printf ' (a compose file is present)'
    fi
}

# ── Shared data root ───────────────────────────────────────────────────────────
# Both deployment modes read and write the same directory, so switching between
# them no longer strands the projects and the account database in storage the
# other mode cannot reach. Docker bind-mounts it rather than using a private
# named volume, and runs as the uid that owns it.
#
# Sets DATA_UID / DATA_GID for the compose file to consume. The bare-metal
# service user's ids are authoritative when that user exists, because the same
# files have to be writable by the systemd service; 999 matches the container's
# built-in user otherwise.
DATA_UID=999
DATA_GID=999

ensure_data_root() {
    local projects="${CFG[DATA_ROOT]:-/data/projects}"
    local root; root="$(dirname "$projects")"
    local user="${CFG[REQMESH_USER]:-reqmesh}"

    if id "$user" >/dev/null 2>&1; then
        DATA_UID="$(id -u "$user")"
        DATA_GID="$(id -g "$user")"
    fi

    ensure_dir "$projects"
    ensure_dir "$root/.reqmesh"
    ensure_dir "$root/.tectonic-cache"
    # Not -R: an existing populated data root may legitimately contain files
    # owned by another id, and rewriting every project's ownership on each
    # upgrade is both slow and a good way to break a running deployment.
    sudo chown "$DATA_UID:$DATA_GID" "$root" "$projects" \
        "$root/.reqmesh" "$root/.tectonic-cache" 2>/dev/null || true
    info "Data root: $projects (owner ${DATA_UID}:${DATA_GID})"
}

# ── Port holders ───────────────────────────────────────────────────────────────
# Who is actually listening on a port, as a printable phrase.
#
# Every "likely holder" message so far guessed from filesystem evidence — a unit
# file that still existed after the service was stopped, an nginx site config on a
# host whose nginx was disabled. Each one sent the operator to stop something that
# was not running while the real holder (a container) kept the port. Ask the
# system instead.
port_holder() {
    local port="$1"
    local cname
    cname="$(${DOCKER[@]:-docker} ps --format '{{.Names}} {{.Ports}}' 2>/dev/null \
             | awk -v p=":$port->" '$0 ~ p {print $1; exit}')"
    if [ -n "$cname" ]; then
        printf 'the container %s' "$cname"
        return 0
    fi
    local proc
    proc="$(sudo ss -tlnp 2>/dev/null | awk -v p=":$port\$" '
        { for (i = 1; i <= NF; i++) if ($i ~ p) { match($0, /users:\(\("[^"]+"/); 
          if (RSTART) { s = substr($0, RSTART + 8); gsub(/".*/, "", s); print s; exit } } }')"
    if [ -n "$proc" ]; then
        printf 'the process %s' "$proc"
        return 0
    fi
    printf 'an unidentified process'
}

# ── This installation's services ───────────────────────────────────────────────
# Everything the installer owns on this host, in either deployment mode.
#
# The alternative — checking each port, guessing its holder, and telling the
# operator which service to stop — produced four rounds of wrong advice, because
# the "evidence" used was files on disk rather than what was listening. An
# install already knows what it deployed; it can simply stop it.
#
# A proxy counts as ours only with evidence: an nginx site named reqmesh, or a
# Caddyfile that mentions it. A host may run nginx for something else entirely.
reqmesh_owns_nginx() { [ -f /etc/nginx/sites-enabled/reqmesh ]; }
reqmesh_owns_caddy() { sudo grep -q 'reqmesh' /etc/caddy/Caddyfile 2>/dev/null; }

# reqmesh_services — one "kind:name" per line for everything of ours now running.
reqmesh_services() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    systemctl is-active --quiet reqmesh 2>/dev/null && echo "unit:reqmesh"
    if systemctl is-active --quiet nginx 2>/dev/null && reqmesh_owns_nginx; then
        echo "unit:nginx"
    fi
    if systemctl is-active --quiet caddy 2>/dev/null && reqmesh_owns_caddy; then
        echo "unit:caddy"
    fi
    local c
    for c in $(${DOCKER[@]:-docker} ps --format '{{.Names}}' --filter 'name=reqmesh-' 2>/dev/null); do
        echo "container:$c"
    done
}

# port_is_ours <port> — is this port held by something we are about to stop?
# Such a port is not a conflict, so the check must not treat it as one.
port_is_ours() {
    local port="$1" svc
    while read -r svc; do
        [ -n "$svc" ] || continue
        case "$svc" in
            container:*)
                ${DOCKER[@]:-docker} port "${svc#container:}" 2>/dev/null \
                    | grep -q ":${port}\$" && return 0
                ;;
            unit:reqmesh) [ "$port" = "${CFG[PORT]:-8000}" ] && return 0 ;;
            unit:nginx|unit:caddy)
                { [ "$port" = 80 ] || [ "$port" = 443 ]; } && return 0
                ;;
        esac
    done <<< "$(reqmesh_services)"
    return 1
}

# stop_reqmesh_services — stop all of it. Called once the deploy has passed every
# preflight, so a failed check leaves the running deployment alone rather than
# taking it down and then refusing to continue.
stop_reqmesh_services() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    local svcs; svcs="$(reqmesh_services)"
    [ -n "$svcs" ] || return 0

    info "Stopping the current reqmesh deployment:"
    local svc
    while read -r svc; do
        [ -n "$svc" ] || continue
        info "  $svc"
    done <<< "$svcs"

    # Containers go as a project, so the network and any orphan go with them.
    if printf '%s' "$svcs" | grep -q '^container:'; then
        set_docker_cmd
        ( cd "$dir" && "${DOCKER[@]}" compose \
            -f "${CFG[COMPOSE_FILE]:-docker-compose.prod.yml}" down --remove-orphans ) \
            >/dev/null 2>&1 || true
        local stray; stray="$("${DOCKER[@]}" ps -aq --filter 'name=reqmesh-' 2>/dev/null || true)"
        [ -n "$stray" ] && "${DOCKER[@]}" rm -f $stray >/dev/null 2>&1 || true
    fi

    # Units are disabled as well as stopped: leaving one enabled means it races
    # the new deployment for the same port on the next boot.
    printf '%s' "$svcs" | grep -q '^unit:reqmesh' && \
        sudo systemctl disable --now reqmesh >/dev/null 2>&1 || true
    if printf '%s' "$svcs" | grep -q '^unit:nginx'; then
        sudo rm -f /etc/nginx/sites-enabled/reqmesh
        sudo systemctl disable --now nginx >/dev/null 2>&1 || true
    fi
    printf '%s' "$svcs" | grep -q '^unit:caddy' && \
        sudo systemctl disable --now caddy >/dev/null 2>&1 || true

    # Verify, rather than assume. A port still held here means something we did
    # not recognise owns it, and the deploy would fail on the bind instead.
    local p
    for p in "${CFG[PORT]:-8000}" 80 443; do
        if check_port "$p" && port_is_ours "$p"; then
            error "Port $p is still held after stopping our services."
            error "  holder: $(port_holder "$p")"
            return 1
        fi
    done
    success "Stopped"
}

# ── Mode conversion ────────────────────────────────────────────────────────────
# Switching between bare metal and Docker is safe now that both modes share one
# data root (see ensure_data_root): the projects and the account database stay
# where they are and the new deployment reads them in place.
#
# It was not always so. With Docker on a private named volume, a conversion came
# up against an empty data root — projects and accounts still on disk, invisible
# to the new deployment, and a fresh admin password generated. This function used
# to refuse outright for that reason; it now explains what changes and continues,
# and only objects if the data root itself would move.
guard_mode_conversion() {
    local requested="$1"
    $PREV_FOUND || return 0

    local current
    current="$(prev_env REQMESH_DEPLOY_MODE '')"
    [ -n "$current" ] || current="$(detect_deploy_mode)"
    [ "$requested" = "$current" ] && return 0

    local old_root new_root
    old_root="$(prev_env REQMESH_DATA_ROOT "$(prev_env RT_DATA_ROOT '')")"
    new_root="${CFG[DATA_ROOT]:-/data/projects}"

    if [ -n "$old_root" ] && [ "$old_root" != "$new_root" ]; then
        error "Refusing to convert $current -> $requested: the data root would move."
        error "  now:   $old_root"
        error "  after: $new_root"
        error ""
        error "Projects and accounts live in the first and would not be visible in"
        error "the second. Either keep the current location:"
        error "  RT_DATA_ROOT=$old_root REQMESH_DEPLOY_MODE=$requested ..."
        error "or move the data yourself first, then re-run."
        return 1
    fi

    # The old deployment holds the ports the new one needs, so converting always
    # means stopping it. Asking the operator to do that by hand meant the run
    # advised it and then failed on the very conflict it had just described —
    # two messages and two commands for one stated intent. Stopping it is the
    # disruptive half of the conversion, so it needs explicit authorisation, but
    # once given there is nothing left to ask.
    if [ "${REQMESH_CONFIRM_CONVERT:-0}" != "1" ]; then
        error "Converting this deployment from $current to $requested."
        error "  Data root $new_root is shared by both modes and is reused in place,"
        error "  so no projects or accounts move."
        error ""
        error "This has to stop the current $current deployment to free its ports."
        error "Re-run with REQMESH_CONFIRM_CONVERT=1 to do that and convert:"
        error "  REQMESH_CONFIRM_CONVERT=1 REQMESH_DEPLOY_MODE=$requested ..."
        error ""
        error "Or keep the current deployment: REQMESH_DEPLOY_MODE=$current"
        return 1
    fi

    warn "Converting this deployment from $current to $requested."
    warn "  Data root $new_root is shared by both modes and will be reused in place."
    warn "  The current $current deployment will be stopped once the checks pass."
    return 0
}

# ── Verified install state ─────────────────────────────────────────────────────
# .env records what a run *attempted*; this file records what actually worked.
#
# The distinction matters because .env is written before the deploy can succeed —
# compose has to read it — so a run that died afterwards left .env asserting a
# deployment that was never reached. A Docker attempt that failed to bind its
# port convinced every later run that the machine was a Docker install, and the
# next upgrade converted a working bare-metal box on the strength of it.
STATE_FILE_NAME=".reqmesh-state"
STATE_VERIFIED=false

# write_install_state — called only after a deploy has verified healthy.
write_install_state() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    write_root_file "$dir/$STATE_FILE_NAME" 644 <<STATE
# Written by install.sh after a successful deploy. Do not edit by hand.
# This is what is actually running; .env is only what was last attempted.
REQMESH_DEPLOY_MODE=${CFG[DEPLOY_MODE]:-}
REQMESH_PROXY=${CFG[PROXY]:-}
REQMESH_TLS=${CFG[TLS]:-}
REQMESH_DOMAIN=${CFG[DOMAIN]:-}
REQMESH_DATA_ROOT=${CFG[DATA_ROOT]:-}
REQMESH_VERIFIED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
STATE
}

# prev_env <KEY> <fallback> — the existing install's value, else the fallback.
prev_env() {
    local key="$1" fallback="${2:-}"
    if [ -n "${PREV_ENV[$key]:-}" ]; then
        printf '%s' "${PREV_ENV[$key]}"
    else
        printf '%s' "$fallback"
    fi
}

# ── Backups ────────────────────────────────────────────────────────────────────
# backup_file <path> — copy to <path>.bak.<ts>, elevating if needed.
#
# This was `cp "$f" "${f}.bak.${ts}" 2>/dev/null || true` in the Docker path: an
# unprivileged copy into a root-owned directory, with the failure discarded
# twice. The installer announced "existing files will be backed up" and then
# reliably backed nothing up. Returns non-zero so the caller can say so.
backup_file() {
    local path="$1" ts="${2:-$(date +%s)}"
    [ -f "$path" ] || return 0
    local dest="${path}.bak.${ts}"
    if cp -p "$path" "$dest" 2>/dev/null; then
        printf '%s' "$dest"; return 0
    fi
    if sudo cp -p "$path" "$dest" 2>/dev/null; then
        printf '%s' "$dest"; return 0
    fi
    return 1
}

# ── Docker invocation ──────────────────────────────────────────────────────────
# Sets DOCKER to the command prefix that can actually read INSTALL_DIR.
#
# The installer writes .env and the compose file as root, 0600 (they hold
# RT_SECRET and the admin password). `docker compose` then has to *read* them as
# the invoking user, and membership of the docker group does not grant that —
# the deployment failed with "open /opt/reqmesh/.env: permission denied" at the
# point where every file had been created correctly.
#
# Decided by testing readability rather than by assuming: a re-install over a
# user-owned directory should not start requiring sudo it did not need before.
set_docker_cmd() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    if [ "$(id -u)" = 0 ] || [ -r "$dir/.env" ]; then
        DOCKER=(docker)
    else
        DOCKER=(sudo docker)
    fi
}

# ── Self-signed certificates ───────────────────────────────────────────────────
# ensure_selfsigned_cert <dir> <common_name> — create server.crt/server.key.
#
# Caddy mints its own via `tls internal`; nginx does not, and nothing in the
# installer ever created one. `TLS=selfsigned` with nginx therefore pointed
# ssl_certificate at files that had never existed, so nginx refused to start.
#
# Includes the name as a SAN: a certificate with only a CN is rejected outright
# by every current browser, which would have replaced a startup failure with an
# unfixable warning page.
ensure_selfsigned_cert() {
    local dir="$1" cn="${2:-localhost}"
    local crt="$dir/server.crt" key="$dir/server.key"

    if [ -f "$crt" ] && [ -f "$key" ]; then
        info "Reusing the existing self-signed certificate in $dir"
        return 0
    fi
    if ! has_cmd openssl; then
        error "openssl is required to generate a self-signed certificate."
        return 1
    fi

    ensure_dir "$dir"

    # An IP needs an IP: SAN; a hostname needs a DNS: one.
    local san="DNS:$cn"
    case "$cn" in
        [0-9]*.[0-9]*.[0-9]*.[0-9]*) san="IP:$cn" ;;
    esac

    info "Generating a self-signed certificate for $cn..."
    local tmp
    tmp="$(mktemp -d)"
    if ! openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
            -keyout "$tmp/server.key" -out "$tmp/server.crt" \
            -subj "/CN=$cn" \
            -addext "subjectAltName=$san,DNS:localhost,IP:127.0.0.1" \
            >/dev/null 2>&1; then
        rm -rf "$tmp"
        error "Failed to generate a self-signed certificate."
        return 1
    fi

    # The key is a secret: 0600 before it leaves the temp directory.
    chmod 600 "$tmp/server.key"; chmod 644 "$tmp/server.crt"
    if ! cp -p "$tmp/server.key" "$key" 2>/dev/null; then
        sudo cp -p "$tmp/server.key" "$key"
        sudo cp -p "$tmp/server.crt" "$crt"
    else
        cp -p "$tmp/server.crt" "$crt"
    fi
    rm -rf "$tmp"

    success "Self-signed certificate written to $dir (valid 825 days)"
    warn "Browsers will warn on first visit — this certificate signs itself."
    return 0
}

# ── TLS / domain reconciliation ─────────────────────────────────────────────────
# Does this name have an address record? A missing lookup tool is not evidence of
# absence, so that case counts as resolvable rather than blocking the install.
domain_resolves() {
    local d="$1"
    if has_cmd getent && getent hosts "$d" >/dev/null 2>&1; then return 0; fi
    if has_cmd dig; then
        [ -n "$(dig +short A "$d" 2>/dev/null)" ] && return 0
        [ -n "$(dig +short AAAA "$d" 2>/dev/null)" ] && return 0
        return 1
    fi
    if has_cmd host; then host "$d" >/dev/null 2>&1 && return 0; return 1; fi
    has_cmd getent && return 1
    return 0
}

# Let's Encrypt needs a public domain it can be reached at. It cannot issue for a
# bare IP, for "localhost", or for a name that resolves nowhere.
#
# The wizard asks for the TLS mode in phase 3a and the domain in phase 4, so
# "requires public domain" could be chosen and then contradicted. The deployment
# then quietly rendered `tls internal` — a self-signed certificate — while .env
# and the state file went on claiming letsencrypt. The only clue was a warning in
# the closing summary that looked like a bug rather than the truth.
#
# Prints the TLS mode that will actually be used, and explains any change.
reconcile_tls_with_domain() {
    local tls="${CFG[TLS]:-none}"
    local domain="${CFG[DOMAIN]:-}"

    [ "$tls" = "letsencrypt" ] || { printf '%s' "$tls"; return 0; }

    if [ -n "$domain" ] && [ "$domain" != "localhost" ] \
       && [ "$domain" != "localserver.reqmesh.com" ]; then
        # Must look like a hostname, not an address: an IP has dots too, and
        # Let's Encrypt cannot issue for one. Anything without a dot is a bare
        # label that resolves only on a local network.
        case "$domain" in
            *[!0-9.]*)
                case "$domain" in
                    *.*)
                        # Let's Encrypt looks the name up before anything else:
                        # without an A/AAAA record the challenge fails with
                        # NXDOMAIN and no certificate is ever issued. Warned
                        # rather than refused — DNS may still be propagating and
                        # Caddy retries — but the operator needs to know why the
                        # padlock never appears.
                        if ! domain_resolves "$domain"; then
                            warn "'$domain' does not resolve — Let's Encrypt will fail."
                            warn "  It looks up an A/AAAA record before issuing; without one the"
                            warn "  challenge returns NXDOMAIN and no certificate is obtained."
                            warn "  Point the name at this host's public address, then re-run."
                            warn "  The site stays reachable on the LAN address regardless."
                        fi
                        printf 'letsencrypt'; return 0 ;;
                esac
                ;;
        esac
    fi

    warn "Let's Encrypt needs a public domain name, and none is configured."
    if [ -n "$domain" ]; then
        warn "  '$domain' is not a name Let's Encrypt can issue for."
    fi
    warn "  Using a self-signed certificate instead. Browsers will warn on first visit."
    warn "  Re-run with REQMESH_DOMAIN=<your.domain> for a trusted certificate."
    printf 'internal'
}

# ── Base URL ───────────────────────────────────────────────────────────────────
# The address the deployment tells people to use. It has to follow the shape of
# the deployment, because switching a machine between HTTP and HTTPS changes it:
# the proxy takes 80/443 and the app loses its published port, or the reverse.
#
# derive_base_url — the canonical URL for the *current* PROXY/TLS/DOMAIN.
derive_base_url() {
    local proxy="${CFG[PROXY]:-caddy}"
    local tls="${CFG[TLS]:-none}"
    local domain="${CFG[DOMAIN]:-}"
    local port="${CFG[PORT]:-8000}"
    local lan="${CFG[LAN_IP]:-}"

    local scheme="http"
    [ "$proxy" != "none" ] && [ "$tls" != "none" ] && scheme="https"

    local host="localhost"
    if [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ]; then
        host="$domain"
    elif [ -n "$lan" ]; then
        host="$lan"
    fi

    if [ "$proxy" != "none" ]; then
        printf '%s://%s' "$scheme" "$host"      # the proxy owns 80/443
    else
        printf '%s://%s:%s' "$scheme" "$host" "$port"
    fi
}

# base_url_fits_shape <url> — is this URL still valid for the current PROXY/TLS?
#
# Used to decide whether a base URL carried over from an existing install is
# still usable. A deliberately customised host (an external load balancer, a
# CNAME) should survive an unrelated re-run; a URL whose scheme or port
# contradicts the deployment must not, because carrying it over is how switching
# to HTTPS left the operator being told to browse to a dead http://host:8000.
base_url_fits_shape() {
    local url="$1"
    local proxy="${CFG[PROXY]:-caddy}"
    local tls="${CFG[TLS]:-none}"

    local want_scheme="http"
    [ "$proxy" != "none" ] && [ "$tls" != "none" ] && want_scheme="https"

    case "$url" in
        "${want_scheme}://"*) ;;
        *) return 1 ;;
    esac

    # Behind a proxy the app's port must not appear; without one it must.
    local port="${CFG[PORT]:-8000}"
    if [ "$proxy" != "none" ]; then
        case "$url" in *":${port}"*) return 1 ;; esac
    else
        case "$url" in *":${port}"*) ;; *) return 1 ;; esac
    fi
    return 0
}

# ── Listen address ─────────────────────────────────────────────────────────────
# Which interface the app's published port binds to.
#
# Behind a reverse proxy, loopback is correct and deliberate: the proxy holds
# 80/443 and reaches the app over the Docker network, so publishing the app
# itself to the LAN would only offer an unencrypted way around the proxy.
#
# With PROXY=none there is nothing else listening, so loopback means the install
# is reachable from precisely nowhere. The compose template's hardcoded
# `${RT_BIND:-127.0.0.1}` was never overridden by the installer, so a
# `--non-interactive` deployment with no proxy came up healthy, bound to
# 127.0.0.1, and failed its own health check against the LAN BASE_URL.
effective_bind() {
    if [ -n "${CFG[BIND]:-}" ]; then
        printf '%s' "${CFG[BIND]}"
    elif [ "${CFG[PROXY]:-caddy}" = "none" ]; then
        printf '0.0.0.0'
    else
        printf '127.0.0.1'
    fi
}

# ── Privileged file writes ─────────────────────────────────────────────────────
# The installer runs as an ordinary user and elevates per-command, so anything
# under INSTALL_DIR (/opt/reqmesh by default) needs sudo. deploy-bare.sh did this
# by hand everywhere; deploy-docker.sh did not do it at all, so the entire Docker
# path — the *default* mode — died on `mkdir: cannot create directory
# '/opt/reqmesh': Permission denied` for every non-root user.
#
# Elevation is decided by testing the target, not by checking for uid 0: the
# directory may already be user-owned from a previous install, and a needless
# sudo would then change ownership out from under the running service.

# ensure_dir <dir> — mkdir -p, elevating only if the plain attempt fails.
ensure_dir() {
    local dir="$1"
    [ -d "$dir" ] && return 0
    mkdir -p "$dir" 2>/dev/null || sudo mkdir -p "$dir"
}

# write_root_file <path> [mode] — write stdin to <path>, elevating if needed.
#
# The writer is chosen *before* the pipe runs. `tee "$f" || sudo tee "$f"` looks
# equivalent but is not: the first tee consumes stdin before failing on
# permissions, so the sudo retry inherits a drained pipe and writes an empty
# file. That exact bug once produced a 0-byte admin credential (see
# write_admin_credential).
write_root_file() {
    local path="$1" mode="${2:-}"
    ensure_dir "$(dirname "$path")"

    local writer=(tee)
    if [ -n "$mode" ]; then
        # Create with the mode *before* writing, so the content is never briefly
        # world-readable — `>` truncates but keeps the existing mode.
        if ! install -m "$mode" /dev/null "$path" 2>/dev/null; then
            sudo install -m "$mode" /dev/null "$path"
            writer=(sudo tee)
        fi
    elif ! touch "$path" 2>/dev/null; then
        sudo touch "$path"
        writer=(sudo tee)
    fi

    "${writer[@]}" "$path" >/dev/null
}

# ── Credential reporting ───────────────────────────────────────────────────────
# Write the admin password to a 0600 file and echo that file's *path* on stdout.
# The password itself is never printed: both deploy scripts used to finish with
# `info "Admin: admin / $PASSWORD"`, and installers are routinely run under tee,
# in CI, or inside a terminal recorder, so that put the credential straight into
# a log — the same finding (F-04) the backend fixed by writing a 0600 file and
# logging only the path. summary_box prints what this returns.
#
# The write is `sudo tee` or plain `tee`, decided *before* the pipe runs — not
# `tee || sudo tee`. In the fallback form the first tee has already consumed
# stdin by the time it fails on permissions, so sudo tee inherits a drained pipe
# and writes an empty file: the installer then reports a password that is not
# there, and the operator is locked out.
write_admin_credential() {
    local install_dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    local cred_file="$install_dir/.initial-admin"

    # On a re-install the app ignores RT_ADMIN_PASSWORD entirely: load_users()
    # seeds the admin only when users.yaml does not exist. Writing a freshly
    # generated password here and captioning it "Admin password" handed the
    # operator a credential that returns 401 — verified on the test host, where
    # the reported password failed and the original still worked. Say what is
    # actually true instead.
    if [ "${CFG[EXISTING_INSTALL]:-false}" = "true" ]; then
        # A credential file from the original install is left on disk but is not
        # necessarily still valid: the account may have been reseeded since, or
        # the password changed in the UI. Leaving it unmentioned invited reading
        # it and concluding the deployment was broken when the login failed.
        #
        # The application writes its own generated password to
        # $RT_DATA_ROOT/.initial-admin, which is a different file from the one
        # this installer writes under INSTALL_DIR — so say which is which.
        local old_cred="$install_dir/.initial-admin"
        if [ -f "$old_cred" ]; then
            warn "$old_cred is from the original install and may no longer be valid."
            warn "  The current password is whatever this deployment's admin account uses."
        fi
        local seeded="${CFG[DATA_ROOT]:-}/.initial-admin"
        if [ -n "${CFG[DATA_ROOT]:-}" ] && sudo test -f "$seeded" 2>/dev/null; then
            warn "  A password generated by the application is at $seeded."
        fi
        printf ''
        return 0
    fi

    if [ -n "${CFG[ADMIN_PASSWORD]:-}" ]; then
        local writer=(tee)
        if ! install -m 600 /dev/null "$cred_file" 2>/dev/null; then
            sudo install -m 600 /dev/null "$cred_file"
            writer=(sudo tee)
        fi
        printf '%s\n' "${CFG[ADMIN_PASSWORD]}" | "${writer[@]}" "$cred_file" >/dev/null
    fi

    printf '%s' "$cred_file"
}

# The closing summary both deploy scripts print. Takes the credential file path
# followed by the mode-specific management commands.
#
# Shared rather than duplicated: the two scripts previously carried their own
# copies of the URL logic, the TLS caveat and the credential write, and the
# copies had already drifted apart in wording — with the credential write
# duplicating a bug (see write_admin_credential) into two places at once.
summary_box() {
    local cred_file="$1"; shift

    local base_url="${CFG[BASE_URL]:-}"
    local lan="${CFG[LAN_IP]:-}"
    local domain="${CFG[DOMAIN]:-}"
    local proxy="${CFG[PROXY]:-none}"
    local tls="${CFG[TLS]:-none}"

    local has_domain=false
    if [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ]; then
        has_domain=true
    fi

    box_top
    box_line "reqmesh is running!" "$BOLD"
    box_line ""
    box_line "Browser URL:  $base_url" "$CYAN"
    # A second address is only worth printing when the server actually answers
    # on it. With a domain configured the proxy serves that name alone, so the
    # LAN IP would not resolve to a site — the extra line goes on the
    # domainless install, whose BASE_URL is already the LAN address.
    if ! $has_domain && [ "$proxy" != "none" ] && [ -n "$lan" ]; then
        box_line "From this PC: https://localhost" "$CYAN"
    fi
    box_line ""

    # Deliberately ASCII: see box_line. Under LC_ALL=C — which is what an
    # installer run from CI, systemd or a minimal container gets — ${#text}
    # counts bytes, so a single em dash here shortened the line by two columns.
    if [ "$proxy" = "none" ] || [ "$tls" = "none" ]; then
        box_line "! TLS is not enabled - traffic is unencrypted." "$YELLOW"
        box_line "  Do not expose this deployment to the internet." "$YELLOW"
        box_line ""
    elif ! $has_domain || [ "$tls" != "letsencrypt" ]; then
        box_line "! TLS uses a self-signed certificate." "$YELLOW"
        box_line "  Your browser will warn on first visit - accept it." "$YELLOW"
        box_line "  Re-run with a public domain for a trusted one." "$YELLOW"
        box_line ""
    fi

    box_line "Admin user:  admin"
    if [ -z "$cred_file" ]; then
        # Upgrade of an existing install: the accounts were already seeded, so
        # whatever password is in use now is still the password.
        box_line "Password:    unchanged - existing accounts were kept."
        # Naming the command matters: the seed password in .env does not apply
        # to an existing install, so "reset it from the shell" left the operator
        # with no way to act on the one thing standing between them and the app.
        if [ "${CFG[DEPLOY_MODE]:-}" = "docker" ]; then
            box_line "Lost it? Reset with:" "$YELLOW"
            box_line "  cd ${CFG[INSTALL_DIR]:-/opt/reqmesh}" "$YELLOW"
            box_line "  sudo docker compose -f ${CFG[COMPOSE_FILE]:-docker-compose.prod.yml} \\" "$YELLOW"
            box_line "       exec reqmesh python -m app.cli reset-admin" "$YELLOW"
        else
            box_line "Lost it? Reset with:" "$YELLOW"
            box_line "  sudo -u reqmesh ${CFG[INSTALL_DIR]:-/opt/reqmesh}/venv/bin/python \\" "$YELLOW"
            box_line "       -m app.cli reset-admin" "$YELLOW"
        fi
    else
        box_line "Password:    $cred_file (mode 0600)"
        box_line "Log in, change the password, then delete that file." "$YELLOW"
    fi
    box_line ""

    local line
    for line in "$@"; do
        box_line "$line"
    done
    box_bottom
}

# JSON-encode a string (quotes included). Passwords routinely contain
# characters that would otherwise break out of the literal — the generated ones
# use base64, which includes '/' and '+', and operators pick anything.
json_string() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
    else
        # Escape backslash and double-quote; enough for a password field.
        printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    fi
}

# ── Login check ────────────────────────────────────────────────────────────────
# A passing /health only proves the process is up. It says nothing about whether
# anyone can get in, and the two failure modes that actually stranded an install
# were both invisible to it:
#
#   * RT_ADMIN_PASSWORD is only applied when users.yaml is absent, so on every
#     later deploy the configured password silently does not work.
#   * Auth state landing somewhere unwritable or ephemeral, so the account is
#     never created (or is thrown away on restart).
#
# Both end with an operator holding a password the server has never heard of and
# an installer that reported success. So: actually log in.
login_check() {
    local url="${1:-http://localhost:8000}"
    local password="${2:-}"
    [ -z "$password" ] && return 0          # nothing configured to test with

    local body code
    body="$(curl -sk -m 15 -o /tmp/.reqmesh-login.$$ -w '%{http_code}' \
        -X POST "$url/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"admin\",\"password\":$(json_string "$password")}" 2>/dev/null)" || body=""
    code="$body"
    rm -f "/tmp/.reqmesh-login.$$"

    if [ "$code" = "200" ]; then
        success "Admin login verified"
        return 0
    fi

    if [ "$code" = "401" ]; then
        warn "The admin password in .env does NOT work on this instance."
        echo ""
        echo "  This is expected when the deployment already had accounts: the"
        echo "  seed password only applies when the accounts file is absent, so"
        echo "  a value set later is ignored."
        echo ""
        echo "  Reset it:"
        if [ "${CFG[DEPLOY_MODE]:-}" = "docker" ]; then
            echo "    cd ${CFG[INSTALL_DIR]:-/opt/reqmesh}"
            echo "    sudo ${DOCKER[*]:-docker} compose -f ${CFG[COMPOSE_FILE]:-docker-compose.prod.yml} \\"
            echo "         exec reqmesh python -m app.cli reset-admin"
        else
            echo "    sudo -u reqmesh ${CFG[INSTALL_DIR]:-/opt/reqmesh}/venv/bin/python \\"
            echo "         -m app.cli reset-admin"
        fi
        echo ""
        return 1
    fi

    if [ "$code" = "429" ]; then
        warn "Login rate-limited (429) — cannot verify the password right now."
        warn "Five failed attempts also lock an account for 15 minutes."
        return 0
    fi

    warn "Could not verify admin login (HTTP ${code:-no response} from $url)."
    return 1
}

# ── Health check ───────────────────────────────────────────────────────────────
healthcheck() {
    local url="${1:-http://localhost:8000/health}"
    local timeout="${2:-60}"
    local elapsed=0
    info "Waiting for reqmesh to be ready..."
    while [ $elapsed -lt $timeout ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            success "reqmesh is healthy at $url"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    # A bare "timed out, check the logs" was the least useful message the
    # installer produced: it fired while the container was healthy (the probe
    # URL was wrong), and the command it suggested — `docker compose ... logs`
    # unprefixed — is itself denied for the unprivileged operator, because the
    # .env it must read is root-owned. So: show the state, show the tail, and
    # print a command that actually runs.
    error "Health check timed out after ${timeout}s: $url never answered."
    if [ "${CFG[DEPLOY_MODE]:-}" = "docker" ]; then
        local dc="${DOCKER[*]:-docker} compose -f ${CFG[COMPOSE_FILE]:-docker-compose.prod.yml}"
        echo ""
        echo "  Container state:"
        ${DOCKER[@]:-docker} ps -a --filter 'name=reqmesh' \
            --format '    {{.Names}}  {{.Status}}' 2>/dev/null || true
        echo ""
        echo "  Last 20 log lines:"
        $dc logs --tail 20 2>&1 | sed 's/^/    /' || true
        echo ""
        echo "  Full logs:  $dc logs -f"
        # The container reporting healthy while this probe fails means the app
        # is up and the address is wrong — worth saying, because it sends the
        # reader to the proxy and the bind address instead of the app.
        if ${DOCKER[@]:-docker} ps --filter 'name=reqmesh' --filter 'health=healthy' \
             --format '{{.Names}}' 2>/dev/null | grep -q .; then
            warn "The container reports healthy — the app is running and this address is wrong."
            warn "Check the published port and RT_BIND rather than the application logs."
        fi
    else
        echo ""
        echo "  Service state:"
        systemctl is-active reqmesh 2>&1 | sed 's/^/    /' || true
        echo ""
        echo "  Last 20 log lines:"
        sudo journalctl -u reqmesh -n 20 --no-pager 2>&1 | sed 's/^/    /' || true
        echo ""
        echo "  Full logs:  sudo journalctl -u reqmesh -f"
    fi
    [ -n "${REQMESH_LOG_FILE:-}" ] && echo "  Transcript: $REQMESH_LOG_FILE"
    return 1
}
