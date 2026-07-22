FROM python:3.12-slim

# git: project auto-commit / history. pango+harfbuzz+fonts: weasyprint PDF export
# (fallback renderer). curl/ca-certificates: fetch the tectonic LaTeX engine.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
