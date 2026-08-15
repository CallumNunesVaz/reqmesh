FROM python:3.12-slim

# git: project auto-commit / history. pango+harfbuzz+fonts: weasyprint PDF export
# (fallback renderer). curl/ca-certificates: fetch the tectonic LaTeX engine.
#
# openssh-client is listed explicitly because git only *Recommends* it and
# --no-install-recommends drops it: without it `ssh` does not exist, and every
# git@/ssh:// remote fails with "ssh: not found" even though both schemes are
# in ALLOWED_REMOTE_SCHEMES. It also provides ssh-keygen for managed keys.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    ca-certificates \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# tectonic: self-contained LaTeX engine for the primary (LaTeX) PDF report path.
# Only the ~30MB binary is baked in; its ~300MB TeX package bundle is fetched on
# demand at first PDF export and cached (see TECTONIC_CACHE_DIR). If tectonic or
# the network is unavailable, the report falls back to the weasyprint renderer.
RUN curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh \
    && mv tectonic /usr/local/bin/tectonic

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# See frontend/Dockerfile: dev images should not run as root either.
# Dockerfile.prod has had its own `USER reqmesh` since it was written.
RUN useradd -r -m -d /home/reqmesh reqmesh && chown -R reqmesh /app
USER reqmesh

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
