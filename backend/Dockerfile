FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

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
# Pinned release tarball verified against a recorded SHA-256, as in Dockerfile.prod;
# the old installer piped an unpinned remote script straight into a shell.
ARG TECTONIC_VERSION=0.17.0
ARG TECTONIC_SHA256=1a715688baf591e650c8aeb160ae934e181685eecbb38b317de30b269ac5d606
RUN curl --proto '=https' --tlsv1.2 -fsSL -o /tmp/tectonic.tar.gz \
      "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
 && echo "${TECTONIC_SHA256}  /tmp/tectonic.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic \
 && rm /tmp/tectonic.tar.gz

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
