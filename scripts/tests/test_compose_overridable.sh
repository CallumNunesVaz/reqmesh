#!/usr/bin/env bash
# Neither the shipped compose file nor the installer's generated one may pin a
# runtime setting the operator never set.
#
# `docker-compose.prod.yml` and the installer template both used to list every
# overridable key as `RT_X=${RT_X:-default}`, which compose substitutes and
# exports even when unset. `is_env_locked` is presence-based
# (`RT_<KEY> in os.environ`), so the admin settings page showed each one
# read-only — the runtime-settings feature was disabled by its own deployment
# file.
#
# The fix keeps `is_env_locked` untouched and instead stops exporting the keys:
# `environment:` pins only what the deployment must, and an operator pins a
# runtime setting by writing it to a `.env` file beside the compose file.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

COMPOSE="$REPO/docker-compose.prod.yml"
TMPL="$REPO/scripts/templates/docker-compose.prod.yml.tmpl"

# RT_<KEY> names for every key in backend/app/core/settings_store.py's
# OVERRIDABLE table. Driven from the model rather than hardcoded, so a key
# added there later is covered here without touching this file.
OVERRIDABLE="$(cd "$REPO/backend" && .venv/bin/python -c \
    'from app.core.settings_store import OVERRIDABLE; print(" ".join("RT_" + k.upper() for k in OVERRIDABLE))' \
    2>/dev/null)"
if [ -z "$OVERRIDABLE" ]; then
    printf 'could not read OVERRIDABLE from backend/app/core/settings_store.py\n' >&2
    exit 1
fi

# The keys that DO belong (deployment identity, secrets, security posture) —
# asserted present so the test cannot pass by emptying the whole environment
# block.
KEEP="RT_STATIC_DIR RT_DATA_ROOT RT_STATE_DIR RT_UPDATE_CONTROL_DIR RT_SECRET RT_ADMIN_PASSWORD RT_PROFILE RT_HOST RT_PORT"

# Report the RT_* keys exported in the rendered reqmesh service environment.
exported_keys() { # <yaml-output>
    printf '%s\n' "$1" | sed -n 's/^[[:space:]]*\(RT_[A-Z0-9_]*\):.*/\1/p' | sort -u | tr '\n' ' '
}

# Which of the overridable keys are present in an exported-key list.
overridable_in() { # <exported-keys>
    local exported="$1" leaked="" v
    for v in $OVERRIDABLE; do
        case " $exported " in *" $v "*) leaked="$leaked $v" ;; esac
    done
    printf '%s' "${leaked# }"
}

section "the shipped compose file leaves overridable settings editable"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    # A project dir with no `.env`, so only the required :? vars come from the
    # shell and nothing else can leak in.
    PROJ="$(mktemp -d)"
    trap 'rm -rf "$PROJ"' EXIT
    rendered="$(env -i PATH="$PATH" HOME="$HOME" RT_SECRET=x RT_ADMIN_PASSWORD=x \
        docker compose -f "$COMPOSE" --project-directory "$PROJ" config 2>/dev/null)"

    exported="$(exported_keys "$rendered")"
    leaked="$(overridable_in "$exported")"
    check "docker compose config exports no overridable keys" "$leaked" ""

    missing=""
    for v in $KEEP; do
        case " $exported " in *" $v "*) ;; *) missing="$missing $v" ;; esac
    done
    check "deployment-pinned keys are still exported" "$missing" ""

    # Pinning via `.env` must still work — that is how ops locks a key on purpose.
    printf 'RT_OFFLINE_MODE=true\n' > "$PROJ/.env"
    pinned="$(env -i PATH="$PATH" HOME="$HOME" RT_SECRET=x RT_ADMIN_PASSWORD=x \
        docker compose -f "$COMPOSE" --project-directory "$PROJ" config 2>/dev/null \
        | sed -n 's/^[[:space:]]*\(RT_OFFLINE_MODE\):.*/\1/p')"
    check "a .env pin is exported" "$pinned" "RT_OFFLINE_MODE"
else
    # No docker — parse the file and say so. The environment list is a sequence
    # of `- RT_X=...` entries; none of the overridable names may appear.
    env_list="$(sed -n '/^[[:space:]]*environment:/,/^[[:space:]]*volumes:/p' "$COMPOSE")"
    leaked=""
    for v in $OVERRIDABLE; do
        if printf '%s\n' "$env_list" | grep -qE "^[[:space:]]*-[[:space:]]*${v}="; then
            leaked="$leaked $v"
        fi
    done
    check "compose file lists no overridable keys (docker unavailable; parsed file)" "$leaked" ""
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "the installer's compose template leaves overridable settings editable"

# Render the template the way generate_compose does (the "none" proxy branch
# clears the service placeholders), then let compose interpolate it with an
# optional `.env` beside it.
render_template() { # <env-file-content>
    local proj env_body="${1-}"
    proj="$(mktemp -d)"
    sed -e 's/%_CADDY_SERVICE_%//' -e 's/%_NGINX_SERVICE_%//' -e 's/%_CADDY_VOLUME_%//' \
        "$TMPL" > "$proj/docker-compose.prod.yml"
    if [ -n "$env_body" ]; then
        printf '%s\n' "$env_body" > "$proj/.env"
    fi
    env -i PATH="$PATH" HOME="$HOME" RT_SECRET=x RT_ADMIN_PASSWORD=x \
        docker compose -f "$proj/docker-compose.prod.yml" --project-directory "$proj" config 2>/dev/null
    rm -rf "$proj"
}

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    # No operator settings: the rendered template must export none of the
    # overridable keys, so every field on the Settings page stays editable.
    rendered="$(render_template "")"
    exported="$(exported_keys "$rendered")"
    check "template exports no overridable keys" "$(overridable_in "$exported")" ""

    missing=""
    for v in $KEEP; do
        case " $exported " in *" $v "*) ;; *) missing="$missing $v" ;; esac
    done
    check "template still pins the deployment-owned keys" "$missing" ""

    # One overridable key set via .env must be exported — and only that one.
    rendered_one="$(render_template 'RT_SMTP_HOST=smtp.example.com')"
    exported_one="$(exported_keys "$rendered_one")"
    check "a single .env pin exports exactly that key" \
          "$(overridable_in "$exported_one")" "RT_SMTP_HOST"

    # The deployment-owned keys survive the pinned case too.
    missing=""
    for v in $KEEP; do
        case " $exported_one " in *" $v "*) ;; *) missing="$missing $v" ;; esac
    done
    check "template pins the deployment-owned keys alongside the pin" "$missing" ""
else
    env_list="$(sed -n '/^[[:space:]]*environment:/,/^[[:space:]]*volumes:/p' "$TMPL")"
    leaked=""
    for v in $OVERRIDABLE; do
        if printf '%s\n' "$env_list" | grep -qE "^[[:space:]]*-[[:space:]]*${v}="; then
            leaked="$leaked $v"
        fi
    done
    check "template lists no overridable keys (docker unavailable; parsed file)" "$leaked" ""
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "install.sh's generated env emits overridable settings only when set"

# Run lib.sh's emitter against a CFG populated exactly as install.sh would leave
# it — empty for a key the operator never chose.
emit_with() { # <KEY=value>...
    bash -c '
        declare -A CFG=()
        COLLECTED_DIR="$(mktemp -d)"; export COLLECTED_DIR
        source "$1/scripts/lib.sh" >/dev/null 2>&1
        shift
        for kv in "$@"; do
            k="${kv%%=*}"; v="${kv#*=}"
            CFG[$k]="$v"
        done
        emit_overridable_env
    ' _ "$REPO" "$@"
}

check "no operator settings -> no overridable lines" "$(emit_with)" ""

check "one set key -> exactly that line" \
      "$(emit_with SMTP_HOST=smtp.example.com)" "RT_SMTP_HOST=smtp.example.com"

check "every configured key is emitted" \
      "$(emit_with SMTP_HOST=smtp.example.com SMTP_PORT=2525 REPORT_COMPANY_NAME=Acme)" \
      $'RT_SMTP_HOST=smtp.example.com\nRT_SMTP_PORT=2525\nRT_REPORT_COMPANY_NAME=Acme'

check "base_url is emitted only when pinned" \
      "$(emit_with BASE_URL=https://reqs.example.com BASE_URL_PINNED=true)" \
      "RT_BASE_URL=https://reqs.example.com"
check "a derived base_url is not pinned" \
      "$(emit_with BASE_URL=https://reqs.example.com BASE_URL_PINNED=false)" ""

check "docker deploy emits overridable keys conditionally" \
      "$(grep -c 'overrides="\$(emit_overridable_env)"' "$REPO/scripts/deploy-docker.sh")" "1"
check "bare deploy emits overridable keys conditionally" \
      "$(grep -c 'overrides="\$(emit_overridable_env)"' "$REPO/scripts/deploy-bare.sh")" "1"

# The deployment-owned keys remain in the always-written block of both .env
# generators, so pinning a runtime key never displaces them.
check "docker .env keeps RT_SECRET" \
      "$(grep -c 'RT_SECRET=${CFG\[RT_SECRET\]}' "$REPO/scripts/deploy-docker.sh")" "1"
check "docker .env keeps RT_PROFILE" \
      "$(grep -c 'RT_PROFILE=${CFG\[PROFILE\]' "$REPO/scripts/deploy-docker.sh")" "1"
check "bare .env keeps RT_STATE_DIR" \
      "$(grep -c 'RT_STATE_DIR=$STATE_DIR' "$REPO/scripts/deploy-bare.sh")" "1"
check "bare .env keeps RT_STATIC_DIR" \
      "$(grep -c 'RT_STATIC_DIR=${CFG\[STATIC_DIR\]' "$REPO/scripts/deploy-bare.sh")" "1"

finish
