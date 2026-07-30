# reqmesh — Server Deployment

Below are the available installation options depending on your setup. The
install process requires some knowledge of Linux server administration.
reqmesh is a Python application backed by the filesystem — no database
server is needed.

- [Requirements](#requirements)
- [Ubuntu 24.04](#ubuntu-2404) – the installer, one command
- [Upgrading](#upgrading) – re-running over an existing install
- [Manual Installation](#manual) – Python venv + systemd
- [Docker Containers](#docker) – Docker Compose with optional TLS
- [Configuration Guide](#configuration)

There is **one** installer, `scripts/install.sh`. It covers Docker and
bare-metal, Caddy/nginx/no proxy, and TLS, and it is the only path tested end to
end on a real host. Earlier releases also shipped `install-ubuntu-24.04.sh` and
a separate installer inside the release bundle; both were parallel
implementations that had drifted, and both have been removed.

---

## Requirements

| Component | Minimum | Notes |
|-----------|---------|-------|
| **Python** | 3.11+ | Includes `venv` and `pip` |
| **Node.js** | 20+ | Only needed to build the frontend. Pre-built bundles include `frontend/dist` |
| **Git** | 2.x | For project versioning and in-app change history |
| **nginx / Caddy** | Any recent | Reverse proxy for TLS and SSE streaming |
| **pango / harfbuzz** | – | System libraries for the fallback PDF renderer (weasyprint). Part of the script install |
| **tectonic** | Optional | LaTeX engine for the primary, typeset PDF reports. If absent, PDF export falls back to the weasyprint HTML renderer |

No database or message broker is required — projects are plain YAML files on
disk, and real-time collaboration uses in-process SSE.

### PDF reports (optional tectonic)

PDF export prefers a real LaTeX engine — [tectonic](https://tectonic-typesetting.github.io/)
— for typeset tables, coloured status/priority badges, and a table of contents.
Without one, reqmesh silently falls back to the weasyprint (HTML→PDF) renderer,
so PDF export always works either way. The System page shows which path is
active ("PDF reports: LaTeX (tectonic)" vs "HTML fallback").

The Docker images already bundle tectonic. On a **bare-metal** install, add it to
`PATH` to enable the LaTeX path:

```bash
# Single self-contained binary (MIT-licensed); no full TeX Live needed.
curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh
sudo mv tectonic /usr/local/bin/
```

tectonic downloads its TeX package bundle (~300 MB) on first use and caches it
under `TECTONIC_CACHE_DIR` (defaults to `~/.cache/tectonic`); that first PDF
needs network access, after which it works offline.

---

## Which URL to install from

The install command names a **git tag or branch**, which is not the same as the
`latest` container image tag:

| URL | Meaning |
|---|---|
| `.../reqmesh/v0.1.13/scripts/install.sh` | that release — reproducible, recommended |
| `.../reqmesh/main/scripts/install.sh` | current development tip |
| `.../reqmesh/latest/scripts/install.sh` | **404** — there is no git ref called `latest` |

`latest` exists only as a container image tag, and the installer already uses it
by default for the application image: an unpinned run deploys the newest
published image regardless of which installer tag you fetched. Pin the
application with `REQMESH_VERSION=<x.y.z>` if you need a specific one — note that
a pin is not remembered, so pass it on every run.

---

## Ubuntu 24.04

Use the standard installer — it covers Ubuntu 24.04 along with every other
supported target, and is the only install path that is tested end to end:

```bash
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.1.13/scripts/install.sh | bash
```

For a bare-metal install (Python venv + systemd, no Docker), answer "bare" at
the deployment-mode prompt, or run it scripted:

```bash
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.1.13/scripts/install.sh \
  | REQMESH_DEPLOY_MODE=bare REQMESH_PROXY=nginx bash -s -- --non-interactive
```

Re-running it over an existing installation keeps that machine's settings, its
signing secret and its accounts; see [Upgrading](#upgrading).

---

## Upgrading

```bash
sudo ./install.sh --upgrade
```

That moves the application to the newest published release and changes nothing
else. It refuses if there is no existing installation, and refuses if any
configuration variable is set in the environment — an upgrade that quietly
reshaped the deployment because a `REQMESH_PROXY` was left exported is not an
upgrade. Drop `--upgrade` to apply such a change deliberately.

A plain re-run behaves the same way for settings, but does allow changes:

```bash
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.1.13/scripts/install.sh \
  | bash -s -- --non-interactive
```

| Kept across an upgrade | Note |
|---|---|
| Every `RT_*` setting | Anything you set explicitly for that run wins |
| `RT_SECRET` | Regenerating it would log every session out |
| Accounts and passwords | The app seeds an admin only when none exists |
| Project data and git history | Untouched |

The previous `.env` and compose file are backed up alongside them with a
`.bak.<timestamp>` suffix.

**Changing the deployment shape works too.** Switching between HTTP and HTTPS,
or between Caddy, nginx and no proxy, re-derives the base URL, flips the cookie
`Secure` flag and the listen address to match, removes the previous proxy's
container, and restarts the new one so it actually reads its new config:

```bash
# turn TLS on
... | REQMESH_PROXY=caddy REQMESH_TLS=selfsigned bash -s -- --non-interactive
# turn it back off
... | REQMESH_PROXY=none REQMESH_TLS=none bash -s -- --non-interactive
```

A base URL you set deliberately (an external load balancer, a CNAME) survives a
re-run; one whose scheme or port contradicts the new configuration is replaced,
and the change is printed.

### From a release bundle (offline)

The tarball unpacks to a directory containing the application and the installer:

```bash
tar xzf reqmesh-v0.1.13.tar.gz && cd reqmesh-v0.1.13
sudo ./install.sh --non-interactive        # delegates to scripts/install.sh
```

The bare-metal path needs no network. For Docker offline, load the published
image first and pin it:

```bash
docker load < reqmesh-v0.1.13-image.tar.gz
REQMESH_VERSION=<loaded-tag> ./install.sh --non-interactive
```

### Diagnosing a failed install

The installer writes a transcript (mode 0600) and prints its path on failure.
`--debug` adds a full command trace — note it then captures `RT_SECRET` and the
admin password, so treat it as a secret. `--no-log` disables it.

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
