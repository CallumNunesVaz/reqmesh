#!/usr/bin/env bash
# install.sh — reqmesh deployment installer
#
# Usage:
#   ./install.sh                          Interactive wizard (recommended)
#   ./install.sh --non-interactive [opts] Scripted deployment (CI/automation)
#   ./install.sh --help                   Show help
#
# The interactive wizard walks through deployment mode, reverse proxy,
# security profile, credentials, and optional integrations. At the end
# it generates configuration files and deploys reqmesh.
#
# For non-interactive use, set environment variables:
#   RT_PROFILE, RT_SECRET, RT_ADMIN_PASSWORD, RT_BASE_URL, ...
#   or pass them on the command line: --profile team --domain example.com ...
#   See the full list at: https://github.com/CallumNunesVaz/reqmesh
#
# Dependencies are installed automatically:
#   Docker path: Docker + Compose plugin, Caddy (optional)
#   Bare path:   Python 3.12+, systemd, Caddy/nginx (optional), tectonic

set -euo pipefail

# Under the documented `curl … | bash`, BASH_SOURCE[0] is *unbound* — not merely
# empty — so `set -u` made the installer's very first line print
# "BASH_SOURCE[0]: unbound variable" before anything else. The value was then
# whatever the failed subshell left behind. Resolve it deliberately instead:
# piped input has no directory, and standalone mode below stages the companions
# into its own temp dir anyway.
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    SCRIPT_DIR="$PWD"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Standalone mode — if lib.sh is absent we are running with only this file.
# Download all companion scripts and templates from the repo so the rest of
# the installer can proceed as if the full tree were present.
# ═══════════════════════════════════════════════════════════════════════════════
if ! [ -f "$SCRIPT_DIR/lib.sh" ]; then
    _RED='\033[0;31m'; _GREEN='\033[0;32m'; _YELLOW='\033[1;33m'; _BLUE='\033[0;34m'; _NC='\033[0m'
    _info()  { printf "${_BLUE}→${_NC} %s\n" "$*"; }
    _warn()  { printf "${_YELLOW}⚠${_NC} %s\n" "$*" >&2; }
    _err()   { printf "${_RED}✗${_NC} %s\n" "$*" >&2; exit 1; }

    # Pinned by default. `main` moves, so an installer fetched today and re-run
    # next month would silently pull different companion scripts than the ones
    # it was tested against — and a force-push would change them under a user
    # mid-install. Override REQMESH_REF to track a branch deliberately.
    _REF="${REQMESH_REF:-v0.1.35}"
    _REPO_RAW="${REQMESH_INSTALL_REPO:-https://raw.githubusercontent.com/CallumNunesVaz/reqmesh/${_REF}/scripts}"

    case "$_REPO_RAW" in
        https://*) ;;
        *) _err "REQMESH_INSTALL_REPO must be an https:// URL (got: $_REPO_RAW)" ;;
    esac

    # Staged in a private temp directory, not alongside this script. When the
    # installer is run the documented way — `curl … | bash` — ${BASH_SOURCE[0]}
    # is empty and SCRIPT_DIR resolves to $PWD, so the previous version wrote
    # lib.sh, wizard.sh, deploy-*.sh, templates/ and updater/ into whatever
    # directory the user happened to be standing in, usually their home.
    _STAGE="$(mktemp -d "${TMPDIR:-/tmp}/reqmesh-bootstrap.XXXXXXXXXX")"
    chmod 700 "$_STAGE"
    trap 'rm -rf "$_STAGE"' EXIT
    mkdir -p "$_STAGE/templates" "$_STAGE/updater"

    _info "Standalone mode — fetching companion scripts"
    _info "  source: $_REPO_RAW"

    _companions=(
        lib.sh wizard.sh deploy-docker.sh deploy-bare.sh
        templates/docker-compose.prod.yml.tmpl
        templates/Caddyfile.tmpl
        templates/nginx.conf.tmpl
        templates/reqmesh.service.tmpl
        updater/watch.sh
    )
    for _f in "${_companions[@]}"; do
        printf "${_BLUE}  ↓${_NC} %s" "$_f"
        if ! curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 15 --retry 2 \
                "$_REPO_RAW/$_f" -o "$_STAGE/$_f"; then
            printf "\r${_RED}  ✗${_NC} %s\n" "$_f"
            _err "Failed to download $_f — check connectivity, or set REQMESH_INSTALL_REPO to a mirror"
        fi
        # These files are about to be sourced and run as root. curl reports
        # success for a response that was cut short mid-transfer, and a
        # half-written lib.sh defines half its functions — the installer would
        # then fail somewhere deep in a deployment rather than here. There is no
        # published checksum to compare against (the release bundle ships a
        # different installer), so verify what can be verified locally: the file
        # is non-empty, and shell scripts actually parse.
        if [ ! -s "$_STAGE/$_f" ]; then
            _err "Downloaded $_f is empty — refusing to continue"
        fi
        case "$_f" in
            *.sh)
                bash -n "$_STAGE/$_f" 2>/dev/null \
                    || _err "Downloaded $_f is not valid shell — refusing to run a truncated or corrupted script"
                ;;
        esac
        printf "\r${_GREEN}  ✓${_NC} %s\n" "$_f"
    done

    chmod +x "$_STAGE"/*.sh "$_STAGE/updater"/*.sh
    SCRIPT_DIR="$_STAGE"
    REQMESH_STANDALONE=1
    printf "${_GREEN}✓${_NC} Companion scripts ready (%s).\n\n" "$_STAGE"
    _warn "Integrity rests on TLS to the host above, exactly as it did for this"
    _warn "script. Review $_STAGE before continuing if that is not sufficient."
fi

source "$SCRIPT_DIR/lib.sh"

# ═══════════════════════════════════════════════════════════════════════════════
# Bootstrap Gum
# ═══════════════════════════════════════════════════════════════════════════════
bootstrap_gum() {
    if command -v gum &>/dev/null; then
        return 0
    fi
    info "Gum TUI not found — downloading..."
    local gum_ver="0.14.5"
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        *)       arch="amd64" ;; # fallback
    esac
    local os
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"

    local base="https://github.com/charmbracelet/gum/releases/download/v${gum_ver}"
    local tarball="gum_${gum_ver}_${os}_${arch}.tar.gz"
    local tmpdir
    tmpdir="$(mktemp -d)"

    # Download to disk and verify against the release's published checksums
    # before unpacking, rather than piping curl straight into tar. A truncated
    # or corrupted download can no longer produce a half-written binary that
    # then gets put on PATH and executed.
    #
    # Note this proves integrity, not provenance — the checksums come from the
    # same host as the tarball, so it is not a defence against a compromised
    # upstream release. Gum is optional UI: air-gapped installs should
    # pre-install it (or skip it and use the plain-text prompts).
    if ! curl -fsSL --proto '=https' --tlsv1.2 -o "$tmpdir/$tarball" "$base/$tarball"; then
        warn "Gum download failed. Falling back to plain-text prompts."
        rm -rf "$tmpdir"
        return 0
    fi

    local checksum_verified=false
    if curl -fsSL --proto '=https' --tlsv1.2 -o "$tmpdir/checksums.txt" \
            "$base/checksums.txt" 2>/dev/null; then
        local expected actual
        expected="$(awk -v f="$tarball" '$2 == f || $2 == "*"f {print $1}' "$tmpdir/checksums.txt" | head -1)"
        if [ -z "$expected" ]; then
            warn "No checksum published for $tarball — skipping Gum rather than trusting it."
            rm -rf "$tmpdir"
            return 0
        fi
        if has_cmd sha256sum; then
            actual="$(sha256sum "$tmpdir/$tarball" | awk '{print $1}')"
        elif has_cmd openssl; then
            actual="$(openssl dgst -sha256 "$tmpdir/$tarball" | awk '{print $NF}')"
        else
            warn "Neither sha256sum nor openssl available — skipping Gum rather than trusting it."
            rm -rf "$tmpdir"
            return 0
        fi
        if [ "$expected" != "$actual" ]; then
            error "Gum checksum mismatch — refusing to install."
            error "  expected $expected"
            error "  actual   $actual"
            rm -rf "$tmpdir"
            return 0
        fi
        checksum_verified=true
    fi
    if ! $checksum_verified; then
        warn "Could not verify the Gum checksum — skipping Gum rather than trusting it."
        rm -rf "$tmpdir"
        return 0
    fi

    tar xzf "$tmpdir/$tarball" -C "$tmpdir"
    local binary
    binary="$(find "$tmpdir" -type f -name gum -perm -u+x | head -1)"
    if [ -z "$binary" ]; then
        warn "No gum binary in the archive. Falling back to plain-text prompts."
        rm -rf "$tmpdir"
        return 0
    fi

    # Install to ~/.local/bin or /usr/local/bin
    local dest="${HOME}/.local/bin"
    mkdir -p "$dest"
    mv "$binary" "$dest/gum" 2>/dev/null || {
        sudo mv "$binary" /usr/local/bin/gum
        dest="/usr/local/bin"
    }
    rm -rf "$tmpdir"

    # Add to PATH for this session if needed
    export PATH="$dest:$PATH"

    if command -v gum &>/dev/null; then
        success "Gum installed to $dest/gum"
    else
        warn "Gum download failed. Falling back to plain-text prompts."
        warn "You can install Gum manually: https://github.com/charmbracelet/gum#installation"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Non-interactive mode
# ═══════════════════════════════════════════════════════════════════════════════
non_interactive() {
    info "Running in non-interactive mode..."

    # Settings resolve in this order: an explicit environment variable for this
    # run, then whatever the install already on this box is using, then the
    # factory default. Before this the middle term did not exist, so upgrading a
    # machine reset every setting the operator had chosen.
    local _install_dir="${REQMESH_INSTALL_DIR:-/opt/reqmesh}"
    if load_installed_env "$_install_dir"; then
        info "Existing installation detected at $_install_dir"
        info "  Its settings will be kept unless overridden for this run."
        save_cfg "EXISTING_INSTALL" "true"
    else
        save_cfg "EXISTING_INSTALL" "false"
    fi

    # ── --upgrade ─────────────────────────────────────────────────────────
    # "Keep everything, just move the application forward." A plain
    # --non-interactive run already preserves settings, but nothing stops a
    # leftover REQMESH_PROXY in the environment from quietly reshaping the
    # deployment as a side effect of an upgrade. This makes that a hard error
    # instead, so the flag means what it says.
    if [ "${REQMESH_UPGRADE:-0}" = "1" ]; then
        if [ "${CFG[EXISTING_INSTALL]}" != "true" ]; then
            error "--upgrade needs an existing installation, and none was found at $_install_dir."
            error ""
            error "Nothing has been changed. To install for the first time, run without"
            error "--upgrade (or pass --non-interactive with the settings you want)."
            exit 1
        fi
        local _shape_vars="" _v
        for _v in REQMESH_DEPLOY_MODE REQMESH_PROXY REQMESH_TLS REQMESH_DOMAIN \
                  RT_DATA_ROOT RT_PORT RT_BASE_URL RT_PROFILE; do
            [ -n "${!_v:-}" ] && _shape_vars="$_shape_vars $_v"
        done
        if [ -n "$_shape_vars" ]; then
            error "--upgrade does not change configuration, but these are set:$_shape_vars"
            error ""
            error "Nothing has been changed. Either unset them to upgrade in place, or"
            error "drop --upgrade to apply them as a reconfiguration."
            exit 1
        fi
        info "Upgrading in place — configuration, accounts and data are kept."
    fi

    # Read settings from environment variables (RT_* prefix)
    # The deploy scripts pick these up from the saved config file
    # The deployment shape is recorded in the generated .env (see generate_env)
    # precisely so a re-install can recover it. Without that, upgrading a
    # domain-backed HTTPS install with a bare `install.sh --non-interactive`
    # silently rebuilt it as a domainless one.
    _mode="$(resolve_deploy_mode)" || exit 1

    # Standalone mode downloads the *scripts*, not the application. Docker mode
    # is fine — it pulls an image — but bare metal copies from $SCRIPT_DIR/..,
    # which under `curl | bash` is the bootstrap temp directory's parent. It used
    # to discover this only in install_app, after apt had installed a reverse
    # proxy and the existing unit had been backed up.
    if [ "${REQMESH_STANDALONE:-0}" = "1" ] && [ "$_mode" = "bare" ]; then
        # Not written as ${REQMESH_REF:-v...}: that literal collides with the
        # ref-pin the release process rewrites, and with the test that checks it.
        local _ver="${REQMESH_REF:-}"
        [ -n "$_ver" ] || _ver="v$(cat "$SCRIPT_DIR/../VERSION" 2>/dev/null || echo 0.1.5)"
        error "Bare-metal install needs the application source, which this"
        error "one-liner does not download (it fetches only the scripts)."
        error ""
        error "Use the release bundle instead — it ships the application and"
        error "this same installer, and needs no network once unpacked:"
        error "  curl -fsSLO https://github.com/CallumNunesVaz/reqmesh/releases/download/${_ver}/reqmesh-${_ver}.tar.gz"
        error "  tar xzf reqmesh-${_ver}.tar.gz && cd reqmesh-${_ver}"
        error "  sudo REQMESH_DEPLOY_MODE=bare ./install.sh --non-interactive"
        exit 1
    fi

    # Both deployment modes default here, so switching mode does not move the
    # data. An existing install keeps whatever it already uses — changing the
    # default must never relocate a populated data root.
    # REQMESH_DATA_ROOT, not RT_DATA_ROOT: under Docker the latter is the path
    # *inside the container* and says nothing about where the host keeps the data.
    # Reading it meant a Docker deploy erased the record and the next run
    # relocated a populated data root to the default.
    save_cfg "DATA_ROOT" "${RT_DATA_ROOT:-$(prev_env REQMESH_DATA_ROOT "$(prev_env RT_DATA_ROOT '/data/projects')")}"
    guard_mode_conversion "$_mode" || exit 1
    save_cfg "DEPLOY_MODE" "$_mode"
    save_cfg "PROXY" "${REQMESH_PROXY:-$(prev_env REQMESH_PROXY "$($PREV_FOUND && detect_proxy || echo caddy)")}"
    save_cfg "TLS" "${REQMESH_TLS:-$(prev_env REQMESH_TLS "$($PREV_FOUND && detect_tls || echo letsencrypt)")}"
    save_cfg "DOMAIN" "${REQMESH_DOMAIN:-$(prev_env REQMESH_DOMAIN '')}"
    # letsencrypt without a public domain cannot work; record what will actually
    # be used rather than leaving .env claiming otherwise.
    save_cfg "TLS" "$(reconcile_tls_with_domain)"
    save_cfg "HOST" "${RT_HOST:-0.0.0.0}"
    save_cfg "PORT" "${RT_PORT:-8000}"
    # Empty means "derive from PROXY" — see effective_bind.
    save_cfg "BIND" "${RT_BIND:-}"
    # Needed before BASE_URL, which derives its host from it.
    save_cfg "LAN_IP" "$(detect_lan_ip)"

    # BASE_URL cannot simply be carried over from the previous install the way
    # the other settings are. Switching a deployment between HTTP and HTTPS
    # changes the correct answer — the proxy takes 80/443 and the app loses its
    # published port, or the reverse — so preserving it left the operator being
    # told to browse to an address that no longer answers, and made the
    # installer's own post-deploy check fail against a URL it had invented.
    #
    # An explicit value always wins. A carried-over value is kept only while it
    # still fits the deployment, so a custom host survives an unrelated re-run.
    if [ -n "${RT_BASE_URL:-}" ]; then
        save_cfg "BASE_URL" "$RT_BASE_URL"
    else
        _prev_base="$(prev_env RT_BASE_URL '')"
        if [ -n "$_prev_base" ] && base_url_fits_shape "$_prev_base"; then
            save_cfg "BASE_URL" "$_prev_base"
        else
            _derived="$(derive_base_url)"
            if [ -n "$_prev_base" ] && [ "$_prev_base" != "$_derived" ]; then
                info "Base URL updated for the new configuration:"
                info "  was $_prev_base"
                info "  now $_derived"
            fi
            save_cfg "BASE_URL" "$_derived"
        fi
    fi
    # Which image tag to deploy: the newest published release unless pinned.
    #
    # This briefly defaulted to the installer's own version, after a host was
    # found serving 0.1.4 having been installed by v0.1.10. That diagnosis was
    # half right — the tag was floating, but the reason it never moved was a
    # preflight that skipped `docker pull` whenever the tag was already present
    # locally. With the pull unconditional (see deploy-docker.sh), `latest`
    # resolves to the newest image on every run, which is what an operator
    # running the installer almost always wants.
    #
    # A pin is an explicit REQMESH_VERSION, and it is not remembered across runs:
    # re-running without it deliberately moves the deployment forward again.
    save_cfg "IMAGE_TAG" "${REQMESH_VERSION:-latest}"
    save_cfg "PROFILE" "${RT_PROFILE:-$(prev_env RT_PROFILE 'team')}"

    # Keep the signing secret across a re-install. Minting a new one on every
    # upgrade invalidated every session and every outstanding reset token, for
    # no benefit — a rotation should be a deliberate act, not a side effect of
    # deploying a new version.
    _secret="${RT_SECRET:-$(prev_env RT_SECRET '')}"
    [ -z "$_secret" ] && _secret="$(rand_secret 32)"
    save_cfg "RT_SECRET" "$_secret"

    # RT_ADMIN_PASSWORD only ever takes effect on a first install: the app seeds
    # the admin account solely when users.yaml is absent. Generating a fresh one
    # for an existing install therefore produced a password that does not work,
    # printed to the operator as though it did. Carry the old value through so
    # the .env stays self-consistent, and let the summary say the accounts were
    # kept rather than inventing a credential.
    _admin_pw="${RT_ADMIN_PASSWORD:-$(prev_env RT_ADMIN_PASSWORD '')}"
    [ -z "$_admin_pw" ] && _admin_pw="$(rand_secret 12)"
    save_cfg "ADMIN_PASSWORD" "$_admin_pw"
    save_cfg "REQUIRE_AUTH" "${RT_REQUIRE_AUTH:-$(prev_env RT_REQUIRE_AUTH 'true')}"
    save_cfg "SELF_REG" "${RT_ALLOW_SELF_REGISTRATION:-$(prev_env RT_ALLOW_SELF_REGISTRATION 'false')}"
    # A Secure cookie is never sent over plain HTTP, so hardcoding `true` here
    # produced a deployment where login returned 200 and every request after it
    # returned 401 — the session cookie was set and then never sent back. The
    # wizard already derives this from whether TLS is actually active; the
    # non-interactive path has to apply the same rule rather than a constant.
    # An explicit RT_COOKIE_SECURE still wins, for a TLS-terminating proxy in
    # front that the installer cannot see.
    # Read from CFG, not the raw environment: those were resolved above and may
    # have come from the existing install rather than from this invocation.
    _tls_active=false
    case "${CFG[TLS]:-letsencrypt}" in
        ""|none) ;;
        *) [ "${CFG[PROXY]:-caddy}" != "none" ] && _tls_active=true ;;
    esac
    if [ -n "${RT_COOKIE_SECURE:-}" ]; then
        save_cfg "COOKIE_SECURE" "$RT_COOKIE_SECURE"
    else
        save_cfg "COOKIE_SECURE" "$_tls_active"
        [ "$_tls_active" = false ] && warn \
            "No TLS configured — cookies will not be marked Secure. Do not expose this deployment to the internet."
    fi
    save_cfg "TLS_ACTIVE" "$_tls_active"
    save_cfg "REQUIRE_EMAIL_VERIFICATION" "${RT_REQUIRE_EMAIL_VERIFICATION:-$(prev_env RT_REQUIRE_EMAIL_VERIFICATION 'false')}"
    save_cfg "SMTP_HOST" "${RT_SMTP_HOST:-$(prev_env RT_SMTP_HOST '')}"
    save_cfg "SMTP_PORT" "${RT_SMTP_PORT:-$(prev_env RT_SMTP_PORT '587')}"
    save_cfg "SMTP_USERNAME" "${RT_SMTP_USERNAME:-$(prev_env RT_SMTP_USERNAME '')}"
    save_cfg "SMTP_PASSWORD" "${RT_SMTP_PASSWORD:-$(prev_env RT_SMTP_PASSWORD '')}"
    save_cfg "SMTP_FROM" "${RT_SMTP_FROM:-$(prev_env RT_SMTP_FROM 'reqmesh@localhost')}"
    save_cfg "SMTP_USE_TLS" "${RT_SMTP_USE_TLS:-$(prev_env RT_SMTP_USE_TLS 'true')}"
    save_cfg "GIT_REMOTE_URL" "${RT_GIT_REMOTE_URL:-$(prev_env RT_GIT_REMOTE_URL '')}"
    save_cfg "GIT_AUTOCOMMIT" "${RT_GIT_AUTOCOMMIT:-$(prev_env RT_GIT_AUTOCOMMIT 'true')}"
    save_cfg "GIT_PUSH_ON_COMMIT" "${RT_GIT_PUSH_ON_COMMIT:-$(prev_env RT_GIT_PUSH_ON_COMMIT 'false')}"
    save_cfg "GIT_PUSH_INTERVAL_MINUTES" "${RT_GIT_PUSH_INTERVAL_MINUTES:-$(prev_env RT_GIT_PUSH_INTERVAL_MINUTES '0')}"
    save_cfg "GIT_COMMIT_SCHEDULE" "${RT_GIT_COMMIT_SCHEDULE:-$(prev_env RT_GIT_COMMIT_SCHEDULE 'every_change')}"
    save_cfg "GIT_COMMIT_INTERVAL_HOURS" "${RT_GIT_COMMIT_INTERVAL_HOURS:-$(prev_env RT_GIT_COMMIT_INTERVAL_HOURS '0')}"
    save_cfg "GIT_COMMIT_CHANGES_THRESHOLD" "${RT_GIT_COMMIT_CHANGES_THRESHOLD:-$(prev_env RT_GIT_COMMIT_CHANGES_THRESHOLD '0')}"
    save_cfg "GIT_USER_NAME" "${GIT_USER_NAME:-$(prev_env GIT_USER_NAME 'reqmesh')}"
    save_cfg "GIT_USER_EMAIL" "${GIT_USER_EMAIL:-$(prev_env GIT_USER_EMAIL 'reqmesh@localhost')}"
    save_cfg "REPORT_COMPANY_NAME" "${RT_REPORT_COMPANY_NAME:-$(prev_env RT_REPORT_COMPANY_NAME '')}"
    save_cfg "REPORT_DOCUMENT_TITLE" "${RT_REPORT_DOCUMENT_TITLE:-$(prev_env RT_REPORT_DOCUMENT_TITLE '')}"
    save_cfg "REPORT_LOGO_URL" "${RT_REPORT_LOGO_URL:-$(prev_env RT_REPORT_LOGO_URL '')}"
    save_cfg "SEED_DEMO" "${RT_SEED_DEMO:-$(prev_env RT_SEED_DEMO 'true')}"
    save_cfg "OFFLINE_MODE" "${RT_OFFLINE_MODE:-$(prev_env RT_OFFLINE_MODE 'false')}"
    save_cfg "INSTALL_DIR" "${REQMESH_INSTALL_DIR:-/opt/reqmesh}"
    save_cfg "PROXY_TRUSTED_CIDR" "${RT_PROXY_TRUSTED_CIDR:-127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"
    save_cfg "UPDATE_CONTROL_DIR" "${RT_UPDATE_CONTROL_DIR:-/control}"
    save_cfg "CORS_ORIGINS" "${RT_CORS_ORIGINS:-$(prev_env RT_CORS_ORIGINS '')}"
    save_cfg "ALLOWED_HOSTS" "${RT_ALLOWED_HOSTS:-$(prev_env RT_ALLOWED_HOSTS '')}"
    save_cfg "REQMESH_USER" "${REQMESH_USER:-reqmesh}"
    save_cfg "REQMESH_GROUP" "${REQMESH_GROUP:-reqmesh}"

    # Dispatch to deploy script
    local mode="${CFG[DEPLOY_MODE]:-docker}"
    case "$mode" in
        docker) "$SCRIPT_DIR/deploy-docker.sh" ;;
        bare)   "$SCRIPT_DIR/deploy-bare.sh" ;;
        *)      error "Unknown deploy mode: $mode"; exit 1 ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════════════════════════
show_help() {
    cat << EOF
reqmesh install wizard

Usage:
  ./install.sh                           Interactive wizard (recommended)
  ./install.sh --non-interactive         Scripted deployment (reads RT_* env vars)
  ./install.sh --upgrade                 Move an existing install to the newest
                                         release, changing nothing else
  ./install.sh --debug                   Trace every command (transcript holds secrets)
  ./install.sh --no-log                  Do not write a transcript
  ./install.sh --help                    This help

Re-running over an existing installation keeps its settings, its signing secret
and its accounts. Anything you set explicitly for that run still wins; anything
you leave unset stays as the machine already has it. The admin password is not
regenerated — the application only seeds an admin when there is no account yet.

A transcript of the deployment is written to \$TMPDIR (0600) and its path is
printed on failure. Override with REQMESH_LOG=/path/to/file.

Interactive mode walks through:
  1. Welcome
  2. Deployment mode (Docker / bare-metal)
  3. Reverse proxy (Caddy / nginx / none)
  4. Domain & TLS configuration
  5. Security profile (personal / team / hardened)
  6. Admin credentials
  7. Optional integrations (SMTP, Git, branding)
  8. Installation paths
  9. Review & deploy

Non-interactive mode reads from these environment variables:

  REQMESH_DEPLOY_MODE  docker | bare        (default: docker)
  REQMESH_PROXY        caddy | nginx | none  (default: caddy)
  REQMESH_TLS          letsencrypt | internal | selfsigned | none
  REQMESH_DOMAIN       example.com (or blank for localhost)
  RT_PROFILE           personal | team | hardened  (default: team)
  RT_SECRET            Signing key (auto-generated if empty)
  RT_ADMIN_PASSWORD    Admin password (auto-generated if empty)
  RT_BASE_URL          https://example.com  (default: http://localhost:8000)
  RT_HOST, RT_PORT     Bind address/port
  RT_SMTP_HOST, RT_SMTP_PORT, ...  SMTP relay settings
  RT_GIT_REMOTE_URL    Git remote for backup
  RT_SEED_DEMO         true | false  (default: true)
  REQMESH_INSTALL_DIR  Install path  (default: /opt/reqmesh)
  RT_DATA_ROOT         Project data  (default: /data/projects, both modes)

All RT_* settings from config.py are accepted.

EOF
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
main() {
    local args=() arg
    for arg in "$@"; do
        case "$arg" in
            --debug|--verbose) REQMESH_DEBUG=1 ;;
            --no-log)          REQMESH_NO_LOG=1 ;;
            # An upgrade is a scripted run that is not allowed to reshape the
            # deployment, so it implies --non-interactive rather than adding a
            # second mode that would need its own copy of the same logic.
            --upgrade)         REQMESH_UPGRADE=1; args+=("--non-interactive") ;;
            *)                 args+=("$arg") ;;
        esac
    done
    set -- "${args[@]+"${args[@]}"}"

    case "${1:-}" in
        --help|-h|help)
            show_help
            exit 0
            ;;
        --non-interactive|--batch)
            # No TUI here, so the transcript can cover the whole run.
            start_transcript
            trap 'report_failure $?' EXIT
            detect_os
            non_interactive
            exit $?
            ;;
    esac

    # Interactive wizard
    detect_os
    bootstrap_gum

    # Run the wizard to collect configuration
    source "$SCRIPT_DIR/wizard.sh"
    run_wizard

    # Transcript starts here: the questions are done, and from this point on
    # stdout being a pipe costs nothing.
    start_transcript
    trap 'report_failure $?' EXIT

    # Deploy based on collected mode.
    #
    # Executed as a child process, not sourced. Each deploy script ends with
    # `main "$@"`, so sourcing it ran the whole deployment, and the explicit
    # `main` that followed then ran it a *second* time — re-rendering configs
    # and re-running `docker compose up` on every interactive install.
    # COLLECTED_DIR is exported by lib.sh, so the child sees the same config.
    load_cfg
    local mode="${CFG[DEPLOY_MODE]:-docker}"
    case "$mode" in
        docker) "$SCRIPT_DIR/deploy-docker.sh" ;;
        bare)   "$SCRIPT_DIR/deploy-bare.sh" ;;
        *)
            error "Unknown deployment mode: $mode"
            exit 1
            ;;
    esac
}

main "$@"
