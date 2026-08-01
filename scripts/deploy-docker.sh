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

    # This file holds RT_SECRET, the admin password and the SMTP password, so it
    # is created 0600 before any content is written — see write_root_file, which
    # also supplies the sudo this path previously lacked entirely.
    write_root_file "$env_file" 600 << EOF
# reqmesh environment — generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# The REQMESH_* lines below are the installer's own choices, not application
# settings. They are recorded here so that re-running install.sh can rebuild the
# same deployment instead of falling back to factory defaults.
REQMESH_VERSION=${CFG[IMAGE_TAG]:-latest}
REQMESH_DEPLOY_MODE=${CFG[DEPLOY_MODE]:-docker}
REQMESH_PROXY=${CFG[PROXY]:-caddy}
REQMESH_TLS=${CFG[TLS]:-letsencrypt}
REQMESH_DOMAIN=${CFG[DOMAIN]:-}
# The host path holding projects and accounts. Recorded because the Docker
# path's RT_DATA_ROOT is a *container* path, so without this the host location
# was not written anywhere and the next run relocated it to the default.
REQMESH_DATA_ROOT=${CFG[DATA_ROOT]:-/data/projects}
RT_PROFILE=${CFG[PROFILE]:-team}
RT_SECRET=${CFG[RT_SECRET]}
RT_ADMIN_PASSWORD=${CFG[ADMIN_PASSWORD]}
RT_BASE_URL=${CFG[BASE_URL]}
RT_DATA_HOST=$(dirname "${CFG[DATA_ROOT]:-/data/projects}")
RT_UID=$DATA_UID
RT_GID=$DATA_GID
RT_BIND=$(effective_bind)
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
        # certs is a bind mount, not the named volume this used to reference.
        # `nginx-certs` was never declared under `volumes:`, so compose rejected
        # the whole project with "refers to undefined volume nginx-certs" —
        # nginx mode could not start at all, in any configuration. A bind mount
        # also lets the certificate generated on the host actually reach nginx,
        # which an empty named volume never could.
        local nginx_svc='  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
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

    printf '%s\n' "$content" | write_root_file "$out"
    success "Compose file written to $out"
}

# ── Generate Caddyfile ─────────────────────────────────────────────────────────
generate_caddyfile() {
    local out="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/Caddyfile"
    info "Generating Caddyfile..."
    render_caddyfile "reqmesh:8000" | write_root_file "$out"
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

    # nginx runs in its own container here, so `127.0.0.1:8000` — which the
    # template carries for the bare-metal path, where it is correct — pointed
    # nginx at itself and returned 502. Reach the app by its compose service
    # name, the way the Caddyfile already did.
    content="${content//%_NGINX_UPSTREAM_%/reqmesh:8000}"
    content="${content//\$\{DOMAIN\}/$domain}"
    content="${content//\$\{PORT\}/$port}"

    if [ "$tls" = "selfsigned" ] || [ "$tls" = "certfiles" ]; then
        content="${content//%_NGINX_LISTEN_%/    listen 443 ssl http2;}"
        if [ "$tls" = "selfsigned" ]; then
            # Paths as nginx sees them inside the container. These used to be
            # host paths ($INSTALL_DIR/certs), which do not exist in the
            # container's filesystem — and nothing created the files anyway.
            local host_certdir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/certs"
            local cert_cn="${CFG[DOMAIN]:-}"
            [ -z "$cert_cn" ] || [ "$cert_cn" = "localserver.reqmesh.com" ] \
                && cert_cn="${CFG[LAN_IP]:-localhost}"
            ensure_selfsigned_cert "$host_certdir" "$cert_cn" \
                || error "nginx will not start without a certificate."
            content="${content//%_NGINX_TLS_%/    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;}"
        else
            # Operator-supplied certificates. These are host paths, and the
            # nginx container cannot see them — only ./certs is bind-mounted —
            # so copy them in rather than referencing a path that resolves to
            # nothing inside the container.
            local certpath="${CFG[CERT_PATH]:-/etc/ssl/certs}"
            local keypath="${CFG[KEY_PATH]:-/etc/ssl/private}"
            local host_certdir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}/certs"
            ensure_dir "$host_certdir"
            if ! { cp -p "$certpath/fullchain.pem" "$host_certdir/server.crt" 2>/dev/null \
                   && cp -p "$keypath/privkey.pem" "$host_certdir/server.key" 2>/dev/null; }; then
                sudo cp -p "$certpath/fullchain.pem" "$host_certdir/server.crt" \
                    || error "Could not read $certpath/fullchain.pem"
                sudo cp -p "$keypath/privkey.pem" "$host_certdir/server.key" \
                    || error "Could not read $keypath/privkey.pem"
            fi
            content="${content//%_NGINX_TLS_%/    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
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

    printf '%s\n' "$content" | write_root_file "$out"
    success "nginx.conf written to $out"
}

# ── Deploy ─────────────────────────────────────────────────────────────────────
deploy_docker() {
    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    cd "$dir"

    if [ "${CFG[OFFLINE_MODE]:-false}" = "true" ]; then
        info "Offline mode — building image locally..."
        "${DOCKER[@]}" compose -f "$COMPOSE_FILE" build --pull=false
    fi

    # --remove-orphans: turning the reverse proxy off rewrites the compose file
    # without the caddy (or nginx) service, but a plain `up -d` leaves the old
    # container running. It kept holding 80/443 and kept serving HTTPS from a
    # Caddyfile the installer no longer manages, so "disable TLS" disabled
    # nothing. The same applies to switching caddy -> nginx.
    # The compose file carries a `build:` stanza for source checkouts, so a
    # missing image makes compose try to build from INSTALL_DIR — which holds
    # only generated config, no Dockerfile. The result was
    # "failed to read dockerfile: open Dockerfile.prod: no such file or
    # directory", which says nothing about the actual problem.
    local image="ghcr.io/callumnunesvaz/reqmesh:${CFG[IMAGE_TAG]:-latest}"
    if [ "${CFG[BUILD_FROM_SOURCE]:-false}" != "true" ] \
       && [ "${CFG[OFFLINE_MODE]:-false}" != "true" ] \
       && [ ! -f "$dir/Dockerfile.prod" ]; then
        # Pulled every time, rather than accepted from cache. Skipping the pull
        # when `image inspect` found the tag locally meant a mutable tag like
        # `latest` was never refreshed: one host went on serving 0.1.4 for six
        # releases while the installer that deployed it was 0.1.10, and every
        # line of output said the deployment was healthy.
        info "Pulling $image..."
        if ! "${DOCKER[@]}" compose -f "$COMPOSE_FILE" pull reqmesh 2>&1 | tail -2; then
            # Only fatal with nothing usable locally: an air-gapped host with a
            # docker-loaded image must still deploy, as must one briefly offline.
            if "${DOCKER[@]}" image inspect "$image" >/dev/null 2>&1; then
                warn "Could not pull $image — using the copy already on this host."
                warn "  It may be older than this installer."
            else
                error "Cannot obtain the application image: $image"
                error ""
                error "It is neither pullable nor present locally, and there is no"
                error "Dockerfile in $dir to build from."
                error "  - check the tag exists:  REQMESH_VERSION=<tag>"
                error "  - or load it offline:    sudo docker load < reqmesh-<version>-image.tar.gz"
                return 1
            fi
        fi
    fi

    stop_reqmesh_services || return 1

    info "Starting containers..."
    if [ "${CFG[BUILD_FROM_SOURCE]:-false}" = "true" ] || [ "${CFG[OFFLINE_MODE]:-false}" = "true" ]; then
        "${DOCKER[@]}" compose -f "$COMPOSE_FILE" up -d --build --remove-orphans
    else
        "${DOCKER[@]}" compose -f "$COMPOSE_FILE" up -d --remove-orphans
    fi

    # The proxy's configuration is a bind-mounted file, and `up -d` only
    # recreates a container when its *service definition* changes. Rewriting
    # Caddyfile or nginx.conf does not, so a proxy container that was already
    # running kept serving the config it read at startup: switching nginx from
    # HTTP to HTTPS regenerated the config and the certificate, reported
    # success, and left port 443 closed. Restart it so the new config is read.
    local proxy_svc="${CFG[PROXY]:-caddy}"
    if [ "$proxy_svc" != "none" ]; then
        info "Restarting $proxy_svc to load the new configuration..."
        "${DOCKER[@]}" compose -f "$COMPOSE_FILE" restart "$proxy_svc" >/dev/null 2>&1 \
            || warn "Could not restart $proxy_svc — it may still be serving the previous configuration."
    fi

    # Probe the app directly, not BASE_URL. BASE_URL is the *user-facing* address:
    # it may be a domain with no DNS yet, an HTTPS endpoint whose certificate is
    # still being issued, or — with PROXY=none — a LAN address the container does
    # not bind. Any of those make a healthy install report failure. What this
    # step needs to answer is narrower: did the container come up and serve?
    healthcheck "http://127.0.0.1:${CFG[PORT]:-8000}/health" 60 || return 1
    # /health only proves the process answers. Prove someone can actually get
    # in, which is the failure this installer used to report as success.
    login_check "http://127.0.0.1:${CFG[PORT]:-8000}" "${CFG[ADMIN_PASSWORD]:-}" || true

    # State the version actually serving. A deployment several releases behind the
    # installer that placed it there looked entirely healthy, and nothing in the
    # output would have told the operator.
    local running
    running="$(curl -sf --max-time 5 "http://127.0.0.1:${CFG[PORT]:-8000}/health" 2>/dev/null \
               | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    if [ -n "$running" ]; then
        if [ "${CFG[IMAGE_TAG]:-latest}" != "latest" ] && [ "$running" != "${CFG[IMAGE_TAG]}" ]; then
            warn "Requested image ${CFG[IMAGE_TAG]} but the application reports $running."
        else
            success "Running reqmesh $running"
        fi
    fi

    # The proxy is a separate question, and a soft one — Let's Encrypt issuance
    # can outlast the installer without anything being wrong.
    if [ "${CFG[PROXY]:-caddy}" != "none" ]; then
        if curl -skf --max-time 10 "${CFG[BASE_URL]}/health" >/dev/null 2>&1; then
            success "Reachable through the proxy at ${CFG[BASE_URL]}"
        else
            warn "The app is healthy but not yet answering on ${CFG[BASE_URL]}."
            warn "If TLS is via Let's Encrypt, certificate issuance may still be in progress."
        fi
    fi
    return 0
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    header "Deploying reqmesh (Docker)"

    local dir="${CFG[INSTALL_DIR]:-$INSTALL_DIR}"
    ensure_dir "$dir"
    ensure_data_root

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
    # Fatal, not advisory. This used to warn and carry on, so the deploy went
    # ahead, rewrote .env and the compose file, and then died on "failed to bind
    # host port 127.0.0.1:8000: address already in use" — leaving the machine
    # half-converted. If the port is taken, nothing below can succeed.
    #
    # Our own container holding the port is not a conflict — replacing it in place
    # *is* the upgrade. Without this exemption every Docker-to-Docker upgrade
    # failed on the container it was about to replace.
    set_docker_cmd
    if ! port_is_ours "$port" && check_port "$port"; then
        error "Port $port is held by $(port_holder "$port") — this deployment cannot bind it."
        error "That is not part of this reqmesh install, so it is not ours to stop."
        error "Stop it, or choose a different port with RT_PORT."
        return 1
    fi
    local proxy="${CFG[PROXY]:-caddy}"
    if [ "$proxy" != "none" ]; then
        # Ours will be stopped below; anything else is not ours to touch.
        local blocked=""
        for p in 80 443; do
            port_is_ours "$p" && continue
            check_port "$p" && blocked="$blocked $p"
        done
        if [ -n "$blocked" ]; then
            for p in $blocked; do
                error "Port $p is held by $(port_holder "$p") — the $proxy proxy cannot bind it."
            done
            error "That is not part of this reqmesh install, so it is not ours to stop."
            error "Stop it, or deploy without a proxy: REQMESH_PROXY=none"
            return 1
        fi
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

    generate_env
    generate_compose

    case "$proxy" in
        caddy)  generate_caddyfile ;;
        nginx)  generate_nginx_conf ;;
    esac

    deploy_docker

    # ── Access instructions ────────────────────────────────────────────────
    local cred_file
    # Only now, with the deploy verified healthy, record what is running.
    write_install_state

    cred_file="$(write_admin_credential)"

    # Print the commands that will actually work for this user. The config is
    # root-owned 0600, so an unprivileged operator copying a bare `docker compose`
    # out of the summary hits the same "permission denied" the deploy just fixed.
    local dc="${DOCKER[*]:-docker} compose -f $COMPOSE_FILE"

    echo ""
    summary_box "$cred_file" \
        "Manage:  cd $dir" \
        "         $dc ps" \
        "Logs:    $dc logs -f" \
        "Stop:    $dc down"
    echo ""
}

main "$@"
