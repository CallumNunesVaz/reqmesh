# reqmesh — Server Deployment

Below are the available installation options depending on your setup. The
install process requires some knowledge of Linux server administration.
reqmesh is a Python application backed by the filesystem — no database
server is needed.

- [Requirements](#requirements)
- [Ubuntu 24.04 Script](#ubuntu-2404) – one command on a fresh server
- [Manual Installation](#manual) – Python venv + systemd
- [Docker Containers](#docker) – Docker Compose with optional TLS
- [Configuration Guide](#configuration)

---

## Requirements

| Component | Minimum | Notes |
|-----------|---------|-------|
| **Python** | 3.11+ | Includes `venv` and `pip` |
| **Node.js** | 20+ | Only needed to build the frontend. Pre-built bundles include `frontend/dist` |
| **Git** | 2.x | For project versioning and in-app change history |
| **nginx / Caddy** | Any recent | Reverse proxy for TLS and SSE streaming |
| **pango / harfbuzz** | – | System libraries for PDF export. Part of the script install |

No database or message broker is required — projects are plain YAML files on
disk, and real-time collaboration uses in-process SSE.

---

## Ubuntu 24.04 Script

A script is provided to install reqmesh on a fresh instance of Ubuntu 24.04.
**This script is ONLY FOR A FRESH OS** — it installs nginx and Python system
packages and could overwrite an existing web setup. It also does not configure
TLS or email; you must do those separately.

The script sets up a Python virtual environment in `/opt/reqmesh`, builds the
frontend, generates JWT secrets and an admin password, creates a `reqmesh`
systemd service, and configures nginx as a reverse proxy on port 80.

#### Running the Script

```bash
# Download the script
wget https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/main/scripts/install-ubuntu-24.04.sh

# Make it executable
chmod +x install-ubuntu-24.04.sh

# Run with root privileges
sudo ./install-ubuntu-24.04.sh
```

The admin password is printed at the end of the script. Change it immediately
after logging in at `http://<server-ip>/`.

#### Customising the Install

Set these environment variables before running the script:

| Variable | Default | Effect |
|----------|---------|--------|
| `INSTALL_DIR` | `/opt/reqmesh` | Where the application lives |
| `DATA_DIR` | `$INSTALL_DIR/data/projects` | Where project YAML files are stored |
| `NGINX` | `yes` | Set to `no` to skip nginx setup |
| `REQMESH_HOSTNAME` | auto | Domain or IP for nginx `server_name` |

---

## Manual Installation

Ensure the [requirements](#requirements) are met before installing.

1.  **Clone the repository**
    ```bash
    git clone https://github.com/CallumNunesVaz/reqmesh.git /opt/reqmesh
    cd /opt/reqmesh
    ```

2.  **Create a virtual environment and install dependencies**
    ```bash
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r backend/requirements.txt
    ```

3.  **Build the frontend**
    ```bash
    cd frontend && npm ci && npm run build && cd ..
    ```

4.  **Generate secrets**
    ```bash
    openssl rand -hex 32  > .rt-secret
    openssl rand -base64 12 > .rt-admin-pw
    ```

5.  **Create a data directory and seed the demo project**
    ```bash
    mkdir -p data/projects
    python3 seed_cessna.py --data-root data/projects
    ```

6.  **Start the server**
    ```bash
    cd backend
    export RT_STATIC_DIR=$(realpath ../frontend/dist)
    export RT_DATA_ROOT=$(realpath ../data/projects)
    export RT_SECRET=$(cat ../.rt-secret)
    export RT_ADMIN_PASSWORD=$(cat ../.rt-admin-pw)

    uvicorn app.main:app --host 127.0.0.1 --port 8000
    ```

7.  **Set up a reverse proxy**

    Install nginx and create a site config at `/etc/nginx/sites-available/reqmesh`:
    ```nginx
    server {
        listen 80;
        server_name your-domain.com;

        client_max_body_size 50M;

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 86400s;
            chunked_transfer_encoding off;
        }
    }
    ```
    ```bash
    ln -sf /etc/nginx/sites-available/reqmesh /etc/nginx/sites-enabled/reqmesh
    nginx -t && systemctl restart nginx
    ```

8.  **Create a systemd service** (optional, for autostart)

    Create `/etc/systemd/system/reqmesh.service`:
    ```ini
    [Unit]
    Description=reqmesh requirements management
    After=network.target

    [Service]
    Type=simple
    User=root
    WorkingDirectory=/opt/reqmesh/backend
    EnvironmentFile=/opt/reqmesh/.env
    ExecStart=/opt/reqmesh/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    ```
    ```bash
    systemctl daemon-reload
    systemctl enable --now reqmesh
    ```

9.  **Done.** Log in at `http://<server-ip>/` as `admin` with the generated password.

---

## Docker Containers

A production-ready Docker Compose stack is included. It runs reqmesh as a
single container serving both the API and the built frontend (no separate
Vite dev server, no CORS configuration needed).

#### Quick Start

```bash
git clone https://github.com/CallumNunesVaz/reqmesh.git
cd reqmesh

RT_SECRET=$(openssl rand -hex 32) \
RT_ADMIN_PASSWORD=$(openssl rand -base64 12) \
  docker compose -f docker-compose.prod.yml up -d
```

reqmesh is now listening on `http://localhost:8000`. Log in with
`admin` / the generated password.

#### Making It Reachable on the Network

Set `RT_BIND=0.0.0.0` to expose port 8000 to all interfaces:
```bash
RT_BIND=0.0.0.0 RT_SECRET=... RT_ADMIN_PASSWORD=... \
  docker compose -f docker-compose.prod.yml up -d
```

#### Adding TLS

Uncomment the Caddy service in `docker-compose.prod.yml` and comment out the
reqmesh service's `ports:` block. Edit the `Caddyfile` with your hostname.
Caddy auto-provisions Let's Encrypt for public domains; for LAN-only domains
use `tls internal`.

#### Self-Updating (Optional)

Enable the updater sidecar by adding the `self-update` profile:
```bash
docker compose -f docker-compose.prod.yml --profile self-update up -d
```

The sidecar holds the Docker socket (the app container does not) and
orchestrates image pulls and container recreation when an admin clicks
"Update" in the app UI.

#### Offline / Air-Gapped

Set `RT_OFFLINE_MODE=true`. Pre-build or pull the image on a connected
machine and transfer it:
```bash
docker save ghcr.io/callumnunesvaz/reqmesh:latest | gzip > reqmesh.tar.gz
scp reqmesh.tar.gz airgap-server:/opt/reqmesh/
# On the air-gapped server:
gunzip -c reqmesh.tar.gz | docker load
RT_OFFLINE_MODE=true docker compose -f docker-compose.prod.yml up -d
```

---

## Configuration Guide

### TLS (HTTPS)

**With Caddy** (Docker): Edit `Caddyfile`, uncomment the Caddy service in
`docker-compose.prod.yml`. For LAN domains use `tls internal`; for public
domains Caddy provisions Let's Encrypt automatically.

**With nginx** (bare-metal): Obtain certificates via Let's Encrypt
(`certbot`) or `mkcert` for local domains, then add `ssl_certificate`
directives to your nginx site config.

**Important for SSE**: The reverse proxy MUST disable response buffering
and set a long read timeout, otherwise real-time updates will not work.
- nginx: `proxy_buffering off; proxy_read_timeout 86400s;`
- Caddy: `flush_interval -1`

### Email Notifications

reqmesh can send email for requirement reviews, change requests, risks,
decisions, and comments. Set these in the environment:

| Variable | Example | Notes |
|----------|---------|-------|
| `RT_SMTP_HOST` | `smtp.gmail.com` | Empty to disable |
| `RT_SMTP_PORT` | `587` | |
| `RT_SMTP_USERNAME` | `reqmesh@example.com` | |
| `RT_SMTP_PASSWORD` | `your-app-password` | |
| `RT_SMTP_FROM` | `reqmesh@example.com` | |
| `RT_BASE_URL` | `https://reqmesh.example.com` | Used for links in emails |

For testing without a real SMTP server:
```bash
docker run -d --name mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit
RT_SMTP_HOST=localhost RT_SMTP_PORT=1025 RT_SMTP_USE_TLS=false \
  docker compose -f docker-compose.prod.yml up -d
```
Open `http://localhost:8025` to see captured emails.

### Git Remote Push

reqmesh can push every change to an external Git repository for off-server
backup and an audit trail. Configure the remote via Settings → Project or
set `RT_GIT_REMOTE_URL` globally. For SSH remotes mount your key into the
container.

### Offline Mode

Set `RT_OFFLINE_MODE=true` to suppress all outbound network calls:
- Git remote pushes are skipped
- Email notifications are suppressed
- Release update checks are skipped
- All UI assets are bundled locally

### User Management

After logging in, go to **Users** to create team accounts, assign roles
(Administrator / Standard), and manage invitations. Users can also
self-register if `RT_ALLOW_SELF_REGISTRATION=true`.

---

## Backups

reqmesh data is plain YAML files. Back up the data directory:

```bash
# Bare-metal
tar -czf reqmesh-backup-$(date +%Y%m%d).tar.gz -C /opt/reqmesh data/projects/

# Docker
docker exec reqmesh-reqmesh-1 tar -czf /tmp/backup.tar.gz -C /data projects/
docker cp reqmesh-reqmesh-1:/tmp/backup.tar.gz ./backup.tar.gz
```

For projects with Git enabled, the auto-commit history serves as an
additional fail-safe.

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `RT_SECRET` | (required) | JWT signing key. Generate with `openssl rand -hex 32` |
| `RT_ADMIN_PASSWORD` | (required) | Initial admin password |
| `RT_DATA_ROOT` | `~/.reqmesh/projects` | Project data directory |
| `RT_STATIC_DIR` | `""` | Path to built frontend `/dist`. Set for single-origin serve |
| `RT_HOST` | `0.0.0.0` | uvicorn bind address |
| `RT_PORT` | `8000` | uvicorn listen port |
| `RT_BASE_URL` | `http://localhost:8000` | Public URL for email links |
| `RT_OFFLINE_MODE` | `false` | Suppress all outbound network calls |
| `RT_GIT_AUTOCOMMIT` | `true` | Auto-commit changes in project git repos |
| `RT_GIT_REMOTE_URL` | `""` | Remote to push auto-commits to |
| `RT_GIT_PUSH_ON_COMMIT` | `false` | Push after each auto-commit |
| `RT_SMTP_HOST` | `""` | SMTP server. Empty disables email |
| `RT_SMTP_PORT` | `587` | SMTP port |
| `RT_SMTP_USERNAME` | `""` | SMTP auth username |
| `RT_SMTP_PASSWORD` | `""` | SMTP auth password |
| `RT_SMTP_FROM` | `reqmesh@localhost` | From: address on emails |
| `RT_ALLOW_SELF_REGISTRATION` | `true` | Let users register from the login page |
| `RT_REQUIRE_EMAIL_VERIFICATION` | `false` | Require email verification for new accounts |
| `RT_LOCKOUT_MAX_ATTEMPTS` | `5` | Failed login attempts before lockout (0 to disable) |
| `RT_TOKEN_TTL_SECONDS` | `604800` | Session duration in seconds (default 7 days) |
| `RT_SEED_DEMO` | `true` | Create Cessna 172S example project on first launch |
| `RT_SELF_UPDATE_ENABLED` | `true` | Enable one-click update from UI (needs updater sidecar) |
