#!/usr/bin/env bash
# deploy-docker.sh — Docker Compose deployment for reqmesh
# shellcheck disable=SC1090,SC1091
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_cfg

DEPLOY_MODE="docker"
COMPOSE_FILE="${CFG[COMPOSE_FILE]:-docker-compose.prod.yml}"
TEMPLATES="$SCRIPT_DIR/templates"

# ── Generate .env file ─────────────────────────────────────────────────────────
generate_env() {
    local env_file="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/.env"
    info "Generating $env_file..."
    mkdir -p "$(dirname "$env_file")"

    # This file holds RT_SECRET, the admin password and the SMTP password.
    # Create it 0600 *before* writing, so it is never even briefly readable —
    # `cat >` truncates but keeps the existing mode. deploy-bare.sh already
    # chmod'd its .env; the Docker path did not, and left secrets at 0644.
    # (A bare `umask 077` here would leak into every later file this script
    # writes, since umask is not scoped to the function.)
    install -m 600 /dev/null "$env_file"

    cat > "$env_file" << EOF
# reqmesh environment — generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
RT_PROFILE=${CFG[PROFILE]:-team}
RT_SECRET=${CFG[RT_SECRET]}
RT_ADMIN_PASSWORD=${CFG[ADMIN_PASSWORD]}
RT_BASE_URL=${CFG[BASE_URL]}
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
RT_SMTP_HOST=${CFG[SMTP_HOST]:-}
RT_SMTP_PORT=${CFG[SMTP_PORT]:-587}
RT_SMTP_USERNAME=${CFG[SMTP_USERNAME]:-}
RT_SMTP_PASSWORD=${CFG[SMTP_PASSWORD]:-}
RT_SMTP_FROM=${CFG[SMTP_FROM]:-reqmesh@localhost}
RT_SMTP_USE_TLS=${CFG[SMTP_USE_TLS]:-true}
RT_REPORT_COMPANY_NAME=${CFG[REPORT_COMPANY_NAME]:-}
RT_REPORT_DOCUMENT_TITLE=${CFG[REPORT_DOCUMENT_TITLE]:-}
RT_REPORT_LOGO_URL=${CFG[REPORT_LOGO_URL]:-}
RT_CORS_ORIGINS=${CFG[CORS_ORIGINS]:-[]}
RT_ALLOWED_HOSTS=${CFG[ALLOWED_HOSTS]:-}
GIT_USER_NAME=${CFG[GIT_USER_NAME]:-reqmesh}
GIT_USER_EMAIL=${CFG[GIT_USER_EMAIL]:-reqmesh@localhost}
EOF

    success "Environment written to $env_file (mode 0600)"
}

# ── Generate Docker Compose file ───────────────────────────────────────────────
generate_compose() {
    local out="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/$COMPOSE_FILE"
    info "Generating $out..."
    local tmpl="$TEMPLATES/docker-compose.prod.yml.tmpl"
    local content
    content="$(< "$tmpl")"

    local proxy="${CFG[PROXY]:-caddy}"

    if [ "$proxy" = "caddy" ]; then
        local caddy_svc='  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on:
      - reqmesh
    restart: unless-stopped'
        local caddy_vol='  caddy-data:'
        content="${content//%_CADDY_SERVICE_%/$caddy_svc}"
        content="${content//%_CADDY_VOLUME_%/$caddy_vol}"
        content="${content//%_NGINX_SERVICE_%/}"
    elif [ "$proxy" = "nginx" ]; then
        local nginx_svc='  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - nginx-certs:/etc/nginx/certs:ro
    depends_on:
      - reqmesh
    restart: unless-stopped'
        content="${content//%_NGINX_SERVICE_%/$nginx_svc}"
        content="${content//%_CADDY_SERVICE_%/}"
        content="${content//%_CADDY_VOLUME_%/}"
    else
        content="${content//%_CADDY_SERVICE_%/}"
        content="${content//%_NGINX_SERVICE_%/}"
        content="${content//%_CADDY_VOLUME_%/}"
    fi

    echo "$content" > "$out"
    success "Compose file written to $out"
}

# ── Generate Caddyfile ─────────────────────────────────────────────────────────
generate_caddyfile() {
    local out="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/Caddyfile"
    info "Generating Caddyfile..."
    render_caddyfile "reqmesh:8000" > "$out"
    success "Caddyfile written to $out"
}

# ── Generate nginx.conf ────────────────────────────────────────────────────────
generate_nginx_conf() {
    local out="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/nginx.conf"
    info "Generating nginx.conf..."
    local tmpl="$TEMPLATES/nginx.conf.tmpl"
    local content
    content="$(< "$tmpl")"

    local domain="${CFG[DOMAIN]:-localserver.reqmesh.com}"
    local tls="${CFG[TLS]:-none}"
    local port="${CFG[PORT]:-8000}"

    content="${content//\$\{DOMAIN\}/$domain}"
    content="${content//\$\{PORT\}/$port}"

    if [ "$tls" = "selfsigned" ] || [ "$tls" = "certfiles" ]; then
        content="${content//%_NGINX_LISTEN_%/    listen 443 ssl http2;}"
        if [ "$tls" = "selfsigned" ]; then
            local certdir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/certs"
            content="${content//%_NGINX_TLS_%/    ssl_certificate     $certdir/server.crt;
    ssl_certificate_key $certdir/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;}"
        else
            local certpath="${CFG[CERT_PATH]:-/etc/ssl/certs}"
            local keypath="${CFG[KEY_PATH]:-/etc/ssl/private}"
            content="${content//%_NGINX_TLS_%/    ssl_certificate     $certpath/fullchain.pem;
    ssl_certificate_key $keypath/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;}"
        fi
        # HTTP redirect
        content="${content//%_NGINX_HTTP_REDIRECT_%/server {
    listen 80;
    server_name $domain;
    return 301 https://\$host\$request_uri;
\}}"
    else
        content="${content//%_NGINX_LISTEN_%/    listen 80;}"
        content="${content//%_NGINX_TLS_%/}"
        content="${content//%_NGINX_HTTP_REDIRECT_%/}"
    fi

    echo "$content" > "$out"
    success "nginx.conf written to $out"
}

# ── Deploy ─────────────────────────────────────────────────────────────────────
deploy_docker() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    cd "$dir"

    if [ "${CFG[OFFLINE_MODE]:-false}" = "true" ]; then
        info "Offline mode — building image locally..."
        docker compose -f "$COMPOSE_FILE" build --pull=false
    fi

    info "Starting containers..."
    if [ "${CFG[BUILD_FROM_SOURCE]:-false}" = "true" ] || [ "${CFG[OFFLINE_MODE]:-false}" = "true" ]; then
        docker compose -f "$COMPOSE_FILE" up -d --build
    else
        docker compose -f "$COMPOSE_FILE" pull --quiet 2>/dev/null || true
        docker compose -f "$COMPOSE_FILE" up -d
    fi

    healthcheck "${CFG[BASE_URL]}/health" 60
    return $?
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    header "Deploying reqmesh (Docker)"

    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    mkdir -p "$dir"

    # ── Re-install check ──────────────────────────────────────────────────
    local backups=()
    local existing_files=("$dir/.env" "$dir/$COMPOSE_FILE" "$dir/Caddyfile" "$dir/nginx.conf")
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
    local port
    port="${CFG[PORT]:-8000}"
    if check_port "$port"; then
        warn "Port $port is already in use — the app may fail to bind."
    fi
    local proxy="${CFG[PROXY]:-caddy}"
    if [ "$proxy" != "none" ]; then
        if check_port 443; then warn "Port 443 (HTTPS) is already in use."; fi
        if check_port 80; then warn "Port 80 (HTTP) is already in use."; fi
    fi

    # ── Back up existing files ────────────────────────────────────────────
    local ts
    ts="$(date +%s)"
    for f in "${backups[@]}"; do
        cp "$f" "${f}.bak.${ts}" 2>/dev/null || true
    done

    generate_env
    generate_compose

    case "$proxy" in
        caddy)  generate_caddyfile ;;
        nginx)  generate_nginx_conf ;;
    esac

    deploy_docker

    # ── Access instructions ────────────────────────────────────────────────
    local cred_file
    cred_file="$(write_admin_credential)"

    echo ""
    summary_box "$cred_file" \
        "Manage:  cd $dir" \
        "         docker compose -f $COMPOSE_FILE ps" \
        "Logs:    docker compose -f $COMPOSE_FILE logs -f" \
        "Stop:    docker compose -f $COMPOSE_FILE down"
    echo ""
}

main "$@"
