#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/reqmesh}"
DATA_DIR="${DATA_DIR:-$INSTALL_DIR/data/projects}"
HOSTNAME="${REQMESH_HOSTNAME:-}"
NGINX="${NGINX:-yes}"
VERBOSE="${VERBOSE:-0}"

log()  { echo "==>" "$@"; }
vlog() { if [ "$VERBOSE" = "1" ]; then echo "    " "$@"; fi; }

fail() { echo "error:" "$@" >&2; exit 1; }

gen_secret() { openssl rand -hex 32 2>/dev/null || python3 -c "import secrets;print(secrets.token_hex(32))"; }
gen_pw()     { python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16)))"; }

UUID=$(id -u 2>/dev/null || echo 0)
if [ "$UUID" != "0" ]; then
  fail "Run this script as root (or with sudo). Example: sudo ./install-ubuntu-24.04.sh"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IS_BUNDLE=0
if [ -f "$SCRIPT_DIR/../VERSION" ] && [ -f "$SCRIPT_DIR/../backend/requirements.txt" ]; then
  IS_BUNDLE=1
  REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  vlog "Bundle detected at $REPO_DIR"
fi

log "reqmesh installer — Ubuntu 24.04 LTS"
log ""
log "This script installs reqmesh on a fresh Ubuntu 24.04 server."
log "On an existing server it may overwrite or conflict with prior web setups."
log "Continuing in 5 seconds… (Ctrl-C to cancel)"
sleep 5

INSTALL_DEPS=1
if command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import venv' 2>/dev/null && \
   command -v git >/dev/null 2>&1; then
  vlog "Core dependencies already present — skipping system package install"
  INSTALL_DEPS=0
fi

if [ "$INSTALL_DEPS" = "1" ]; then
  log "Installing system packages (python3, nginx, git, weasyprint deps)"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    git curl openssl \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    fonts-dejavu-core libcairo2 libgdk-pixbuf2.0-0 \
    libffi-dev libssl-dev
fi

if [ "$NGINX" = "yes" ] && [ "$INSTALL_DEPS" = "1" ]; then
  apt-get install -y -qq nginx
fi

log "Setting up reqmesh in $INSTALL_DIR"

if [ "$IS_BUNDLE" = "1" ]; then
  log "Copying from bundle at $REPO_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  if [ "$REPO_DIR" != "$INSTALL_DIR" ]; then
    rsync -a "$REPO_DIR"/ "$INSTALL_DIR"/ \
      --exclude '.git' --exclude 'dist' --exclude 'node_modules' \
      --exclude '__pycache__' --exclude '.venv' \
      --exclude 'backend/.venv' --exclude 'frontend/node_modules'
  fi
else
  log "Cloning reqmesh from GitHub"
  git clone https://github.com/CallumNunesVaz/reqmesh.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

VENV="$INSTALL_DIR/.venv"
if ! python3 -c 'import venv' 2>/dev/null; then
  apt-get install -y -qq python3-venv
fi
log "Creating Python virtual environment"
python3 -m venv "$VENV"
. "$VENV/bin/activate"
pip install --quiet --upgrade pip

log "Installing Python dependencies"
pip install --quiet -r backend/requirements.txt 2>/dev/null || pip install -r backend/requirements.txt

if [ -d frontend ] && [ -f frontend/package.json ]; then
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    log "Building frontend"
    (cd frontend && npm ci --silent 2>/dev/null || npm ci && npm run build)
  elif [ -f frontend/dist/index.html ]; then
    vlog "Pre-built frontend found — skipping build"
  else
    vlog "Node.js not available; frontend will need to be built separately"
    vlog "Install Node.js 20+ and run: cd $INSTALL_DIR/frontend && npm ci && npm run build"
  fi
fi

log "Generating secrets"
RT_SECRET=$(gen_secret)
RT_ADMIN_PASSWORD=$(gen_pw)
RAND_PORT=$((8000 + RANDOM % 1000))

mkdir -p "$DATA_DIR"
if [ -d "$INSTALL_DIR/data/projects" ] && [ -z "$(ls -A "$DATA_DIR" 2>/dev/null 2>&1 || true)" ]; then
  log "Seeding bundled example project"
  cp -a "$INSTALL_DIR/data/projects"/. "$DATA_DIR"/ 2>/dev/null || true
fi

if [ ! -f "$INSTALL_DIR/.env" ]; then
  cat > "$INSTALL_DIR/.env" <<ENV
RT_SECRET=$RT_SECRET
RT_ADMIN_PASSWORD=$RT_ADMIN_PASSWORD
RT_STATIC_DIR=$INSTALL_DIR/frontend/dist
RT_DATA_ROOT=$DATA_DIR
RT_HOST=127.0.0.1
RT_PORT=8000
RT_SEED_DEMO=true
RT_GIT_AUTOCOMMIT=true
ENV
  log "Wrote $INSTALL_DIR/.env"
else
  vlog ".env already exists — leaving unchanged"
fi

log "Creating systemd service"
cat > /etc/systemd/system/reqmesh.service <<UNIT
[Unit]
Description=reqmesh requirements management
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR/backend
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable reqmesh.service
systemctl start reqmesh.service
log "reqmesh service started — listening on 127.0.0.1:8000"

if [ "$NGINX" = "yes" ]; then
  SITE_HOSTNAME="${REQMESH_HOSTNAME:-_}"
  SITE_FILE="/etc/nginx/sites-available/reqmesh"
  if [ ! -f "$SITE_FILE" ]; then
    cat > "$SITE_FILE" <<NGINX_SITE
server {
    listen 80;
    server_name $SITE_HOSTNAME;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        chunked_transfer_encoding off;
    }
}
NGINX_SITE

    if [ ! -e "/etc/nginx/sites-enabled/reqmesh" ]; then
      ln -sf "$SITE_FILE" /etc/nginx/sites-enabled/reqmesh
    fi

    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl restart nginx
    log "nginx configured — proxying 0.0.0.0:80 → reqmesh (127.0.0.1:8000)"
  else
    vlog "nginx site config already exists at $SITE_FILE — leaving unchanged"
  fi
fi

log ""
log "reqmesh installed successfully!"
log "──────────────────────────────────────────"
log "  Admin URL:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '<server-ip>')/"
log "  Admin user: admin"
log "  Password:   $RT_ADMIN_PASSWORD"
log ""
log "  Service:    systemctl status reqmesh"
log "  Logs:       journalctl -u reqmesh -f"
log "  Config:     $INSTALL_DIR/.env"
log "──────────────────────────────────────────"
log ""
log "Change the admin password immediately after logging in."
if [ "$NGINX" != "yes" ]; then
  log "nginx was skipped — reqmesh listens on 127.0.0.1:8000 only."
  log "To serve over the network, install nginx or set RT_HOST=0.0.0.0 in .env (not recommended)."
fi
log ""
log "For TLS, add ssl_certificate directives to the nginx site config and run: nginx -t && systemctl reload nginx"
