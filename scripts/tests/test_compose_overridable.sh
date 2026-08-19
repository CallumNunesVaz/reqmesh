#!/usr/bin/env bash
# The shipped compose file must not pin a runtime setting the operator never set.
#
# `docker-compose.prod.yml` used to list every overridable key as
# `RT_X=${RT_X:-default}`, which compose substitutes and exports even when
# unset. `is_env_locked` is presence-based (`RT_<KEY> in os.environ`), so the
# admin settings page showed each one read-only — the runtime-settings feature
# was disabled by its own deployment file.
#
# The fix keeps `is_env_locked` untouched and instead stops exporting the keys:
# `environment:` now pins only what the deployment must, and an operator pins a
# runtime setting by writing it to a `.env` file beside the compose file.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

COMPOSE="$REPO/docker-compose.prod.yml"

# RT_<KEY> names for every key in backend/app/core/settings_store.py's
# OVERRIDABLE table. None of these may be exported by the compose file on its
# own; the app's default supplies the value and the UI stays editable.
OVERRIDABLE="RT_INSTANCE_NAME RT_SUPPORT_EMAIL RT_ALLOW_SELF_REGISTRATION \
RT_REQUIRE_EMAIL_VERIFICATION RT_OFFLINE_MODE RT_SELF_UPDATE_ENABLED RT_BASE_URL \
RT_SMTP_HOST RT_SMTP_PORT RT_SMTP_USERNAME RT_SMTP_PASSWORD RT_SMTP_FROM \
RT_SMTP_USE_TLS RT_TOKEN_TTL_SECONDS RT_LOCKOUT_MAX_ATTEMPTS \
RT_LOCKOUT_WINDOW_MINUTES RT_MAX_UPLOAD_SIZE_MB RT_GITHUB_REPO RT_GITHUB_TOKEN \
RT_TEAMS RT_REPORT_COMPANY_NAME RT_REPORT_DEPARTMENT RT_REPORT_DOCUMENT_TITLE \
RT_REPORT_LOGO_URL RT_REPORT_SHOW_GIT_COMMIT RT_REPORT_DOCUMENT_NUMBER \
RT_REPORT_REVISION RT_REPORT_CLASSIFICATION RT_REPORT_STATUS RT_REPORT_PREPARED_BY \
RT_REPORT_REVIEWED_BY RT_REPORT_APPROVED_BY RT_REPORT_DISTRIBUTION RT_REPORT_COLOR"

# The keys that DO belong in the shipped compose (deployment identity, secrets,
# security posture) — asserted present so the test cannot pass by emptying the
# whole environment block.
KEEP="RT_STATIC_DIR RT_DATA_ROOT RT_STATE_DIR RT_SECRET RT_ADMIN_PASSWORD RT_PROFILE RT_HOST RT_PORT"

# Report the RT_* keys exported in the rendered reqmesh service environment.
exported_keys() { # <yaml-output>
    printf '%s\n' "$1" | sed -n 's/^[[:space:]]*\(RT_[A-Z0-9_]*\):.*/\1/p' | sort -u | tr '\n' ' '
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
    leaked=""
    for v in $OVERRIDABLE; do
        case " $exported " in *" $v "*) leaked="$leaked $v" ;; esac
    done
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

finish
