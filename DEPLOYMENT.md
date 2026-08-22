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
| `.../reqmesh/v0.3.6/scripts/install.sh` | that release — reproducible, recommended |
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
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.3.6/scripts/install.sh | bash
```

For a bare-metal install (Python venv + systemd, no Docker), answer "bare" at
the deployment-mode prompt, or run it scripted:

```bash
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.3.6/scripts/install.sh \
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

### Version-specific notes

**Upgrading to 0.2.4 invalidates outstanding password-reset and invitation
links.** Reset tokens are now stored hashed, so the file no longer holds a
usable copy of anyone's token — but entries written by an earlier version are
keyed by the raw token and cannot be told apart from a hash, so they are deleted
rather than converted. Anyone mid-reset asks for a new link; **any invitation you
sent and that has not yet been accepted must be re-sent** from Users.

The same upgrade repairs file permissions in the state directory (an older
bootstrap path could leave `users.yaml` world-readable) and will refuse to start
if `RT_STATE_DIR` resolves inside `RT_DATA_ROOT` — a layout in which git
auto-commit would commit and push your password hashes. If that refusal fires,
move the state directory outside the data root and restart; nothing is lost.

A plain re-run behaves the same way for settings, but does allow changes:

```bash
curl -fsSL https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/v0.3.6/scripts/install.sh \
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
tar xzf reqmesh-v0.3.6.tar.gz && cd reqmesh-v0.3.6
sudo ./install.sh --non-interactive        # delegates to scripts/install.sh
```

The bare-metal path needs no network. For Docker offline, load the published
image first and pin it:

```bash
docker load < reqmesh-v0.3.6-image.tar.gz
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

    > `.rt-secret` (the JWT signing key), `.rt-admin-pw` (the admin password)
    > and `data/` (the requirement data) are secrets and are gitignored. If you
    > move them to another location, check that your `.gitignore` still matches.

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

#### Pinning a runtime setting

Most instance settings (SMTP, offline mode, base URL, self-update, the report
branding, …) are **editable from the admin UI** out of the box — they fall back
to the app's own defaults. To pin one at the deployment level, write it into a
`.env` file next to the compose file; the container picks it up and the UI then
shows it read-only:

```bash
# .env  (same directory as docker-compose.prod.yml)
RT_OFFLINE_MODE=true
RT_SMTP_HOST=smtp.example.com
```

`RT_SECRET` and `RT_ADMIN_PASSWORD` are still required, either in the
environment or in `.env`.

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
echo RT_OFFLINE_MODE=true >> .env
docker compose -f docker-compose.prod.yml up -d
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
decisions, and comments. Set these either from the admin Settings page or by
pinning them in a `.env` file next to `docker-compose.prod.yml`:

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
cat >> .env <<'EOF'
RT_SMTP_HOST=localhost
RT_SMTP_PORT=1025
RT_SMTP_USE_TLS=false
EOF
docker compose -f docker-compose.prod.yml up -d
```
Open `http://localhost:8025` to see captured emails.

### Git Remote Push

reqmesh can push every change to an external Git repository for off-server
backup and an audit trail. Configure the remote via Settings → Project or
set `RT_GIT_REMOTE_URL` globally.

For SSH remotes, generate a deploy key from the project's Git panel (admin
only): the public half and its fingerprint are shown there for pasting into
GitHub/GitLab as a deploy key with write access, and the private half is stored
on the server under `<data root>/.ssh/<project>/id_ed25519`. Use **Rotate** to
replace it (pushes fail until the new public key is re-registered at the host)
and **Delete** to remove it.

Mounting your own key into the container remains supported as an alternative:
place it where the container's `ssh` agent or default identity can find it, and
reqmesh will use it when no project deploy key exists.

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

reqmesh data is plain YAML files, so a backup is a copy of a directory. Back up
**both** the project data and the state directory beside it — they are separate
trees and the projects alone are not a complete backup:

| Path | Holds | Cost of losing it |
|------|-------|-------------------|
| `projects/` | every project's requirements, components, history | the work itself |
| `.reqmesh/users.yaml` | every account (password hashes, roles) | re-bootstrap the admin and re-invite everyone |
| `.reqmesh/secret` | the session signing key | every session invalidated; everyone logs in again. Irrelevant if you pin `RT_SECRET` in the environment, which is the better practice |
| `.reqmesh/settings.yaml` | admin settings overrides, including the SMTP password | re-enter them |

```bash
# Bare-metal — the parent of projects/, so the state dir is included
tar -czf reqmesh-backup-$(date +%Y%m%d).tar.gz \
    --exclude .initial-admin -C /opt/reqmesh data/

# Docker
docker exec reqmesh-reqmesh-1 tar -czf /tmp/backup.tar.gz \
    --exclude .initial-admin -C / data/
docker cp reqmesh-reqmesh-1:/tmp/backup.tar.gz ./backup.tar.gz
```

`.initial-admin` is excluded deliberately: it holds the generated bootstrap
password in cleartext, and it should have been deleted after first login anyway.

**The archive contains password hashes and your SMTP credentials.** Store it with
the same care as the instance itself — an offline copy of `users.yaml` is exactly
what a password-cracking attempt needs.

### Restoring

```bash
# Stop first: restoring under a running instance races its writes
docker compose -f docker-compose.prod.yml stop reqmesh
sudo tar -xzf backup.tar.gz -C /
sudo chown -R 999:999 /data          # the container runs as uid 999
sudo chmod 600 /data/.reqmesh/users.yaml /data/.reqmesh/secret
docker compose -f docker-compose.prod.yml start reqmesh
```

The ownership step is the one people miss: restoring as root leaves files the
container cannot write, and the failure shows up later as a login that cannot
update `last_active`.

For projects with Git enabled, the auto-commit history serves as an
additional fail-safe — but note it covers project data only, never accounts.

---

## Environment Variable Reference

Every setting below is read through the `RT_` prefix, a leftover from an
earlier name of the product — the letters no longer expand to anything, and
today they simply mark a **reqmesh** setting. Defaults are the code defaults in
`backend/app/core/config.py`;
the `personal`, `team` and `hardened` deployment profiles adjust a few of them,
and any `RT_*` value you set explicitly always wins over both.

| Variable | Default | Description |
|----------|---------|-------------|
| `RT_PROFILE` | `team` | Security posture: `personal`, `team`, or `hardened`. Sets defaults for auth, registration and cookies |
| `RT_HOST` | `0.0.0.0` | uvicorn bind address |
| `RT_PORT` | `8000` | uvicorn listen port |
| `RT_BIND` | `127.0.0.1` (compose) | **Not an app setting.** The compose host bind for the `ports:` mapping — `${RT_BIND:-127.0.0.1}:8000:8000` in `docker-compose.prod.yml`. One letter from `RT_HOST` (the uvicorn bind address), but it only controls which host interface Docker publishes on |
| `RT_DATA_ROOT` | `~/.reqmesh/projects` | Project data directory |
| `RT_STATE_DIR` | `~/.reqmesh` | Accounts, signing secret, settings. Must **not** be inside `RT_DATA_ROOT` — the app refuses to start if it is, because git auto-commit would push password hashes |
| `RT_STATIC_DIR` | `""` | Path to built frontend `/dist`. Set for single-origin serve |
| `RT_BASE_URL` | `http://localhost:8000` | Public URL for email links |
| `RT_ALLOWED_HOSTS` | `["*"]` | Reject requests whose `Host` header doesn't match (comma-separated) |
| `RT_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed cross-origin browser origins (comma-separated). Leave empty for a single-origin deployment; the app refuses to start on `*` |
| `RT_SECRET` | (generated) | JWT signing key. Generate with `openssl rand -hex 32` |
| `RT_ADMIN_PASSWORD` | (generated) | Initial admin password |
| `RT_REQUIRE_AUTH` | (per profile) | Require a session for every API route. Defaults `true` in `team`/`hardened`, `false` in `personal` |
| `RT_ALLOW_SELF_REGISTRATION` | (per profile) | Let users register from the login page. Defaults `false` in `team`/`hardened`, `true` in `personal` |
| `RT_REQUIRE_EMAIL_VERIFICATION` | `false` | Require email verification for new accounts. Defaults `true` in `hardened` |
| `RT_REGISTRATION_DOMAIN_ALLOWLIST` | `""` | Self-registration email-domain allowlist (comma-separated). Empty = any domain when registration is enabled |
| `RT_COOKIE_SECURE` | (per profile) | `Secure` flag on the session cookie. Defaults `true` in `team`/`hardened`, `false` in `personal` (plain HTTP) |
| `RT_TOKEN_TTL_SECONDS` | `604800` | Session duration in seconds (default 7 days) |
| `RT_LOCKOUT_MAX_ATTEMPTS` | `5` | Failed login attempts before lockout |
| `RT_LOCKOUT_WINDOW_MINUTES` | `15` | Lockout duration in minutes after too many failed logins |
| `RT_RATE_LIMIT_ENABLED` | `true` | Per-IP rate limiting on login, password reset, export and analysis endpoints. Only turn off for the end-to-end suite — a deployment running without it is warned at startup |
| `RT_MAX_UPLOAD_SIZE_MB` | `50` | Upload size cap for imports and test-result files |
| `RT_MAX_JSON_BODY_MB` | `10` | JSON request body size cap |
| `RT_MAX_SSE_CONNS_PER_USER` | `5` | Maximum concurrent SSE connections per user |
| `RT_MAX_SSE_CONNS_GLOBAL` | `100` | Maximum concurrent SSE connections in total |
| `RT_PROXY_TRUSTED_CIDR` | `127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` | Trusted proxy CIDRs whose `X-Forwarded-For` is used for the real client IP. Narrow to your reverse proxy's exact address |
| `RT_CSP_DEFAULT` | `""` | Content-Security-Policy override. Empty = profile-appropriate default (`hardened` adds `upgrade-insecure-requests`) |
| `RT_GIT_AUTOCOMMIT` | `true` | Auto-commit changes in project git repos |
| `RT_GIT_REMOTE_URL` | `""` | Remote to push auto-commits to |
| `RT_GIT_PUSH_ON_COMMIT` | `false` | Push after each auto-commit |
| `RT_GIT_PUSH_INTERVAL_MINUTES` | `0` | When set, batch pushes on a timer rather than on every commit |
| `RT_GIT_COMMIT_SCHEDULE` | `every_change` | When auto-commits fire: `every_change`, `interval`, `changes`, or `both` |
| `RT_GIT_COMMIT_INTERVAL_HOURS` | `0` | Commit interval in hours when `RT_GIT_COMMIT_SCHEDULE` is `interval` or `both` |
| `RT_GIT_COMMIT_CHANGES_THRESHOLD` | `0` | Commit after this many mutating requests when `RT_GIT_COMMIT_SCHEDULE` is `changes` or `both` |
| `RT_SEED_DEMO` | `true` | Create the Cessna 172S example project on first launch |
| `RT_OFFLINE_MODE` | `false` | Suppress all outbound network calls (git push, SMTP, update checks) |
| `RT_CODE_ROOT` | `""` | Default source directory for the code-to-requirement tag scanner |
| `RT_INSTANCE_NAME` | `reqmesh` | Instance name shown on the login/registration UI |
| `RT_SUPPORT_EMAIL` | `""` | Support address shown on the login/registration UI |
| `RT_TEAMS` | `["Systems Engineering"]` | Comma-separated list of team names offered when creating accounts |
| `RT_SMTP_HOST` | `""` | SMTP server. Empty disables email |
| `RT_SMTP_PORT` | `587` | SMTP port |
| `RT_SMTP_USERNAME` | `""` | SMTP auth username |
| `RT_SMTP_PASSWORD` | `""` | SMTP auth password |
| `RT_SMTP_FROM` | `reqmesh@localhost` | From: address on emails |
| `RT_SMTP_USE_TLS` | `true` | Use TLS for SMTP (set `false` for Mailpit-style local testing) |
| `RT_REPORT_COMPANY_NAME` | `""` | Company name in published reports |
| `RT_REPORT_DEPARTMENT` | `""` | Department line in published reports |
| `RT_REPORT_DOCUMENT_TITLE` | `""` | Document title in published reports |
| `RT_REPORT_LOGO_URL` | `""` | Logo URL used in published reports |
| `RT_REPORT_SHOW_GIT_COMMIT` | `false` | Show the git commit hash in published reports |
| `RT_REPORT_DOCUMENT_NUMBER` | `""` | Document number field in published reports |
| `RT_REPORT_REVISION` | `""` | Revision field in published reports |
| `RT_REPORT_CLASSIFICATION` | `""` | Classification field in published reports |
| `RT_REPORT_STATUS` | `""` | Status field in published reports |
| `RT_REPORT_PREPARED_BY` | `""` | Prepared-by field in published reports |
| `RT_REPORT_REVIEWED_BY` | `""` | Reviewed-by field in published reports |
| `RT_REPORT_APPROVED_BY` | `""` | Approved-by field in published reports |
| `RT_REPORT_DISTRIBUTION` | `[]` | Distribution list in published reports (comma-separated) |
| `RT_REPORT_COLOR` | `#2094f3` | Hex accent colour for PDF reports |
| `RT_GITHUB_REPO` | `CallumNunesVaz/reqmesh` | Repository the self-updater checks against |
| `RT_GITHUB_TOKEN` | `""` | GitHub token for update checks (avoids rate limiting) |
| `RT_SELF_UPDATE_ENABLED` | `true` | Enable one-click update from UI (needs the updater sidecar) |
| `RT_UPDATE_CONTROL_DIR` | `/control` | Directory the app shares with the updater sidecar |
| `RT_UPDATE_CHECK_TTL_SECONDS` | `3600` | How long update-check results are cached |
| `RT_MAX_UPDATE_UPLOAD_MB` | `2048` | Size cap for uploaded update archives |
| `RT_LOG_LEVEL` | `INFO` | Python log level |
| `RT_DEBUG` | `false` | Show stack traces in error responses |
