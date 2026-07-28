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
    if ! has_cmd python3; then
        case "$OS_ID" in
            ubuntu|debian) sudo apt-get install -y -qq python3 python3-venv python3-pip ;;
            fedora|rhel)   sudo dnf install -y python3 python3-pip ;;
            *) error "Python 3 not found. Install python3, venv, and pip."; exit 1 ;;
        esac
    fi

    # Node.js (only needed if building frontend from source, not from tarball)
    if [ "${CFG[BUILD_FROM_SOURCE]:-false}" = "true" ]; then
        if ! has_cmd node || ! has_cmd npm; then
            info "Installing Node.js 20.x..."
            case "$OS_ID" in
                ubuntu|debian)
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
        save_cfg "STATIC_DIR" "/app/frontend/dist"
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
            save_cfg "STATIC_DIR" "/app/frontend/dist"
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
    cat > "$INSTALL_DIR/.env.tmp" << EOF
# reqmesh environment — generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
RT_PROFILE=${CFG[PROFILE]:-team}
RT_SECRET=${CFG[RT_SECRET]}
RT_ADMIN_PASSWORD=${CFG[ADMIN_PASSWORD]}
RT_HOST=$host
RT_PORT=$port
RT_DATA_ROOT=$data_root
RT_STATIC_DIR=${CFG[STATIC_DIR]:-/app/frontend/dist}
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
    sudo mv "$INSTALL_DIR/.env.tmp" "$env_file"
    sudo chmod 600 "$env_file"
    sudo chown "$REQMESH_USER:$REQMESH_GROUP" "$env_file" 2>/dev/null || true

    # Tectonic cache directory
    sudo mkdir -p "$data_root/.tectonic-cache"
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
        sudo sed -i "s/\${DOMAIN}/$domain/g" /etc/nginx/sites-available/reqmesh
        sudo sed -i "s/\${PORT}/$port/g" /etc/nginx/sites-available/reqmesh
        # Default to HTTP for bare-metal
        sudo sed -i 's/%_NGINX_LISTEN_%/    listen 80;/g' /etc/nginx/sites-available/reqmesh
        sudo sed -i 's/%_NGINX_TLS_%//g' /etc/nginx/sites-available/reqmesh
        sudo sed -i 's/%_NGINX_HTTP_REDIRECT_%//g' /etc/nginx/sites-available/reqmesh
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
    local port="${CFG[PORT]:-8000}"
    if check_port "$port"; then
        warn "Port $port is already in use — the app may fail to bind."
    fi
    if [ "$proxy" != "none" ]; then
        if check_port 443; then warn "Port 443 (HTTPS) is already in use."; fi
        if check_port 80; then warn "Port 80 (HTTP) is already in use."; fi
    fi

    # ── Back up existing files ────────────────────────────────────────────
    local ts
    ts="$(date +%s)"
    for f in "${backups[@]}"; do
        sudo cp "$f" "${f}.bak.${ts}" 2>/dev/null || true
    done

    install_deps
    install_app
    install_python_deps
    generate_configs
    install_service
    start_service

    # ── Access instructions ────────────────────────────────────────────────
    local cred_file
    cred_file="$(write_admin_credential)"

    echo ""
    summary_box "$cred_file" \
        "Manage:  systemctl {start,stop,restart,status} reqmesh" \
        "Logs:    journalctl -u reqmesh -f" \
        "Config:  $INSTALL_DIR/.env"
    echo ""
}

main "$@"
