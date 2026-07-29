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
#
# Every prompt in the fallback path writes to stderr, never stdout.
#
# Callers capture these with `value="$(gum_input …)"`, which captures stdout —
# so a prompt printed there ended up *inside the answer*. Without Gum the wizard
# was saving values like
#     DOMAIN=<esc>[0;34mServer domain name<esc>[0m []: example.com
# into config.env, and from there into the .env file and the Caddyfile. The
# password prompt was worse: its answer carried an embedded newline, which
# validate_cfg_value rejects, aborting the wizard outright. Gum writes its own
# UI to stderr for exactly this reason; the fallback has to match.
gum_input() {
    local prompt="$1" default="${2:-}" placeholder="${3:-}"
    if $GUMMED; then
        gum input --header "$prompt" --value "$default" --placeholder "$placeholder" --width 70
    else
        local reply
        printf "${BLUE}%s${NC} [%s]: " "$prompt" "$default" >&2
        read -r reply || { printf "\n" >&2; return 1; }
        printf '%s' "${reply:-$default}"
    fi
}

gum_password() {
    local prompt="$1" default="${2:-}"
    if $GUMMED; then
        gum input --header "$prompt" --value "$default" --password --width 70
    else
        local reply
        printf "${BLUE}%s${NC}: " "$prompt" >&2
        read -rs reply || { printf "\n" >&2; return 1; }
        printf "\n" >&2
        printf '%s' "${reply:-$default}"
    fi
}

gum_choose() {
    local prompt="$1"; shift
    local arr=("$@")
    if $GUMMED; then
        printf "%s\n" "$@" | gum choose --header "$prompt" --height "${#arr[@]}"
    else
        local choice i=1 opt
        printf "${BLUE}%s${NC}\n" "$prompt" >&2
        for opt in "$@"; do
            printf "  %d) %s\n" "$i" "$opt" >&2
            i=$((i + 1))
        done
        printf "Choose [1-%d]: " "${#arr[@]}" >&2
        read -r choice || choice=""
        # Out-of-range and non-numeric both fall back to the first option, which
        # is the recommended one everywhere this is used. `${arr[$((c-1))]}`
        # cannot do that itself: bash arithmetic on a non-numeric string is a
        # fatal error under `set -e`, not something a `|| echo` can catch.
        case "$choice" in
            ''|*[!0-9]*) choice=1 ;;
        esac
        if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#arr[@]}" ]; then
            choice=1
        fi
        printf '%s' "${arr[$((choice - 1))]}"
    fi
}

gum_confirm() {
    local prompt="$1"
    if $GUMMED; then
        gum confirm "$prompt" && return 0 || return 1
    else
        local reply
        printf "${BLUE}%s${NC} [y/N]: " "$prompt" >&2
        read -r reply || return 1
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

# Prompt until the value passes `validator`, which is called with the entered
# value and should print its own explanation and return non-zero on rejection.
#
# The wizard collects nine phases of input before it deploys anything, so
# aborting on a mistyped port (`exit 1`) threw all of it away — and since the
# config lives in a per-run temp directory, re-running started from nothing.
# Re-asking is the only reasonable response to a typo. p6_credentials already
# did this for the password; these are the rest.
gum_input_valid() {
    local prompt="$1" default="${2:-}" placeholder="${3:-}" validator="$4"
    local value
    while true; do
        # A failed read means the input stream ended (EOF, or a closed stdin
        # under automation). Re-prompting then would spin forever against a
        # source that can never answer, so stop and say why.
        if ! value="$(gum_input "$prompt" "$default" "$placeholder")"; then
            error "No more input available while asking: $prompt"
            exit 1
        fi
        if "$validator" "$value"; then
            printf '%s' "$value"
            return 0
        fi
        default="$value"
    done
}

# A hostname, or empty for "no domain". Rejects what would silently produce a
# broken vhost: an embedded scheme, whitespace, or an over-long name.
valid_domain() {
    local d="$1"
    case "$d" in
        *://*)  warn "Enter just the hostname — no http:// or https:// prefix."; return 1 ;;
        *[[:space:]]*) warn "A domain name cannot contain spaces."; return 1 ;;
    esac
    if [ "${#d}" -gt 253 ]; then
        warn "Domain name exceeds the 253-character limit (RFC 1035)."
        return 1
    fi
    return 0
}

valid_port() {
    local p="$1"
    case "$p" in
        ''|*[!0-9]*) warn "Port must be a number between 1 and 65535."; return 1 ;;
    esac
    # Compared as a string first: bash arithmetic aborts on a value wider than
    # a 64-bit integer, which would take the wizard down with it.
    if [ "${#p}" -gt 5 ] || [ "$p" -lt 1 ] || [ "$p" -gt 65535 ]; then
        warn "Port must be between 1 and 65535."
        return 1
    fi
    return 0
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

    # Offer to resume a previous session.
    #
    # "Previous" means a config the caller pinned via COLLECTED_DIR. The default
    # config lives in a fresh `mktemp -d` per run (lib.sh), so it is always empty
    # here and this block is correctly skipped — checking it is what makes the
    # feature honest rather than dead code that never fires.
    if [ -s "$CONFIG_FILE" ] && grep -q '=' "$CONFIG_FILE" 2>/dev/null; then
        local entries
        entries="$(grep -c '=' "$CONFIG_FILE")"
        gum_style --foreground 240 --align center \
            "Found a previous session with $entries settings." \
            ""
        if gum_confirm "Resume it and go straight to the review screen?"; then
            load_cfg
            RESUME_TO_REVIEW=true
            return
        fi
        # Declining means starting over, so the old values must actually go:
        # load_cfg already ran when this file was sourced, so without clearing
        # both the file and CFG the "fresh" run would silently inherit the old
        # secret, admin password and SMTP credentials as prompt defaults.
        info "Starting fresh — discarding the previous settings."
        : > "$CONFIG_FILE"
        CFG=()
        echo ""
    fi

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

    local domain host port proxy tls
    proxy="${CFG[PROXY]:-none}"
    tls="${CFG[TLS]:-none}"

    domain="$(gum_input_valid "Server domain name" "${CFG[DOMAIN]:-}" \
        "example.com or leave blank for localhost" valid_domain)"
    save_cfg "DOMAIN" "$domain"

    host="$(gum_input "Bind address" "${CFG[HOST]:-0.0.0.0}" "0.0.0.0 = all interfaces, 127.0.0.1 = localhost only")"
    save_cfg "HOST" "$host"

    port="$(gum_input_valid "Application port" "${CFG[PORT]:-8000}" "8000" valid_port)"
    save_cfg "PORT" "$port"

    # ── Compute BASE_URL ────────────────────────────────────────────────────
    # The scheme follows the TLS mode, not merely "is there a proxy" — nginx
    # with TLS 'none' terminates plain HTTP. Advertising https:// there gives a
    # base URL nothing answers on, and (via COOKIE_SECURE below) a session
    # cookie the browser refuses to store, so login fails with no visible error.
    local lan_ip base_url scheme="http"
    lan_ip="$(detect_lan_ip)"
    [ "$proxy" != "none" ] && [ "$tls" != "none" ] && scheme="https"

    local has_domain=false
    if [ -n "$domain" ] && [ "$domain" != "localserver.reqmesh.com" ]; then
        has_domain=true
    fi

    if [ "$proxy" != "none" ]; then
        # The proxy owns 80/443, so no port suffix.
        if $has_domain; then
            base_url="${scheme}://${domain}"
        elif [ -n "$lan_ip" ]; then
            base_url="${scheme}://${lan_ip}"
        else
            base_url="${scheme}://localhost"
        fi

        if [ "$tls" = "none" ]; then
            echo ""
            warn "TLS is disabled — traffic to this server will be unencrypted."
            gum_style --foreground 240 \
                "Passwords and session cookies will cross the network in clear text." \
                "Only acceptable on a trusted private network."
            echo ""
        elif ! $has_domain || [ "$tls" != "letsencrypt" ]; then
            echo ""
            warn "No public domain configured — TLS will use a self-signed certificate."
            gum_style --foreground 240 \
                "Browsers will show a security warning on first visit." \
                "Accept the warning to proceed (usually 'Advanced' → 'Proceed')." \
                "" \
                "If you have a public domain, re-run the wizard and enter it —" \
                "Caddy will automatically provision a trusted Let's Encrypt certificate."
            echo ""
        fi
    elif [ "$host" = "0.0.0.0" ] || [ "$host" = "127.0.0.1" ]; then
        base_url="http://localhost:${port}"
    else
        base_url="http://${host}:${port}"
    fi
    save_cfg "BASE_URL" "$base_url"
    save_cfg "LAN_IP" "$lan_ip"
    save_cfg "TLS_ACTIVE" "$([ "$scheme" = "https" ] && echo true || echo false)"

    if [ "$proxy" != "none" ]; then
        check_firewall "80 443"
    else
        check_firewall "$port"
    fi

    # Allowed hosts for Host header validation. Every name the deployment is
    # actually reachable under has to be here or the request is rejected — and
    # with no domain that means the LAN address the summary screen prints.
    local allowed_hosts=""
    if $has_domain; then
        allowed_hosts="$domain"
        [ -n "$lan_ip" ] && allowed_hosts="${allowed_hosts},${lan_ip}"
        allowed_hosts="${allowed_hosts},localhost,127.0.0.1"
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

    # Override cookie_secure for HTTP-only deployments.
    #
    # Keyed on whether TLS is actually terminated, not on whether a proxy
    # exists: "nginx + TLS none" is plain HTTP, and a Secure cookie there is
    # dropped by the browser, so every login silently fails. p3_proxy already
    # forces TLS=none when no proxy is selected, so this covers both cases.
    if [ "${CFG[TLS_ACTIVE]:-false}" != "true" ]; then
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
        while true; do
            admin_pw=$(gum_password "Admin password (min 12 chars, use upper+lower+digit+symbol)" "$admin_pw")
            if [ "${#admin_pw}" -ge 12 ]; then
                break
            fi
            warn "Password too short — must be at least 12 characters."
        done
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
        save_cfg "SMTP_PORT" "$(gum_input_valid "SMTP port" "${CFG[SMTP_PORT]:-587}" "587" valid_port)"
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

        # Commit schedule
        local schedule
        schedule=$(gum_choose "Commit schedule" \
            "every_change — commit on every change (debounced, default)" \
            "interval     — commit on a time schedule (every N hours)" \
            "changes      — commit after N changes accumulate" \
            "both         — whichever comes first (time or N changes)")
        save_cfg "GIT_COMMIT_SCHEDULE" "${schedule%% *}"

        if [[ "$schedule" == interval* || "$schedule" == both* ]]; then
            save_cfg "GIT_COMMIT_INTERVAL_HOURS" "$(gum_input "Commit interval (hours)" "24" "24")"
        else
            save_cfg "GIT_COMMIT_INTERVAL_HOURS" "0"
        fi
        if [[ "$schedule" == changes* || "$schedule" == both* ]]; then
            save_cfg "GIT_COMMIT_CHANGES_THRESHOLD" "$(gum_input "Number of changes per commit" "50" "50")"
        else
            save_cfg "GIT_COMMIT_CHANGES_THRESHOLD" "0"
        fi
    else
        save_cfg "GIT_REMOTE_URL" ""
        save_cfg "GIT_AUTOCOMMIT" "true"
        save_cfg "GIT_PUSH_ON_COMMIT" "false"
        save_cfg "GIT_PUSH_INTERVAL_MINUTES" "0"
        save_cfg "GIT_COMMIT_SCHEDULE" "every_change"
        save_cfg "GIT_COMMIT_INTERVAL_HOURS" "0"
        save_cfg "GIT_COMMIT_CHANGES_THRESHOLD" "50"
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
        "LAN address:        ${CFG[LAN_IP]:-N/A}" \
        "Profile:            ${CFG[PROFILE]:-team}" \
        "Install directory:  ${CFG[INSTALL_DIR]:-}" \
        "Data directory:     ${CFG[DATA_ROOT]:-}" \
        "Admin password:     $([ "${CFG[EXISTING_INSTALL]:-false}" = "true" ] \
                                && echo 'unchanged (existing accounts kept)' \
                                || echo 'generated - shown after install')" \
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

    # Read the settings of any install already on this box, so an upgrade
    # defaults to what the machine is doing rather than to factory values.
    # Each phase still asks; PREV_ENV only changes the default offered.
    #
    # Nothing is written to CONFIG_FILE here. p1_welcome offers to resume a saved
    # session when that file is non-empty, so a save_cfg at this point made every
    # run look like a resumable one — the wizard asked an extra question that the
    # caller had no answer for, and every scripted answer after it landed one
    # prompt too early. The flag is persisted after p1_welcome instead, which is
    # also where a declined resume clears the file.
    local _had_install=false
    if load_installed_env "${REQMESH_INSTALL_DIR:-/opt/reqmesh}"; then
        _had_install=true
    fi

    # p1_welcome sets this when the user resumes a saved session. It has to be
    # checked *here*: `return` inside p1_welcome only leaves that function, so
    # the earlier "jump to review" path ran p9_review and then fell straight
    # through into p2…p9, re-asking every question it had just skipped.
    RESUME_TO_REVIEW=false

    p1_welcome

    # Safe to persist now: the resume prompt is behind us, and a declined resume
    # has already cleared the file.
    save_cfg "EXISTING_INSTALL" "$_had_install"
    if $_had_install; then
        warn "An existing reqmesh installation was found at ${REQMESH_INSTALL_DIR:-/opt/reqmesh}."
        warn "Its settings are offered as the defaults below."
        warn "Accounts and project data are kept — the admin password is not reset."
        echo ""
    fi

    if ! $RESUME_TO_REVIEW; then
        p2_deploy_mode
        p3_proxy
        p4_domain
        p5_profile
        p6_credentials
        p7_integrations
        p8_paths
    fi
    p9_review
}

# If run directly, execute the wizard
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    run_wizard
fi
