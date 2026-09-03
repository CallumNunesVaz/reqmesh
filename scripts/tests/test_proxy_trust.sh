#!/usr/bin/env bash
# Proxy trust invariants that only break at run time.
#
# The app derives the real client IP from X-Forwarded-For only when the
# immediate peer is inside `proxy_trusted_cidr` (loopback by default). The
# three launch sites hand uvicorn a `--forwarded-allow-ips` trust list that must
# stay in step with that default: uvicorn's ProxyHeadersMiddleware rewrites
# `request.client` from the forwarded header before the app sees it, so a wider
# list lets any LAN host that can reach the app port choose its own client IP
# and get a fresh rate-limit bucket per request — silently disabling the per-IP
# defence the app layer built.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

# ══════════════════════════════════════════════════════════════════════════════
section "--forwarded-allow-ips matches proxy_trusted_cidr in every launch site"
# ══════════════════════════════════════════════════════════════════════════════

# The app's source of truth, parsed out of config.py rather than hardcoded, so
# the test still bites the moment someone changes the default.
default_cidr="$(grep 'proxy_trusted_cidr' "$REPO/backend/app/core/config.py" \
    | sed -n 's/.*=[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -1)"

# The value that follows --forwarded-allow-ips, whichever quoting style the
# file uses (JSON array element, double, or single quotes).
forwarded_value() {
    grep -h -- '--forwarded-allow-ips' "$1" \
        | sed -nE 's/.*--forwarded-allow-ips[^0-9]*([0-9][0-9./,]*).*/\1/p' \
        | head -1
}

# A silent parse failure must not read as a pass.
check "config.py proxy_trusted_cidr default was parsed" \
      "$([ -n "$default_cidr" ] && echo yes || echo no)" "yes"

check "Dockerfile.prod trusts only proxy_trusted_cidr" \
      "$(forwarded_value "$REPO/Dockerfile.prod")" "$default_cidr"

check "DEPLOYMENT.md systemd unit trusts only proxy_trusted_cidr" \
      "$(forwarded_value "$REPO/DEPLOYMENT.md")" "$default_cidr"

check "start.sh trusts only proxy_trusted_cidr" \
      "$(forwarded_value "$REPO/start.sh")" "$default_cidr"

finish
