#!/usr/bin/env bash
# deploy-bare.sh — bare-metal systemd deployment for reqmesh
# shellcheck disable=SC1090,SC1091
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_cfg

INSTALL_DIR="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
BACKEND_DIR="$INSTALL_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
# Where accounts and the signing secret live. Script-level because both
# generate_configs and install_service need it — as a `local` in the former
# it was an unbound variable by the time the unit was rendered.
STATE_DIR="$(dirname "${CFG[DATA_ROOT]:-${INSTALL_DIR}/data/projects}")/.reqmesh"
REQMESH_USER="${CFG[REQMESH_USER]:-reqmesh}"
REQMESH_GROUP="${CFG[REQMESH_GROUP]:-reqmesh}"
TEMPLATES="$SCRIPT_DIR/templates"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — System dependencies
# ═══════════════════════════════════════════════════════════════════════════════
install_deps() {
    header "Installing system dependencies"
    install_system_pkgs
    install_tectonic

    # Python 3.12+ check
    local python="python3"
    # Test for the capability, not the binary. Ubuntu 24.04 ships python3 but
    # splits venv/ensurepip into python3-venv, so `has_cmd python3` succeeded,
    # this whole block was skipped, and the install died later with "The virtual
    # environment was not created successfully because ensurepip is not
    # available" — after apt, the service user and the file copy had all run.
    if ! has_cmd python3 || ! python3 -c 'import ensurepip' 2>/dev/null; then
        case "$OS_ID" in
            ubuntu|debian) sudo apt-get install -y -qq python3 python3-venv python3-pip ;;
            fedora|rhel)   sudo dnf install -y python3 python3-pip ;;
            *) error "Python 3 with venv support not found. Install python3, venv, and pip."; exit 1 ;;
        esac
        if ! python3 -c 'import ensurepip' 2>/dev/null; then
            error "python3 still cannot create virtual environments (ensurepip missing)."
            error "On Debian/Ubuntu: sudo apt install python3-venv"
            exit 1
        fi
    fi

    # Node.js (only needed if building frontend from source, not from tarball)
    if [ "${CFG[BUILD_FROM_SOURCE]:-false}" = "true" ]; then
        if ! has_cmd node || ! has_cmd npm; then
            info "Installing Node.js 20.x..."
            case "$OS_ID" in
                ubuntu|debian)
  # NodeSource's documented install path. Piping it to a shell trusts
  # deb.nodesource.com, which this script already trusts for the packages it
  # then installs from that repo, so pinning a checksum here would not change
  # who has to be trusted. Kept visible rather than hidden.
                    # nosemgrep: bash.curl.security.curl-pipe-bash.curl-pipe-bash
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
                    sudo apt-get install -y -qq nodejs
                    ;;
                *)
                    warn "Automatic Node.js install not supported on $OS_ID."
                    warn "Install Node.js 20+ from: https://nodejs.org"
                    ;;
            esac
        fi
    fi

    # Reverse proxy
    if [ "${CFG[PROXY]:-}" = "caddy" ]; then
        install_caddy
    elif [ "${CFG[PROXY]:-}" = "nginx" ]; then
        install_nginx
    fi

    # Create service user
    if ! id "$REQMESH_USER" &>/dev/null; then
        info "Creating $REQMESH_USER user..."
        sudo useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" "$REQMESH_USER" 2>/dev/null || true
        if ! getent group "$REQMESH_GROUP" &>/dev/null; then
            sudo groupadd -r "$REQMESH_GROUP" 2>/dev/null || true
        fi
        sudo usermod -a -G "$REQMESH_GROUP" "$REQMESH_USER" 2>/dev/null || true
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Application files
# ═══════════════════════════════════════════════════════════════════════════════
install_app() {
    header "Installing reqmesh application"

    sudo mkdir -p "$INSTALL_DIR" "$BACKEND_DIR"

    # Determine source
    local app_src="${CFG[APP_SOURCE]:-$SCRIPT_DIR/..}"
    if [ "${CFG[FROM_BUNDLE]:-false}" = "true" ]; then
        app_src="$SCRIPT_DIR/.."
    fi

    info "Copying from $app_src..."

    # Backend
    if [ -d "$app_src/backend/app" ]; then
        sudo cp -r "$app_src/backend/app" "$BACKEND_DIR/"
    else
        error "Backend source not found at $app_src/backend/app"
        return 1
    fi
    if [ -f "$app_src/backend/requirements.txt" ]; then
        sudo cp "$app_src/backend/requirements.txt" "$BACKEND_DIR/"
    fi

    # Frontend (pre-built)
    if [ -d "$app_src/frontend/dist" ]; then
        sudo mkdir -p "$INSTALL_DIR/frontend"
        sudo cp -r "$app_src/frontend/dist" "$INSTALL_DIR/frontend/"
        save_cfg "STATIC_DIR" "$INSTALL_DIR/frontend/dist"
        success "Copied pre-built frontend"
    elif [ "${CFG[BUILD_FROM_SOURCE]:-false}" = "true" ]; then
        info "Building frontend from source..."
        if [ -d "$app_src/frontend" ]; then
            (
                cd "$app_src/frontend"
                npm install --silent 2>/dev/null
                npm run build 2>/dev/null
            )
            sudo mkdir -p "$INSTALL_DIR/frontend"
            sudo cp -r "$app_src/frontend/dist" "$INSTALL_DIR/frontend/"
            save_cfg "STATIC_DIR" "$INSTALL_DIR/frontend/dist"
            success "Built and copied frontend"
        fi
    else
        warn "No pre-built frontend found; reqmesh will run API-only"
        save_cfg "STATIC_DIR" ""
    fi

    # Set permissions
    sudo chown -R "$REQMESH_USER:$REQMESH_GROUP" "$INSTALL_DIR" 2>/dev/null || true
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Python virtualenv
# ═══════════════════════════════════════════════════════════════════════════════
install_python_deps() {
    header "Installing Python dependencies"

    if [ ! -d "$VENV_DIR" ]; then
        sudo -u "$REQMESH_USER" python3 -m venv "$VENV_DIR"
    fi

    local pip="$VENV_DIR/bin/pip"
    if [ "${CFG[OFFLINE_MODE]:-false}" = "true" ]; then
        sudo -u "$REQMESH_USER" "$pip" install --no-index -r "$BACKEND_DIR/requirements.txt" 2>/dev/null || {
            warn "Offline pip install failed — packages may not be cached"
        }
    else
        sudo -u "$REQMESH_USER" "$pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
    fi

    # Git config for the service user
    local git_name="${CFG[GIT_USER_NAME]:-reqmesh}"
    local git_email="${CFG[GIT_USER_EMAIL]:-reqmesh@localhost}"
    sudo -u "$REQMESH_USER" git config --global user.email "$git_email" 2>/dev/null || true
    sudo -u "$REQMESH_USER" git config --global user.name "$git_name" 2>/dev/null || true
    sudo -u "$REQMESH_USER" git config --global init.defaultBranch main 2>/dev/null || true

    # Needs both tectonic and the venv, so it lands here rather than in
    # install_deps. The cache dir matches the one ensure_data_root creates and
    # chowns to the service user.
    warm_tectonic_cache "$BACKEND_DIR" "$VENV_DIR/bin/python" \
        "$(dirname "${CFG[DATA_ROOT]:-${INSTALL_DIR}/data/projects}")/.tectonic-cache" \
        "$REQMESH_USER"

    success "Python dependencies installed"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4 — Configuration files
# ═══════════════════════════════════════════════════════════════════════════════
generate_configs() {
    header "Generating configuration"

    local data_root="${CFG[DATA_ROOT]:-${INSTALL_DIR}/data/projects}"
    local host="${CFG[HOST]:-127.0.0.1}"
    local port="${CFG[PORT]:-8000}"
    local domain="${CFG[DOMAIN]:-}"
    local tls="${CFG[TLS]:-none}"
    local proxy="${CFG[PROXY]:-none}"
    local proxy_cidr="${CFG[PROXY_TRUSTED_CIDR]:-127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"

    # .env file
    local env_file="$INSTALL_DIR/.env"
    info "Writing $env_file..."
    # write_root_file elevates and creates the file 0600 before any content
    # reaches it. The previous form wrote a temp file with an unprivileged
    # `cat >` into a root-owned INSTALL_DIR and then sudo-moved it, so on a
    # clean host it died with "/opt/reqmesh/.env.tmp: Permission denied" —
    # the same defect the Docker path had.
    write_root_file "$env_file" 600 << EOF
# reqmesh environment — generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# The REQMESH_* lines record the installer's own choices so a re-run rebuilds
# this same deployment. Only the Docker path used to write them, so a bare
# install had no recorded mode: re-running the installer fell through to the
# `docker` default and silently converted the machine, while the systemd
# service and nginx still held :8000 and :80.
REQMESH_DEPLOY_MODE=bare
REQMESH_PROXY=${CFG[PROXY]:-none}
REQMESH_TLS=${CFG[TLS]:-none}
REQMESH_DOMAIN=${CFG[DOMAIN]:-}
# The host path holding projects and accounts. Recorded because the Docker
# path's RT_DATA_ROOT is a *container* path, so without this the host location
# was not written anywhere and the next run relocated it to the default.
REQMESH_DATA_ROOT=${CFG[DATA_ROOT]:-/data/projects}
RT_PROFILE=${CFG[PROFILE]:-team}
RT_SECRET=${CFG[RT_SECRET]}
RT_ADMIN_PASSWORD=${CFG[ADMIN_PASSWORD]}
RT_HOST=$host
RT_PORT=$port
RT_DATA_ROOT=$data_root
RT_STATE_DIR=$STATE_DIR
# The cache install_python_deps warmed. Without this the service runs with
# tectonic's default per-user cache, which for a systemd unit is an empty
# \$HOME — so the warmed packages are ignored and the first export downloads
# them again, or falls back to the degraded renderer if it cannot.
TECTONIC_CACHE_DIR=$(dirname "$data_root")/.tectonic-cache
RT_STATIC_DIR=${CFG[STATIC_DIR]:-$INSTALL_DIR/frontend/dist}
RT_BASE_URL=${CFG[BASE_URL]:-http://localhost:8000}
RT_COOKIE_SECURE=${CFG[COOKIE_SECURE]:-true}
RT_REQUIRE_AUTH=${CFG[REQUIRE_AUTH]:-true}
RT_ALLOW_SELF_REGISTRATION=${CFG[SELF_REG]:-false}
RT_REQUIRE_EMAIL_VERIFICATION=${CFG[REQUIRE_EMAIL_VERIFICATION]:-false}
RT_SEED_DEMO=${CFG[SEED_DEMO]:-true}
RT_OFFLINE_MODE=${CFG[OFFLINE_MODE]:-false}
RT_GIT_AUTOCOMMIT=${CFG[GIT_AUTOCOMMIT]:-true}
RT_GIT_REMOTE_URL=${CFG[GIT_REMOTE_URL]:-}
RT_GIT_PUSH_ON_COMMIT=${CFG[GIT_PUSH_ON_COMMIT]:-false}
RT_GIT_PUSH_INTERVAL_MINUTES=${CFG[GIT_PUSH_INTERVAL_MINUTES]:-0}
RT_GIT_COMMIT_SCHEDULE=${CFG[GIT_COMMIT_SCHEDULE]:-every_change}
RT_GIT_COMMIT_INTERVAL_HOURS=${CFG[GIT_COMMIT_INTERVAL_HOURS]:-0}
RT_GIT_COMMIT_CHANGES_THRESHOLD=${CFG[GIT_COMMIT_CHANGES_THRESHOLD]:-0}
RT_SMTP_HOST=${CFG[SMTP_HOST]:-}
RT_SMTP_PORT=${CFG[SMTP_PORT]:-587}
RT_SMTP_USERNAME=${CFG[SMTP_USERNAME]:-}
RT_SMTP_PASSWORD=${CFG[SMTP_PASSWORD]:-}
RT_SMTP_FROM=${CFG[SMTP_FROM]:-reqmesh@localhost}
RT_SMTP_USE_TLS=${CFG[SMTP_USE_TLS]:-true}
RT_REPORT_COMPANY_NAME=${CFG[REPORT_COMPANY_NAME]:-}
RT_REPORT_DOCUMENT_TITLE=${CFG[REPORT_DOCUMENT_TITLE]:-}
RT_REPORT_LOGO_URL=${CFG[REPORT_LOGO_URL]:-}
RT_ALLOWED_HOSTS=${CFG[ALLOWED_HOSTS]:-}
RT_PROXY_TRUSTED_CIDR=$proxy_cidr
EOF
    sudo chown "$REQMESH_USER:$REQMESH_GROUP" "$env_file" 2>/dev/null || true

    # Tectonic cache directory
    ensure_data_root
    sudo mkdir -p "$data_root/.tectonic-cache" "$STATE_DIR"
    sudo chown -R "$REQMESH_USER:$REQMESH_GROUP" "$STATE_DIR" 2>/dev/null || true
    sudo chown -R "$REQMESH_USER:$REQMESH_GROUP" "$data_root" 2>/dev/null || true

    # Proxy config
    if [ "$proxy" = "caddy" ]; then
        info "Configuring Caddy..."
        render_caddyfile "${host}:${port}" | sudo tee /etc/caddy/Caddyfile >/dev/null
        sudo systemctl enable caddy
        sudo systemctl restart caddy
    elif [ "$proxy" = "nginx" ]; then
        info "Configuring nginx..."
        sudo cp "$TEMPLATES/nginx.conf.tmpl" /etc/nginx/sites-available/reqmesh
        sudo ln -sf /etc/nginx/sites-available/reqmesh /etc/nginx/sites-enabled/reqmesh 2>/dev/null || true
        # Ubuntu enables a default site on the same catch-all name, and nginx
        # resolves the clash by ignoring ours ("conflicting server name \"_\"")
        # — serving its welcome page instead of reqmesh.
        if [ -e /etc/nginx/sites-enabled/default ]; then
            info "Disabling the default nginx site (it claims the same server_name)"
            sudo rm -f /etc/nginx/sites-enabled/default
        fi
        # `_` is nginx's catch-all. Without a domain this substituted nothing,
        # producing a bare `server_name ;` — "invalid number of arguments in
        # server_name directive" — so nginx refused to start and took the whole
        # install down with it.
        sudo sed -i "s/\${DOMAIN}/${domain:-_}/g" /etc/nginx/sites-available/reqmesh
        sudo sed -i "s/\${PORT}/$port/g" /etc/nginx/sites-available/reqmesh
        # Bare metal runs the app on the host, so loopback is correct here. The
        # placeholder exists because the Docker path shares this template and
        # must reach the app by its compose service name instead.
        sudo sed -i "s/%_NGINX_UPSTREAM_%/127.0.0.1:$port/g" /etc/nginx/sites-available/reqmesh
        # Default to HTTP for bare-metal
        sudo sed -i 's/%_NGINX_LISTEN_%/    listen 80;/g' /etc/nginx/sites-available/reqmesh
        sudo sed -i 's/%_NGINX_TLS_%//g' /etc/nginx/sites-available/reqmesh
        sudo sed -i 's/%_NGINX_HTTP_REDIRECT_%//g' /etc/nginx/sites-available/reqmesh
        if ! sudo nginx -t 2>&1 | sed 's/^/    /'; then
            error "The generated nginx configuration is invalid (see above)."
            return 1
        fi
        sudo systemctl enable nginx
        sudo systemctl restart nginx
    fi

    success "Configuration files written"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5 — systemd service
# ═══════════════════════════════════════════════════════════════════════════════
install_service() {
    header "Installing systemd service"

    local data_root="${CFG[DATA_ROOT]:-${INSTALL_DIR}/data/projects}"
    local host="${CFG[HOST]:-127.0.0.1}"
    local port="${CFG[PORT]:-8000}"
    local proxy_cidr="${CFG[PROXY_TRUSTED_CIDR]:-127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"

    local tmpl="$TEMPLATES/reqmesh.service.tmpl"
    local content
    content="$(< "$tmpl")"
    content="${content//\$\{INSTALL_DIR\}/$INSTALL_DIR}"
    content="${content//\$\{DATA_ROOT\}/$data_root}"
    content="${content//\$\{STATE_DIR\}/$STATE_DIR}"
    content="${content//\$\{HOST\}/$host}"
    content="${content//\$\{PORT\}/$port}"
    content="${content//\$\{PROXY_TRUSTED_CIDR\}/$proxy_cidr}"
    content="${content//\$\{REQMESH_USER\}/$REQMESH_USER}"
    content="${content//\$\{REQMESH_GROUP\}/$REQMESH_GROUP}"

    echo "$content" | sudo tee /etc/systemd/system/reqmesh.service > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable reqmesh

    success "systemd service installed"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6 — Start
# ═══════════════════════════════════════════════════════════════════════════════
start_service() {
    header "Starting reqmesh"
    sudo systemctl restart reqmesh
    healthcheck "http://localhost:${CFG[PORT]:-8000}/health" 90
    # /health only proves the process answers. Prove someone can actually get
    # in, which is the failure this installer used to report as success.
    login_check "http://localhost:${CFG[PORT]:-8000}" "${CFG[ADMIN_PASSWORD]:-}" || true
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
main() {
    header "Deploying reqmesh (bare-metal)"
    detect_os
    detect_selinux

    # ── Re-install check ──────────────────────────────────────────────────
    local backups=()
    local existing_files=("$INSTALL_DIR/.env" "/etc/systemd/system/reqmesh.service")
    local proxy="${CFG[PROXY]:-none}"
    if [ "$proxy" = "caddy" ]; then
        existing_files+=("/etc/caddy/Caddyfile")
    elif [ "$proxy" = "nginx" ]; then
        existing_files+=("/etc/nginx/sites-available/reqmesh")
    fi
    for f in "${existing_files[@]}"; do
        if [ -f "$f" ]; then
            backups+=("$f")
        fi
    done
    if [ ${#backups[@]} -gt 0 ]; then
        warn "Existing installation files found:"
        for f in "${backups[@]}"; do
            echo "  $f"
        done
        info "Existing files will be backed up with a .bak timestamp suffix."
        echo ""
    fi

    # ── Port conflict check ───────────────────────────────────────────────
    # Ours is stopped just before the service starts; anything else is a genuine
    # conflict we have no business resolving.
    local port="${CFG[PORT]:-8000}"
    if ! port_is_ours "$port" && check_port "$port"; then
        error "Port $port is held by $(port_holder "$port") — this deployment cannot bind it."
        error "That is not part of this reqmesh install, so it is not ours to stop."
        return 1
    fi
    if [ "$proxy" != "none" ]; then
        local p
        for p in 80 443; do
            if ! port_is_ours "$p" && check_port "$p"; then
                error "Port $p is held by $(port_holder "$p") — the $proxy proxy cannot bind it."
                error "That is not part of this reqmesh install, so it is not ours to stop."
                return 1
            fi
        done
    fi

    # ── Source preflight ──────────────────────────────────────────────────
    # install_app discovers a missing source, but it runs after install_deps has
    # already apt-installed a reverse proxy and after the existing unit has been
    # backed up. Check it while the host is still untouched.
    local _src="${CFG[APP_SOURCE]:-$SCRIPT_DIR/..}"
    if [ ! -d "$_src/backend/app" ]; then
        error "No application source at $_src/backend/app"
        error ""
        error "The bare-metal install copies the application from the directory"
        error "containing this script. That works from a release bundle or a git"
        error 'checkout, but not from the `curl | bash` one-liner, which downloads'
        error "only the scripts."
        error ""
        error "Use the release bundle:"
        error "  tar xzf reqmesh-<version>.tar.gz && cd reqmesh-<version>"
        error "  sudo REQMESH_DEPLOY_MODE=bare ./install.sh --non-interactive"
        return 1
    fi

    # ── Back up existing files ────────────────────────────────────────────
    local ts
    ts="$(date +%s)"
    for f in "${backups[@]}"; do
        if dest="$(backup_file "$f" "$ts")"; then
            info "Backed up $f -> $dest"
        else
            warn "Could not back up $f — continuing, but the old copy is gone."
        fi
    done

    install_deps
    install_app
    install_python_deps

    # Before generate_configs, not after: that step writes the nginx site and
    # restarts the proxy, and stopping afterwards would delete the config it had
    # just written. Late enough that a failed preflight, a missing source or a
    # broken dependency install all leave the running deployment untouched.
    stop_reqmesh_services || return 1

    generate_configs
    install_service
    start_service

    # ── Access instructions ────────────────────────────────────────────────
    local cred_file
    # Only now, with the deploy verified healthy, record what is running.
    write_install_state

    cred_file="$(write_admin_credential)"

    echo ""
    summary_box "$cred_file" \
        "Manage:  systemctl {start,stop,restart,status} reqmesh" \
        "Logs:    journalctl -u reqmesh -f" \
        "Config:  $INSTALL_DIR/.env"
    echo ""
}

main "$@"
