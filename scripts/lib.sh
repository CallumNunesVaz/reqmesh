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

# ── Credential reporting ───────────────────────────────────────────────────────
# Print where the admin password is, never the password itself.
#
# Both deploy scripts used to finish with `info "Admin: admin / $PASSWORD"`.
# Installers are routinely run under `tee`, in CI, or inside a terminal
# recorder, so that put the credential straight into a log — the same finding
# (F-04) the backend already fixed by writing to a 0600 file and logging only
# the path. This mirrors that behaviour so the two agree.
report_admin_credential() {
    local install_dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    local cred_file="$install_dir/.initial-admin"

    if [ -n "${CFG[ADMIN_PASSWORD]:-}" ]; then
        install -m 600 /dev/null "$cred_file" 2>/dev/null || {
            sudo install -m 600 /dev/null "$cred_file"
        }
        printf '%s\n' "${CFG[ADMIN_PASSWORD]}" | \
            { tee "$cred_file" >/dev/null 2>&1 || sudo tee "$cred_file" >/dev/null; }
    fi

    info "Admin:   username 'admin'"
    info "         password written to $cred_file (mode 0600)"
    warn "         Log in, change it, then delete that file."
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
