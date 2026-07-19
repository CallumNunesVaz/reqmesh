# reqmesh — Local Server Deployment

This guide walks through deploying reqmesh on a local server for network-wide
access with multiple concurrent users. The result is a production-style setup
serving reqmesh at `https://localserver.reqmesh.com` (or any hostname you
choose), with role-based access control, real-time collaboration, and TLS.

## Architecture

```
Browser (https://localserver.reqmesh.com)
        │
        ▼
┌──────────────────────┐
│  Caddy / nginx       │  ← TLS termination, reverse proxy
│  (reverse proxy)     │
└──────┬───────────────┘
       │ http://reqmesh:8000
       ▼
┌──────────────────────┐
│  reqmesh container   │  ← FastAPI + pre-built React SPA
│  (single origin)     │     uvicorn --workers 1
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  /data/projects/     │  ← persisted volume
│  (YAML file storage) │     one directory per project
└──────────────────────┘
```

- **Single origin** — the backend serves both the API and the UI (`RT_STATIC_DIR`). No CORS configuration needed, no Vite dev server.
- **TLS** — the reverse proxy terminates HTTPS. Caddy can auto-provision certificates; nginx uses pre-generated ones.
- **One worker** — the SSE event bus (real-time presence and change streaming) is in-memory, so the backend runs with `--workers 1`. This supports ~20 concurrent users comfortably. For larger teams a Redis-backed event bus can be added later.

---

## Prerequisites

On the server machine:

- **Docker** and **Docker Compose** (v2+)
- **git** (to clone the repo, and for project auto-commits inside containers)
- **openssl** (to generate secrets)
- A hostname that resolves to the server's LAN IP on every client machine. Options:
  - Local DNS (pi-hole, dnsmasq, router A record)
  - `/etc/hosts` on each client (e.g. `192.168.1.100 localserver.reqmesh.com`)
  - mDNS (use `reqmesh.local` instead — no DNS config needed, but TLS requires extra steps)

---

## 1. Clone and prepare

```bash
git clone https://github.com/your-org/reqmesh.git /opt/reqmesh-server
cd /opt/reqmesh-server
```

---

## 2. Generate secrets

```bash
export RT_SECRET=$(openssl rand -hex 32)
export RT_ADMIN_PASSWORD=$(openssl rand -base64 12)

echo "Secret:  $RT_SECRET"
echo "Admin:   $RT_ADMIN_PASSWORD"
# Write these down — the admin password is shown only here.
```

`RT_SECRET` signs JWT tokens. Losing it invalidates all existing sessions.
`RT_ADMIN_PASSWORD` is the password for the `admin` user created on first launch.

---

## 3. Launch (plain HTTP — quick test)

Start without the reverse proxy first to verify the app works:

```bash
RT_SECRET=$RT_SECRET RT_ADMIN_PASSWORD=$RT_ADMIN_PASSWORD \
  docker compose -f docker-compose.prod.yml up -d
```

Check that it's healthy:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

Open `http://<server-ip>:8000` in a browser. Log in with `admin` / `$RT_ADMIN_PASSWORD`.

> **Note:** If you can't reach port 8000 from other machines, the `RT_BIND`
> default may be too restrictive. Set `RT_BIND=0.0.0.0` to bind to all
> interfaces:
>
> ```bash
> RT_BIND=0.0.0.0 RT_SECRET=$RT_SECRET RT_ADMIN_PASSWORD=$RT_ADMIN_PASSWORD \
>   docker compose -f docker-compose.prod.yml up -d
> ```

---

## 4. Add TLS with Caddy (recommended)

Caddy is the simplest option — it auto-provisions certificates and handles
HTTPS setup in a few lines of config.

### 4.1 Choose your TLS mode

| Scenario | Caddyfile entry | Requires |
|----------|----------------|----------|
| Public domain (e.g. `reqmesh.example.com` with real DNS) | Nothing — Caddy auto-provisions Let's Encrypt | Port 80+443 accessible from internet |
| LAN-only domain (e.g. `localserver.reqmesh.com` on local DNS) | `tls internal` | Nothing — self-signed, browsers will warn |
| LAN domain with trusted certificate | Use `mkcert` to create a local CA, then point Caddy at the certs | `mkcert` installed on the server |

For a LAN setup, **`tls internal` + installing the Caddy root CA on clients** is
the most practical:

```bash
# On the server, extract Caddy's root CA after first start:
docker cp reqmesh-caddy-1:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# Distribute caddy-root.crt to clients and install it in their OS trust store.
```

### 4.2 Edit the Caddyfile

The repo includes a `Caddyfile` at the project root. Edit the `server_name` to
match your chosen hostname, then uncomment the `caddy` service in
`docker-compose.prod.yml` and restart:

```bash
# Edit docker-compose.prod.yml:
#   - Comment out the `ports:` block on the `reqmesh` service
#   - Uncomment the `caddy` service block

docker compose -f docker-compose.prod.yml up -d
```

Access at `https://<your-hostname>`.

---

## 5. Add TLS with nginx (alternative)

If you prefer nginx, generate certificates with **mkcert**:

### 5.1 Install mkcert and create a local CA

```bash
# macOS
brew install mkcert
# Linux
sudo apt install libnss3-tools && curl -JLO https://dl.filippo.io/mkcert/latest?for=linux/amd64 && chmod +x mkcert-v*-linux-amd64 && sudo mv mkcert-v*-linux-amd64 /usr/local/bin/mkcert

mkcert -install
```

### 5.2 Generate certificates

```bash
mkcert -cert-file server.crt -key-file server.key \
  localserver.reqmesh.com reqmesh.local "*.reqmesh.lan"
```

### 5.3 Configure nginx

Place the certificates where nginx can read them, e.g. `./certs/server.crt` and
`./certs/server.key`. The repo includes an `nginx.conf` you can mount into an
nginx container or copy to `/etc/nginx/sites-available/`.

Docker compose snippet for adding nginx:

```yaml
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - reqmesh
    restart: unless-stopped
```

---

## 6. Create user accounts

After logging in as `admin`, go to the **Users** page (`/users`) to create
accounts for your team:

- Click **Create User**
- Enter a username, password (≥8 chars), and role:
  - **Standard** (`editor`) — can create, edit, and delete entities
  - **Administrator** (`admin`) — can also delete projects and manage users
- Users can also self-register via the login dialog (they get the `editor` role)

The users file lives at `~/.reqmesh/users.yaml` inside the container (on the
`/data` volume). It persists across restarts.

---

## 7. Enable git auto-commit per project

For git auto-commit to work, each project directory must be a git repository.
The Cessna demo is seeded without `git init` — to enable auto-commit on it:

```bash
docker compose -f docker-compose.prod.yml exec reqmesh sh -c \
  'cd /data/projects/cessna-172 && git init && git add -A && git commit -m "Initial seed"'
```

For new projects created through the UI, run `git init` inside their directory
on the server (or add it as a post-create hook — see below).

> **Note:** The Docker image pre-configures `git config user.name` and
> `user.email` inside the container so auto-commits don't fail.

---

## 8. Real-time collaboration

No additional configuration is needed. The SSE endpoint at
`/api/projects/{id}/events` provides:

- **Live change streaming** — lists, trees, and the graph update when anyone
  mutates the project
- **Presence** — avatars in the header bar show who is currently viewing each
  project

Both work across browser tabs and across users on different machines.

> **Important:** The event bus is **in-memory per process**. Running with
> `--workers 1` (the default in `Dockerfile.prod`) keeps all SSE subscribers in
> the same process. If you scale to multiple workers you'll need to add a Redis
> pub/sub backend to `backend/app/services/event_bus.py`. For teams of up to
> ~20 concurrent users, one worker is sufficient.

---

## 9. Git Remote Push (auto-sync to external repo)

reqmesh can push auto-commits to an external git repository after every change,
giving you an off-server backup and a full audit log accessible outside the
application.

### 9.1 Configure the remote

Set these environment variables:

| Variable | Description |
|----------|-------------|
| `RT_GIT_REMOTE_URL` | Git remote URL (e.g. `git@github.com:org/reqmesh-projects.git`) |
| `RT_GIT_PUSH_ON_COMMIT` | Set to `true` to push after every auto-commit |

```bash
RT_GIT_REMOTE_URL='git@github.com:my-org/reqmesh-data.git' \
RT_GIT_PUSH_ON_COMMIT=true \
RT_SECRET=$RT_SECRET RT_ADMIN_PASSWORD=$RT_ADMIN_PASSWORD \
  docker compose -f docker-compose.prod.yml up -d
```

### 9.2 Authentication

For SSH remotes, mount your SSH key into the container and configure SSH:

```yaml
services:
  reqmesh:
    volumes:
      - ~/.ssh/id_ed25519:/root/.ssh/id_ed25519:ro
      - reqmesh-data:/data
    environment:
      - GIT_SSH_COMMAND=ssh -o StrictHostKeyChecking=accept-new
```

For HTTPS remotes with token auth:
```
RT_GIT_REMOTE_URL='https://username:ghp_xxxxxxxxxxxx@github.com/org/repo.git'
```

### 9.3 What gets pushed

Only the project data (YAML files, history, baselines) — not user accounts or
server configuration. Each project directory must be `git init`'d first (see
section 7). The remote is set automatically on first push.

When `RT_OFFLINE_MODE=true` is set, all push attempts are skipped silently.

---

## 10. Email Notifications

reqmesh can send email notifications when key project events occur, keeping
team members informed without requiring them to be logged in.

### 10.1 Supported notifications

| Event | Trigger |
|-------|---------|
| Requirement reviewed | A requirement is marked as reviewed (fingerprint baselined) |
| Change request created / updated | A CR is created or modified |
| Risk created / updated | A risk is created or modified |
| Decision recorded / updated | A decision record is created or modified |
| Comment added | A comment is posted on a requirement |

### 10.2 Configure SMTP

Set these environment variables:

```bash
RT_SMTP_HOST=smtp.example.com
RT_SMTP_PORT=587
RT_SMTP_USERNAME=reqmesh@example.com
RT_SMTP_PASSWORD=your-app-password
RT_SMTP_FROM=reqmesh@example.com
RT_BASE_URL=https://localserver.reqmesh.com   # for links in emails
```

Or in `docker-compose.prod.yml`:

```yaml
environment:
  - RT_SMTP_HOST=${RT_SMTP_HOST:-}
  - RT_SMTP_PORT=${RT_SMTP_PORT:-587}
  - RT_SMTP_USERNAME=${RT_SMTP_USERNAME:-}
  - RT_SMTP_PASSWORD=${RT_SMTP_PASSWORD:-}
  - RT_SMTP_FROM=${RT_SMTP_FROM:-reqmesh@localhost}
  - RT_BASE_URL=${RT_BASE_URL:-http://localhost:8000}
```

### 10.3 Assign emails to users

1. Log in as admin
2. Go to **Users** (`/users`)
3. Click a user and set their email address
4. Save

Only users with an email set will receive notifications.

### 10.4 Common providers

| Provider | SMTP host | Port | Notes |
|----------|-----------|------|-------|
| Gmail | `smtp.gmail.com` | 587 | Requires app password (not account password) |
| Office 365 | `smtp.office365.com` | 587 | Requires tenant allows SMTP AUTH |
| Mailgun / SendGrid | Use API credentials | 587 | Dedicated relay services |
| Local postfix / exim | `localhost` | 25 | If running an MTA on the server |
| Mailpit (dev) | `localhost` | 1025 | No auth, captures to web UI — great for testing |

### 10.5 Testing email

To test without a real SMTP server, use **Mailpit**:

```bash
docker run -d --name mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit

RT_SMTP_HOST=localhost RT_SMTP_PORT=1025 RT_SMTP_USE_TLS=false \
RT_BASE_URL=http://localhost:8000 \
  docker compose -f docker-compose.prod.yml up -d
```

Then open `http://localhost:8025` to see all captured emails.

### 10.6 Delivery guarantees

Email delivery is **best-effort and fire-and-forget**:
- Sends happen on background threads — they never block API responses
- Failures are logged but never raised as API errors
- If the SMTP server is unreachable, notifications are silently dropped
- When `RT_OFFLINE_MODE=true`, all email sends are skipped

---

## 11. Offline Mode (air-gapped deployment)

For deployments on networks with no internet access, reqmesh can run in fully
offline mode.

### 11.1 Enable offline mode

Set `RT_OFFLINE_MODE=true`:

```bash
RT_OFFLINE_MODE=true docker compose -f docker-compose.prod.yml up -d
```

When offline mode is active:
- Git remote pushes are skipped (even if `RT_GIT_REMOTE_URL` is set)
- Email notifications are suppressed (even if SMTP is configured)
- The UI makes no external CDN calls (all assets are bundled)

### 11.2 Building for offline deployment

Build the Docker image on a machine with internet access, then transfer it:

```bash
# On the connected machine
docker compose -f docker-compose.prod.yml build
docker save reqmesh-reqmesh:latest | gzip > reqmesh-image.tar.gz

# Copy reqmesh-image.tar.gz to the air-gapped server
scp reqmesh-image.tar.gz user@airgap-server:/opt/reqmesh-server/

# On the air-gapped server
cd /opt/reqmesh-server
gunzip -c reqmesh-image.tar.gz | docker load
RT_OFFLINE_MODE=true docker compose -f docker-compose.prod.yml up -d
```

### 11.3 TLS on air-gapped networks

Caddy's `tls internal` generates a self-signed certificate with no external
communication. nginx with `mkcert`-generated certificates also works entirely
offline. See sections 4 and 5 for setup.

---

## 12. Backups

Projects are just YAML files in `/data/projects/`. Back up the volume:

```bash
# With the container running
docker compose -f docker-compose.prod.yml exec reqmesh \
  tar -czf /tmp/reqmesh-backup.tar.gz -C /data projects/

docker cp reqmesh-reqmesh-1:/tmp/reqmesh-backup.tar.gz ./reqmesh-backup-$(date +%Y%m%d).tar.gz
```

Or mount the volume to a host path and use your existing backup tool:

```yaml
volumes:
  - /srv/reqmesh/data:/data
```

---

## 13. Troubleshooting

### Cannot reach the server from other machines

- Check `RT_BIND` — default is `127.0.0.1` (localhost only). Set to `0.0.0.0`.
- Check the firewall: `sudo ufw allow 8000` (or 443 if using Caddy/nginx).
- Verify the DNS/hosts entry on the client machine resolves correctly:
  ```bash
  ping localserver.reqmesh.com
  ```

### Real-time updates not working

- Ensure the reverse proxy has **`proxy_buffering off`** (nginx) or
  **`flush_interval -1`** (Caddy). Without this, SSE streams are buffered and
  events arrive in batches or not at all.
- Check `proxy_read_timeout` (nginx) is high enough — the default 60s will
  disconnect SSE clients. Set to `86400s` (24 hours).

### "Not a valid project" or 404 errors

- The project directory must contain a `_meta.yaml` file. Projects created
  through the API or UI always have this. If you manually copied files in,
  ensure `_meta.yaml` exists at the project root.

### PDF export fails

- The Docker image includes fonts-dejavu-core and libpango for weasyprint.
  If PDF export still fails, ensure the container has write access to `/tmp`.

### Users can't log in after restart

- `RT_SECRET` changed between restarts, invalidating all JWT tokens. Use a
  fixed secret (set once and keep it). If you lose it, users must log in again.

---

## 14. Environment variable reference

| Variable | Default | Description |
|----------|---------|-------------|
| `RT_SECRET` | (auto-generated) | JWT signing key. **Set explicitly for production.** |
| `RT_ADMIN_PASSWORD` | `admin` | Initial admin password. Only used on first launch. |
| `RT_DATA_ROOT` | `~/.reqmesh/projects` | Where project directories live. |
| `RT_STATIC_DIR` | `""` | Path to built frontend. Set to serve SPA from backend. |
| `RT_HOST` | `0.0.0.0` | Interface to bind uvicorn to. |
| `RT_PORT` | `8000` | Port to listen on. |
| `RT_CORS_ORIGINS` | `["http://localhost:5173", …]` | Allowed CORS origins. Unused when `RT_STATIC_DIR` is set (single origin). |
| `RT_GIT_AUTOCOMMIT` | `true` | Auto-commit project changes via git. |
| `RT_GIT_REMOTE_URL` | `""` | Git remote URL to push auto-commits to. |
| `RT_GIT_PUSH_ON_COMMIT` | `false` | Push to the configured remote after each auto-commit. |
| `RT_SEED_DEMO` | `true` | Seed the Cessna 172S example on first launch. |
| `RT_OFFLINE_MODE` | `false` | Suppress all outbound network calls (git push, SMTP). |
| `RT_BASE_URL` | `http://localhost:8000` | Public URL used for links in notification emails. |
| `RT_SMTP_HOST` | `""` | SMTP server host. Empty disables email. |
| `RT_SMTP_PORT` | `587` | SMTP server port. |
| `RT_SMTP_USERNAME` | `""` | SMTP authentication username. |
| `RT_SMTP_PASSWORD` | `""` | SMTP authentication password. |
| `RT_SMTP_FROM` | `reqmesh@localhost` | From: address on notification emails. |
| `RT_SMTP_USE_TLS` | `true` | Use STARTTLS for SMTP connections. |
| `RT_BIND` | `127.0.0.1` | Docker host port bind. Set to `0.0.0.0` for LAN access. |
