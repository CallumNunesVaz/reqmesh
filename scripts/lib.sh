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
install_tectonic() {
    if has_cmd tectonic; then
        info "tectonic already installed"
        return 0
    fi
    info "Installing tectonic PDF engine..."
    curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
    if [ -f tectonic ]; then
        sudo mv tectonic /usr/local/bin/tectonic
        success "tectonic installed to /usr/local/bin/tectonic"
    else
        warn "tectonic download failed — PDF reports will use weasyprint fallback"
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
render_caddyfile() {
    local backend="$1"
    local domain="${CFG[DOMAIN]:-}"
    local tls="${CFG[TLS]:-letsencrypt}"
    local content
    content="$(< "$TEMPLATES_DIR/Caddyfile.tmpl")"

    # Caddy requires the global options block to come first in the file.
    local site_address tls_directive global_block=""
    if [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ]; then
        site_address="$domain"
        if [ "$tls" = "letsencrypt" ]; then
            tls_directive=""          # Let's Encrypt is Caddy's default
        else
            tls_directive="    tls internal"
        fi
    else
        # A bare `:443` routes on every hostname, which is why it was used here,
        # but it cannot *serve* TLS: `tls internal` has no name to issue a
        # certificate for, and a client connecting to a bare IP sends no SNI, so
        # Caddy has nothing to present. The handshake died with
        # "tlsv1 alert internal error" — the site answered on :80 and was
        # unreachable on :443.
        #
        # Naming the addresses gives the internal CA something to sign; Caddy
        # supports IP addresses as site addresses and issues IP SANs for them.
        site_address="https://localhost, https://127.0.0.1"
        local lan="${CFG[LAN_IP]:-}"
        [ -n "$lan" ] && site_address="https://$lan, $site_address"
        tls_directive="    tls internal"

        # Naming the site is necessary but not sufficient. A client connecting
        # to a bare IP sends no SNI at all (RFC 6066 forbids IP literals there),
        # so Caddy has no name to match and aborts the handshake even though it
        # holds a valid certificate for that IP. default_sni tells it which
        # certificate to present when the client offers no name.
        # $( ) strips trailing newlines, so the separating blank line is added
        # explicitly — without it the block runs into the template's first
        # comment and Caddy fails to parse the file.
        if [ -n "$lan" ]; then
            global_block="$(printf '{\n\tdefault_sni %s\n}' "$lan")"$'\n\n'
        fi
    fi

    content="${global_block}${content}"
    content="${content//%_SITE_ADDRESS_%/$site_address}"
    content="${content//%_TLS_%/$tls_directive}"
    content="${content//reqmesh:8000/$backend}"

    # Named sites get an automatic HTTP->HTTPS redirect from Caddy, but only for
    # the names listed. A catch-all keeps http:// working for any other address
    # this box answers on (a second interface, a hostname added later) instead of
    # refusing the connection outright.
    case "$site_address" in
        *localhost*)
            content+="
:80 {
    redir https://{host}{uri} permanent
}" ;;
    esac

    printf '%s\n' "$content"
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
    box_line "Password:    $cred_file (mode 0600)"
    box_line "Log in, change the password, then delete that file." "$YELLOW"
    box_line ""

    local line
    for line in "$@"; do
        box_line "$line"
    done
    box_bottom
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
    error "Health check timed out after ${timeout}s. Check logs:"
    if [ "${CFG[DEPLOY_MODE]:-}" = "docker" ]; then
        echo "  docker compose -f ${CFG[COMPOSE_FILE]:-docker-compose.prod.yml} logs"
    else
        echo "  journalctl -u reqmesh -f"
    fi
    return 1
}
