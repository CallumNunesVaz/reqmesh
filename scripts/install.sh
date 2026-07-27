#!/usr/bin/env bash
# install.sh — reqmesh deployment installer
#
# Usage:
#   ./install.sh                          Interactive wizard (recommended)
#   ./install.sh --non-interactive [opts] Scripted deployment (CI/automation)
#   ./install.sh --help                   Show help
#
# The interactive wizard walks through deployment mode, reverse proxy,
# security profile, credentials, and optional integrations. At the end
# it generates configuration files and deploys reqmesh.
#
# For non-interactive use, set environment variables:
#   RT_PROFILE, RT_SECRET, RT_ADMIN_PASSWORD, RT_BASE_URL, ...
#   or pass them on the command line: --profile team --domain example.com ...
#   See the full list at: https://github.com/CallumNunesVaz/reqmesh
#
# Dependencies are installed automatically:
#   Docker path: Docker + Compose plugin, Caddy (optional)
#   Bare path:   Python 3.12+, systemd, Caddy/nginx (optional), tectonic

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# ═══════════════════════════════════════════════════════════════════════════════
# Bootstrap Gum
# ═══════════════════════════════════════════════════════════════════════════════
bootstrap_gum() {
    if command -v gum &>/dev/null; then
        return 0
    fi
    info "Gum TUI not found — downloading..."
    local gum_ver="0.14.5"
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        *)       arch="amd64" ;; # fallback
    esac
    local os
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"

    local base="https://github.com/charmbracelet/gum/releases/download/v${gum_ver}"
    local tarball="gum_${gum_ver}_${os}_${arch}.tar.gz"
    local tmpdir
    tmpdir="$(mktemp -d)"

    # Download to disk and verify against the release's published checksums
    # before unpacking, rather than piping curl straight into tar. A truncated
    # or corrupted download can no longer produce a half-written binary that
    # then gets put on PATH and executed.
    #
    # Note this proves integrity, not provenance — the checksums come from the
    # same host as the tarball, so it is not a defence against a compromised
    # upstream release. Gum is optional UI: air-gapped installs should
    # pre-install it (or skip it and use the plain-text prompts).
    if ! curl -fsSL --proto '=https' --tlsv1.2 -o "$tmpdir/$tarball" "$base/$tarball"; then
        warn "Gum download failed. Falling back to plain-text prompts."
        rm -rf "$tmpdir"
        return 0
    fi

    if curl -fsSL --proto '=https' --tlsv1.2 -o "$tmpdir/checksums.txt" \
            "$base/checksums.txt" 2>/dev/null && has_cmd sha256sum; then
        local expected actual
        expected="$(awk -v f="$tarball" '$2 == f || $2 == "*"f {print $1}' "$tmpdir/checksums.txt" | head -1)"
        actual="$(sha256sum "$tmpdir/$tarball" | awk '{print $1}')"
        if [ -z "$expected" ]; then
            warn "No checksum published for $tarball — skipping Gum rather than trusting it."
            rm -rf "$tmpdir"
            return 0
        fi
        if [ "$expected" != "$actual" ]; then
            error "Gum checksum mismatch — refusing to install."
            error "  expected $expected"
            error "  actual   $actual"
            rm -rf "$tmpdir"
            return 0
        fi
    else
        warn "Could not verify the Gum checksum — skipping Gum rather than trusting it."
        rm -rf "$tmpdir"
        return 0
    fi

    tar xzf "$tmpdir/$tarball" -C "$tmpdir"
    local binary
    binary="$(find "$tmpdir" -type f -name gum -perm -u+x | head -1)"
    if [ -z "$binary" ]; then
        warn "No gum binary in the archive. Falling back to plain-text prompts."
        rm -rf "$tmpdir"
        return 0
    fi

    # Install to ~/.local/bin or /usr/local/bin
    local dest="${HOME}/.local/bin"
    mkdir -p "$dest"
    mv "$binary" "$dest/gum" 2>/dev/null || {
        sudo mv "$binary" /usr/local/bin/gum
        dest="/usr/local/bin"
    }
    rm -rf "$tmpdir"

    # Add to PATH for this session if needed
    export PATH="$dest:$PATH"

    if command -v gum &>/dev/null; then
        success "Gum installed to $dest/gum"
    else
        warn "Gum download failed. Falling back to plain-text prompts."
        warn "You can install Gum manually: https://github.com/charmbracelet/gum#installation"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Non-interactive mode
# ═══════════════════════════════════════════════════════════════════════════════
non_interactive() {
    info "Running in non-interactive mode..."

    # Read settings from environment variables (RT_* prefix)
    # The deploy scripts pick these up from the saved config file
    save_cfg "DEPLOY_MODE" "${REQMESH_DEPLOY_MODE:-docker}"
    save_cfg "PROXY" "${REQMESH_PROXY:-caddy}"
    save_cfg "TLS" "${REQMESH_TLS:-letsencrypt}"
    save_cfg "DOMAIN" "${REQMESH_DOMAIN:-}"
    save_cfg "HOST" "${RT_HOST:-0.0.0.0}"
    save_cfg "PORT" "${RT_PORT:-8000}"
    save_cfg "BASE_URL" "${RT_BASE_URL:-http://localhost:8000}"
    save_cfg "PROFILE" "${RT_PROFILE:-team}"
    save_cfg "RT_SECRET" "${RT_SECRET:-$(rand_secret 32)}"
    save_cfg "ADMIN_PASSWORD" "${RT_ADMIN_PASSWORD:-$(rand_secret 12)}"
    save_cfg "REQUIRE_AUTH" "${RT_REQUIRE_AUTH:-true}"
    save_cfg "SELF_REG" "${RT_ALLOW_SELF_REGISTRATION:-false}"
    save_cfg "COOKIE_SECURE" "${RT_COOKIE_SECURE:-true}"
    save_cfg "REQUIRE_EMAIL_VERIFICATION" "${RT_REQUIRE_EMAIL_VERIFICATION:-false}"
    save_cfg "SMTP_HOST" "${RT_SMTP_HOST:-}"
    save_cfg "SMTP_PORT" "${RT_SMTP_PORT:-587}"
    save_cfg "SMTP_USERNAME" "${RT_SMTP_USERNAME:-}"
    save_cfg "SMTP_PASSWORD" "${RT_SMTP_PASSWORD:-}"
    save_cfg "SMTP_FROM" "${RT_SMTP_FROM:-reqmesh@localhost}"
    save_cfg "SMTP_USE_TLS" "${RT_SMTP_USE_TLS:-true}"
    save_cfg "GIT_REMOTE_URL" "${RT_GIT_REMOTE_URL:-}"
    save_cfg "GIT_AUTOCOMMIT" "${RT_GIT_AUTOCOMMIT:-true}"
    save_cfg "GIT_PUSH_ON_COMMIT" "${RT_GIT_PUSH_ON_COMMIT:-false}"
    save_cfg "GIT_PUSH_INTERVAL_MINUTES" "${RT_GIT_PUSH_INTERVAL_MINUTES:-0}"
    save_cfg "GIT_USER_NAME" "${GIT_USER_NAME:-reqmesh}"
    save_cfg "GIT_USER_EMAIL" "${GIT_USER_EMAIL:-reqmesh@localhost}"
    save_cfg "REPORT_COMPANY_NAME" "${RT_REPORT_COMPANY_NAME:-}"
    save_cfg "REPORT_DOCUMENT_TITLE" "${RT_REPORT_DOCUMENT_TITLE:-}"
    save_cfg "REPORT_LOGO_URL" "${RT_REPORT_LOGO_URL:-}"
    save_cfg "SEED_DEMO" "${RT_SEED_DEMO:-true}"
    save_cfg "OFFLINE_MODE" "${RT_OFFLINE_MODE:-false}"
    save_cfg "INSTALL_DIR" "${REQMESH_INSTALL_DIR:-/opt/reqmesh}"
    save_cfg "DATA_ROOT" "${RT_DATA_ROOT:-/opt/reqmesh/data/projects}"
    save_cfg "PROXY_TRUSTED_CIDR" "${RT_PROXY_TRUSTED_CIDR:-127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"
    save_cfg "UPDATE_CONTROL_DIR" "${RT_UPDATE_CONTROL_DIR:-/control}"
    save_cfg "CORS_ORIGINS" "${RT_CORS_ORIGINS:-}"
    save_cfg "ALLOWED_HOSTS" "${RT_ALLOWED_HOSTS:-}"
    save_cfg "REQMESH_USER" "${REQMESH_USER:-reqmesh}"
    save_cfg "REQMESH_GROUP" "${REQMESH_GROUP:-reqmesh}"

    # Dispatch to deploy script
    local mode="${CFG[DEPLOY_MODE]:-docker}"
    case "$mode" in
        docker) "$SCRIPT_DIR/deploy-docker.sh" ;;
        bare)   "$SCRIPT_DIR/deploy-bare.sh" ;;
        *)      error "Unknown deploy mode: $mode"; exit 1 ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════════════════════════
show_help() {
    cat << EOF
reqmesh install wizard

Usage:
  ./install.sh                           Interactive wizard (recommended)
  ./install.sh --non-interactive         Scripted deployment (reads RT_* env vars)
  ./install.sh --help                    This help

Interactive mode walks through:
  1. Welcome
  2. Deployment mode (Docker / bare-metal)
  3. Reverse proxy (Caddy / nginx / none)
  4. Domain & TLS configuration
  5. Security profile (personal / team / hardened)
  6. Admin credentials
  7. Optional integrations (SMTP, Git, branding)
  8. Installation paths
  9. Review & deploy

Non-interactive mode reads from these environment variables:

  REQMESH_DEPLOY_MODE  docker | bare        (default: docker)
  REQMESH_PROXY        caddy | nginx | none  (default: caddy)
  REQMESH_TLS          letsencrypt | internal | selfsigned | none
  REQMESH_DOMAIN       example.com (or blank for localhost)
  RT_PROFILE           personal | team | hardened  (default: team)
  RT_SECRET            Signing key (auto-generated if empty)
  RT_ADMIN_PASSWORD    Admin password (auto-generated if empty)
  RT_BASE_URL          https://example.com  (default: http://localhost:8000)
  RT_HOST, RT_PORT     Bind address/port
  RT_SMTP_HOST, RT_SMTP_PORT, ...  SMTP relay settings
  RT_GIT_REMOTE_URL    Git remote for backup
  RT_SEED_DEMO         true | false  (default: true)
  REQMESH_INSTALL_DIR  Install path  (default: /opt/reqmesh)
  RT_DATA_ROOT         Project data  (default: \$INSTALL_DIR/data/projects)

All RT_* settings from config.py are accepted.

EOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
main() {
    case "${1:-}" in
        --help|-h|help)
            show_help
            exit 0
            ;;
        --non-interactive|--batch)
            detect_os
            non_interactive
            exit $?
            ;;
    esac

    # Interactive wizard
    detect_os
    bootstrap_gum

    # Run the wizard to collect configuration
    source "$SCRIPT_DIR/wizard.sh"
    run_wizard

    # Deploy based on collected mode.
    #
    # Executed as a child process, not sourced. Each deploy script ends with
    # `main "$@"`, so sourcing it ran the whole deployment, and the explicit
    # `main` that followed then ran it a *second* time — re-rendering configs
    # and re-running `docker compose up` on every interactive install.
    # COLLECTED_DIR is exported by lib.sh, so the child sees the same config.
    load_cfg
    local mode="${CFG[DEPLOY_MODE]:-docker}"
    case "$mode" in
        docker) "$SCRIPT_DIR/deploy-docker.sh" ;;
        bare)   "$SCRIPT_DIR/deploy-bare.sh" ;;
        *)
            error "Unknown deployment mode: $mode"
            exit 1
            ;;
    esac
}

main "$@"
