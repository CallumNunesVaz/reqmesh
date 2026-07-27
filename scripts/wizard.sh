#!/usr/bin/env bash
# wizard.sh — interactive Gum TUI for reqmesh deployment configuration
# shellcheck disable=SC1090,SC1091,SC2155,SC2034
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_cfg

# Require Gum for the interactive wizard
require_gum() {
    if ! command -v gum &>/dev/null; then
        warn "Gum is not installed — falling back to plain-text prompts."
        GUMMED=false
    else
        GUMMED=true
    fi
}

# ── Prompt wrappers (Gum when available, read fallback) ────────────────────────
gum_input() {
    local prompt="$1" default="${2:-}" placeholder="${3:-}"
    if $GUMMED; then
        gum input --header "$prompt" --value "$default" --placeholder "$placeholder" --width 70
    else
        printf "${BLUE}%s${NC} [%s]: " "$prompt" "$default"
        read -r reply
        echo "${reply:-$default}"
    fi
}

gum_password() {
    local prompt="$1" default="${2:-}"
    if $GUMMED; then
        gum input --header "$prompt" --value "$default" --password --width 70
    else
        printf "${BLUE}%s${NC}: " "$prompt"
        read -rs reply
        echo ""
        echo "${reply:-$default}"
    fi
}

gum_choose() {
    local prompt="$1"; shift
    if $GUMMED; then
        printf "%s\n" "$@" | gum choose --header "$prompt" --height "${#@}"
    else
        printf "${BLUE}%s${NC}\n" "$prompt"
        local i=1
        for opt in "$@"; do
            printf "  %d) %s\n" "$i" "$opt"
            i=$((i + 1))
        done
        printf "Choose [1-%d]: " $((i - 1))
        read -r choice
        local arr=("$@")
        echo "${arr[$((choice - 1))]}" 2>/dev/null || echo "${arr[0]}"
    fi
}

gum_confirm() {
    local prompt="$1"
    if $GUMMED; then
        gum confirm "$prompt" && return 0 || return 1
    else
        printf "${BLUE}%s${NC} [y/N]: " "$prompt"
        read -r reply
        [[ "$reply" =~ ^[Yy] ]]
    fi
}

gum_style() {
    if $GUMMED; then
        gum style "$@"
    else
        printf "%s\n" "$*"
    fi
}

# ── Phase banners ──────────────────────────────────────────────────────────────
phase() {
    local num="$1" title="$2"
    gum_style --foreground 212 --bold "Phase $num" " — $title"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — Welcome
# ═══════════════════════════════════════════════════════════════════════════════
p1_welcome() {
    clear
    gum_style \
        --foreground 212 --bold --align center \
        --width 70 \
        "reqmesh Install Wizard" \
        "" \
        "This wizard will guide you through deploying reqmesh" \
        "on your server. Dependencies (Docker, Caddy, system" \
        "packages) will be installed automatically as needed." \
        "" \
        "You can cancel at any time with Ctrl+C." \
        ""
    gum_style --foreground 240 --align center \
        "Press Enter to continue or Esc to exit."

    if $GUMMED; then
        gum confirm "Continue?" --affirmative "Let's go" --negative "Exit" || exit 0
    else
        printf "\nPress Enter to continue... "
        read -r
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Deployment mode
# ═══════════════════════════════════════════════════════════════════════════════
p2_deploy_mode() {
    clear
    phase "2" "Deployment mode"

    gum_style --foreground 240 \
        "How should reqmesh be deployed?" "" \
        "  Docker Compose — containers, auto-update, read-only rootfs (recommended)" \
        "  Bare-metal    — direct process via systemd, no container runtime needed"

    local mode
    if has_cmd docker && docker info &>/dev/null 2>&1; then
        mode=$(gum_choose "Deployment mode" "docker" "bare")
    else
        gum_style --foreground 240 "Docker not detected — bare-metal only."
        mode="bare"
    fi

    save_cfg "DEPLOY_MODE" "$mode"
    if [ "$mode" = "docker" ]; then
        check_docker
        if ! $DOCKER_OK; then
            if gum_confirm "Docker is not running. Install Docker now?"; then
                install_docker
            else
                error "Docker is required for Docker deployment."
                exit 1
            fi
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Reverse proxy
# ═══════════════════════════════════════════════════════════════════════════════
p3_proxy() {
    clear
    phase "3" "Reverse proxy"

    local mode="${CFG[DEPLOY_MODE]}"

    gum_style --foreground 240 \
        "A reverse proxy handles HTTPS, TLS certificates, and security headers." \
        "" \
        "  Caddy — automatic Let's Encrypt TLS, zero configuration (recommended)" \
        "  nginx — manual certificates, wider enterprise familiarity" \
        "  None  — direct port access (development / LAN only)"

    local proxy
    if [ "$mode" = "docker" ]; then
        proxy=$(gum_choose "Reverse proxy" "caddy" "nginx" "none")
    else
        proxy=$(gum_choose "Reverse proxy" "caddy" "nginx" "none")
    fi
    save_cfg "PROXY" "$proxy"

    if [ "$proxy" = "none" ]; then
        save_cfg "TLS" "none"
        return
    fi

    # TLS choice
    clear
    phase "3a" "TLS configuration"

    local tls
    if [ "$proxy" = "caddy" ]; then
        tls=$(gum_choose "TLS mode" \
            "letsencrypt — automatic via Let's Encrypt (requires public domain)" \
            "internal   — self-signed certificate for LAN / intranet")
    else
        tls=$(gum_choose "TLS mode" \
            "selfsigned   — auto-generated self-signed certificate" \
            "certfiles    — provide your own certificate files" \
            "none         — HTTP only (not recommended for production)")
    fi
    save_cfg "TLS" "${tls%% *}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4 — Domain & networking
# ═══════════════════════════════════════════════════════════════════════════════
p4_domain() {
    clear
    phase "4" "Domain & networking"

    local domain=$(gum_input "Server domain name" "${CFG[DOMAIN]:-}" "example.com or leave blank for localhost")
    save_cfg "DOMAIN" "$domain"

    local host=$(gum_input "Bind address" "${CFG[HOST]:-0.0.0.0}" "0.0.0.0 = all interfaces, 127.0.0.1 = localhost only")
    save_cfg "HOST" "$host"

    local port=$(gum_input "Port" "${CFG[PORT]:-8000}" "8000")
    save_cfg "PORT" "$port"

    local base_url
    if [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ]; then
        base_url="https://${domain}"
    elif [ "$host" = "0.0.0.0" ] || [ "$host" = "127.0.0.1" ]; then
        base_url="http://localhost:${port}"
    else
        base_url="http://${host}:${port}"
    fi
    save_cfg "BASE_URL" "$base_url"

    # Allowed hosts for Host header validation
    local allowed_hosts="$domain"
    if [ -z "$domain" ]; then
        allowed_hosts=""
    fi
    save_cfg "ALLOWED_HOSTS" "$allowed_hosts"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5 — Security profile
# ═══════════════════════════════════════════════════════════════════════════════
p5_profile() {
    clear
    phase "5" "Security profile"

    gum_style --foreground 240 \
        "The profile sets sensible defaults for your deployment scenario:" \
        "" \
        "  personal  — single-user localhost, no login required" \
        "  team      — shared server, login required, admin provisions accounts" \
        "  hardened  — team + mandatory email verification, strict CSP (defence)" \
        ""

    local profile=$(gum_choose "Security profile" "team" "hardened" "personal")
    save_cfg "PROFILE" "$profile"

    # Derive defaults from profile
    case "$profile" in
        personal)
            save_cfg "REQUIRE_AUTH" "false"
            save_cfg "SELF_REG" "true"
            save_cfg "COOKIE_SECURE" "false"
            save_cfg "REQUIRE_EMAIL_VERIFICATION" "false"
            ;;
        team)
            save_cfg "REQUIRE_AUTH" "true"
            save_cfg "SELF_REG" "false"
            save_cfg "COOKIE_SECURE" "true"
            save_cfg "REQUIRE_EMAIL_VERIFICATION" "false"
            ;;
        hardened)
            save_cfg "REQUIRE_AUTH" "true"
            save_cfg "SELF_REG" "false"
            save_cfg "COOKIE_SECURE" "true"
            save_cfg "REQUIRE_EMAIL_VERIFICATION" "true"
            ;;
    esac

    # Override cookie_secure for HTTP-only deployments
    if [ "${CFG[TLS]:-none}" = "none" ] && [ "${CFG[PROXY]:-none}" = "none" ]; then
        save_cfg "COOKIE_SECURE" "false"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6 — Admin credentials
# ═══════════════════════════════════════════════════════════════════════════════
p6_credentials() {
    clear
    phase "6" "Admin credentials"

    # Secret key
    local secret="${CFG[RT_SECRET]:-}"
    if [ -z "$secret" ]; then
        secret=$(rand_secret 32)
    fi
    local regen_choice=$(gum_choose "Signing secret" \
        "auto-generate — cryptographically random (recommended)" \
        "enter custom  — paste your own secret")
    if [[ "$regen_choice" == *"enter"* ]]; then
        secret=$(gum_password "Enter signing secret (min 32 chars)" "$secret")
    fi
    save_cfg "RT_SECRET" "$secret"

    # Admin password
    local admin_pw="${CFG[ADMIN_PASSWORD]:-}"
    if [ -z "$admin_pw" ]; then
        admin_pw=$(rand_secret 16 | base64 2>/dev/null || rand_secret 12)
    fi
    local pw_choice=$(gum_choose "Admin password" \
        "auto-generate — secure random password (recommended)" \
        "enter custom  — choose your own password (min 12 chars)")
    if [[ "$pw_choice" == *"enter"* ]]; then
        admin_pw=$(gum_password "Admin password (min 12 chars, upper+lower+digit+symbol)" "$admin_pw")
    fi
    save_cfg "ADMIN_PASSWORD" "$admin_pw"

    # Email verification (only relevant if hardened)
    if [ "${CFG[PROFILE]:-team}" = "hardened" ]; then
        if gum_confirm "Require email verification for new accounts?"; then
            save_cfg "REQUIRE_EMAIL_VERIFICATION" "true"
        else
            save_cfg "REQUIRE_EMAIL_VERIFICATION" "false"
        fi
    fi

    # Self-registration (team/hardened default off, show option)
    if [ "${CFG[PROFILE]:-team}" != "personal" ]; then
        if gum_confirm "Allow self-registration from the login page?"; then
            save_cfg "SELF_REG" "true"
        fi
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7 — Optional integrations
# ═══════════════════════════════════════════════════════════════════════════════
p7_integrations() {
    clear
    phase "7" "Optional integrations"

    # SMTP
    if gum_confirm "Configure SMTP for email (password reset, invitations)?"; then
        save_cfg "SMTP_HOST" "$(gum_input "SMTP host" "${CFG[SMTP_HOST]:-}" "smtp.example.com")"
        save_cfg "SMTP_PORT" "$(gum_input "SMTP port" "${CFG[SMTP_PORT]:-587}" "587")"
        save_cfg "SMTP_USERNAME" "$(gum_input "SMTP username" "${CFG[SMTP_USERNAME]:-}" "")"
        save_cfg "SMTP_PASSWORD" "$(gum_password "SMTP password" "")"
        save_cfg "SMTP_FROM" "$(gum_input "From address" "${CFG[SMTP_FROM]:-reqmesh@localhost}" "reqmesh@example.com")"
        save_cfg "SMTP_USE_TLS" "true"
    else
        save_cfg "SMTP_HOST" ""
        save_cfg "SMTP_PORT" "587"
        save_cfg "SMTP_USERNAME" ""
        save_cfg "SMTP_PASSWORD" ""
        save_cfg "SMTP_FROM" "reqmesh@localhost"
        save_cfg "SMTP_USE_TLS" "true"
    fi

    # Git remote
    if gum_confirm "Configure a git remote for automatic backup?"; then
        save_cfg "GIT_REMOTE_URL" "$(gum_input "Git remote URL" "${CFG[GIT_REMOTE_URL]:-}" "git@github.com:org/repo.git or https://...")"
        save_cfg "GIT_AUTOCOMMIT" "true"
        save_cfg "GIT_PUSH_ON_COMMIT" "false"
        save_cfg "GIT_PUSH_INTERVAL_MINUTES" "$(gum_input "Push interval (minutes, 0=off)" "0" "15")"
    else
        save_cfg "GIT_REMOTE_URL" ""
        save_cfg "GIT_AUTOCOMMIT" "true"
        save_cfg "GIT_PUSH_ON_COMMIT" "false"
        save_cfg "GIT_PUSH_INTERVAL_MINUTES" "0"
    fi

    # Git author identity
    save_cfg "GIT_USER_NAME" "$(gum_input "Git author name" "${CFG[GIT_USER_NAME]:-reqmesh}" "reqmesh")"
    save_cfg "GIT_USER_EMAIL" "$(gum_input "Git author email" "${CFG[GIT_USER_EMAIL]:-reqmesh@localhost}" "reqmesh@example.com")"

    # Branding
    if gum_confirm "Configure report branding (company name, logo)?"; then
        save_cfg "REPORT_COMPANY_NAME" "$(gum_input "Company name" "${CFG[REPORT_COMPANY_NAME]:-}" "Acme Corp")"
        save_cfg "REPORT_DOCUMENT_TITLE" "$(gum_input "Default document title" "${CFG[REPORT_DOCUMENT_TITLE]:-}" "Requirements Document")"
        save_cfg "REPORT_LOGO_URL" "$(gum_input "Report logo URL" "${CFG[REPORT_LOGO_URL]:-}" "https://example.com/logo.png")"
    else
        save_cfg "REPORT_COMPANY_NAME" ""
        save_cfg "REPORT_DOCUMENT_TITLE" ""
        save_cfg "REPORT_LOGO_URL" ""
    fi

    # Demo project
    if gum_confirm "Seed the Cessna 172S demo project on first start?"; then
        save_cfg "SEED_DEMO" "true"
    else
        save_cfg "SEED_DEMO" "false"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8 — File paths
# ═══════════════════════════════════════════════════════════════════════════════
p8_paths() {
    clear
    phase "8" "Installation paths"

    save_cfg "INSTALL_DIR" "$(gum_input "Install directory" "${CFG[INSTALL_DIR]:-/opt/reqmesh}" "/opt/reqmesh")"

    local data_root
    if [ "${CFG[DEPLOY_MODE]}" = "docker" ]; then
        data_root="/data/projects"  # Docker volume path, not host
    else
        data_root="${CFG[INSTALL_DIR]}/data/projects"
    fi
    save_cfg "DATA_ROOT" "$(gum_input "Project data directory" "${CFG[DATA_ROOT]:-$data_root}" "$data_root")"

    if [ "${CFG[DEPLOY_MODE]}" = "bare" ]; then
        save_cfg "REQMESH_USER" "$(gum_input "Service user" "${CFG[REQMESH_USER]:-reqmesh}" "reqmesh")"
        save_cfg "REQMESH_GROUP" "$(gum_input "Service group" "${CFG[REQMESH_GROUP]:-reqmesh}" "reqmesh")"
    fi

    local proxy="${CFG[PROXY]:-none}"
    local proxy_cidr="${CFG[PROXY_TRUSTED_CIDR]:-127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"
    save_cfg "PROXY_TRUSTED_CIDR" "$proxy_cidr"

    if [ "$proxy" = "caddy" ] || [ "$proxy" = "nginx" ]; then
        save_cfg "HOST" "127.0.0.1"  # Proxy handles external binding
    fi

    save_cfg "OFFLINE_MODE" "false"
    save_cfg "CORS_ORIGINS" ""
    save_cfg "UPDATE_CONTROL_DIR" "${CFG[UPDATE_CONTROL_DIR]:-/control}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9 — Review & confirm
# ═══════════════════════════════════════════════════════════════════════════════
p9_review() {
    clear
    phase "9" "Review configuration"

    load_cfg

    gum_style --foreground 240 --border rounded --padding "1 2" --width 70 \
        "Deployment mode:    ${CFG[DEPLOY_MODE]:-}" \
        "Reverse proxy:      ${CFG[PROXY]:-none}" \
        "TLS mode:           ${CFG[TLS]:-none}" \
        "Domain:             ${CFG[DOMAIN]:-localhost}" \
        "Base URL:           ${CFG[BASE_URL]:-}" \
        "Profile:            ${CFG[PROFILE]:-team}" \
        "Install directory:  ${CFG[INSTALL_DIR]:-}" \
        "Data directory:     ${CFG[DATA_ROOT]:-}" \
        "Admin password:     ${CFG[ADMIN_PASSWORD]:-}" \
        "SMTP:               ${CFG[SMTP_HOST]:-disabled}" \
        "Git remote:         ${CFG[GIT_REMOTE_URL]:-disabled}" \
        "Demo project:       ${CFG[SEED_DEMO]:-true}"

    echo ""
    if ! gum_confirm "Deploy with these settings?"; then
        error "Deployment cancelled."
        exit 0
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main — run all phases
# ═══════════════════════════════════════════════════════════════════════════════
run_wizard() {
    require_gum
    detect_os

    p1_welcome
    p2_deploy_mode
    p3_proxy
    p4_domain
    p5_profile
    p6_credentials
    p7_integrations
    p8_paths
    p9_review
}

# If run directly, execute the wizard
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    run_wizard
fi
