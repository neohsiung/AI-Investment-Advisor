#!/usr/bin/env bash
# Deployment identity + collision guard, sourced by install.sh and start.sh.
# 部署身分與撞名守衛：由 install.sh、start.sh 引用。
#
# A stack is named by two values read from .env:
#   ADVISOR_PROJECT_NAME      compose project (volumes and the network derive from it)
#   ADVISOR_CONTAINER_PREFIX  prefix of every container_name
# Defaults are NOT the production values. The pre-existing production box keeps
# its names by pinning them in its own .env (see docs/06_SRE_Observability).
# 預設值刻意不等於正式環境；既有正式環境在自己的 .env 釘住舊名字。
#
# advisor_guard_identity prints why and returns 1 before anything is built or
# started when the machine already runs something that this checkout would
# collide with or take over. Docker is only queried read-only.

ADVISOR_DEFAULT_PROJECT="advisor"
ADVISOR_DEFAULT_PREFIX="advisor"
ADVISOR_LEGACY_PROJECT="investment_advisor"
ADVISOR_LEGACY_PREFIX="advisor_prod"
ADVISOR_LEGACY_DB_VOLUME="investment_advisor_advisor_db_data"
ADVISOR_CONTAINER_SUFFIXES="api ui db cache beat worker gateway n8n ngrok"

function _advisor_env_value {
    # Usage: _advisor_env_value KEY DEFAULT  — reads the env file without sourcing it.
    local v=""
    # Last assignment wins, as in dotenv and docker compose.
    [ -f .env ] && v=$(grep "^${1}=" .env | tail -n1 | cut -d= -f2- | tr -d "\"' \r")
    echo "${v:-$2}"
}

function advisor_load_identity {
    ADVISOR_PROJECT_NAME="$(_advisor_env_value ADVISOR_PROJECT_NAME "$ADVISOR_DEFAULT_PROJECT")"
    ADVISOR_CONTAINER_PREFIX="$(_advisor_env_value ADVISOR_CONTAINER_PREFIX "$ADVISOR_DEFAULT_PREFIX")"
    ADVISOR_DB_VOLUME="${ADVISOR_PROJECT_NAME}_advisor_db_data"
    export ADVISOR_PROJECT_NAME ADVISOR_CONTAINER_PREFIX
    C_API="${ADVISOR_CONTAINER_PREFIX}_api"
    C_UI="${ADVISOR_CONTAINER_PREFIX}_ui"
    C_DB="${ADVISOR_CONTAINER_PREFIX}_db"
    C_CACHE="${ADVISOR_CONTAINER_PREFIX}_cache"
    C_BEAT="${ADVISOR_CONTAINER_PREFIX}_beat"
    C_WORKER="${ADVISOR_CONTAINER_PREFIX}_worker"
    C_GATEWAY="${ADVISOR_CONTAINER_PREFIX}_gateway"
    C_N8N="${ADVISOR_CONTAINER_PREFIX}_n8n"
}

function advisor_guard_identity {
    # $1 = path of this checkout.
    local here rows volumes
    here="$(cd "$1" && pwd -P)"
    advisor_load_identity

    # name <TAB> compose project <TAB> compose working dir (host path)
    if ! rows="$(docker ps -a --format '{{.Names}}	{{.Label "com.docker.compose.project"}}	{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null)"; then
        echo "✗ Could not list containers; refusing to guess whether a stack already runs here." >&2
        return 1
    fi
    volumes="$(docker volume ls --format '{{.Name}}' 2>/dev/null || true)"

    local expected=" " s
    for s in $ADVISOR_CONTAINER_SUFFIXES; do expected+="${ADVISOR_CONTAINER_PREFIX}_${s} "; done

    local pinned_legacy=0
    if [ "$ADVISOR_PROJECT_NAME" = "$ADVISOR_LEGACY_PROJECT" ] && [ "$ADVISOR_CONTAINER_PREFIX" = "$ADVISOR_LEGACY_PREFIX" ]; then
        pinned_legacy=1
    fi

    local problems="" name project wdir norm_wdir mine legacy_seen=0 legacy_elsewhere=0 legacy_names=""
    while IFS=$'\t' read -r name project wdir; do
        [ -z "$name" ] && continue
        norm_wdir=""
        if [ -n "$wdir" ]; then norm_wdir="$(cd "$wdir" 2>/dev/null && pwd -P || echo "$wdir")"; fi
        mine=0
        if [ "$project" = "$ADVISOR_PROJECT_NAME" ] && [ "$norm_wdir" = "$here" ]; then mine=1; fi

        case "$name" in
            "${ADVISOR_LEGACY_PREFIX}_"*)
                legacy_seen=1
                legacy_names+="${name} "
                if [ "$norm_wdir" != "$here" ]; then legacy_elsewhere=1; fi ;;
        esac
        if [ "$project" = "$ADVISOR_LEGACY_PROJECT" ]; then
            legacy_seen=1
            if [ "$norm_wdir" != "$here" ]; then legacy_elsewhere=1; fi
        fi

        if [ "$project" = "$ADVISOR_PROJECT_NAME" ] && [ "$norm_wdir" != "$here" ]; then
            problems+="  - compose project '${ADVISOR_PROJECT_NAME}' is already used by container ${name} (started from ${wdir:-unknown dir})"$'\n'
        fi
        if [ "$mine" = "0" ] && [[ "$expected" == *" ${name} "* ]]; then
            problems+="  - container name '${name}' is already taken (project '${project:-none}', ${wdir:-unknown dir})"$'\n'
        fi
    done <<< "$rows"

    # Legacy production signature: refuse unless this checkout is that production,
    # pinned by name, and no legacy container belongs to another checkout.
    # 正式環境的特徵：除非這個 checkout 就是正式環境且已釘住舊名字，否則一律拒絕。
    if printf '%s\n' "$volumes" | grep -qx "$ADVISOR_LEGACY_DB_VOLUME"; then legacy_seen=1; fi
    if [ "$legacy_seen" = "1" ] && { [ "$pinned_legacy" = "0" ] || [ "$legacy_elsewhere" = "1" ]; }; then
        problems+="  - an existing production-style stack was found on this machine (containers ${legacy_names:-${ADVISOR_LEGACY_PREFIX}_*}, project ${ADVISOR_LEGACY_PROJECT}, or volume ${ADVISOR_LEGACY_DB_VOLUME})"$'\n'
    fi

    [ -z "$problems" ] && return 0

    {
        echo ""
        echo "✗ Refusing to build or start: this would collide with, or take over, a stack that already exists."
        echo "  拒絕建置與啟動：會與本機既有的 stack 撞名或接管它。"
        echo ""
        printf '%s' "$problems"
        echo ""
        echo "  Names this checkout would use: project '${ADVISOR_PROJECT_NAME}', containers '${ADVISOR_CONTAINER_PREFIX}_*'."
        echo "  A new install should not share a machine with a running production stack."
        echo "  If THIS checkout is that existing stack, pin its names in .env and re-run:"
        echo ""
        echo "      ADVISOR_PROJECT_NAME=${ADVISOR_LEGACY_PROJECT}"
        echo "      ADVISOR_CONTAINER_PREFIX=${ADVISOR_LEGACY_PREFIX}"
        echo ""
    } >&2
    return 1
}
