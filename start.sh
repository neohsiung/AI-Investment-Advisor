#!/usr/bin/env bash
#
# investment-advisor — single-box control script.
#
# Rewritten from 1031 lines / 26 functions / 14 commands down to the commands a
# single-operator deployment actually needs. What went, and why:
#
#   k8s                    manifests deleted (4 months stale, referenced a
#                          Streamlit dashboard that no longer exists)
#   ollama helpers         `check_shared_ollama` sourced ../infra/start-ollama.sh
#                          from a sibling repo that is not in this tree, and
#                          `cleanup` referenced a docker-compose.ollama.yml that
#                          has never existed
#   n8n import/backup      ~150 lines of workflow export + id-1 upsert wrangling;
#                          n8n's three schedules now run in Celery Beat
#   force-start retry loop  papered over deep depends_on chains in an 18-container
#                          cluster; the default stack is 7 containers now
#   workers/worker-status/  the two identical worker services became one; set
#   worker-logs/patch       WORKER_CONCURRENCY to scale it, `logs` to read it
#
# 從 1031 行縮減為單機部署實際需要的指令；移除的都是指向不存在的檔案、
# 或為了掩蓋 18 容器叢集啟動順序問題而存在的補丁。
#
set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Observability (SigNoz: ClickHouse + ZooKeeper + collector + 2 migrators) is an
# opt-in compose profile. `OBSERVABILITY=1 ./start.sh up` brings it up; the
# default stack leaves ~4-6GB of RAM unspent and falls back to structured logs.
# 預設不啟動 SigNoz；需要時 OBSERVABILITY=1 ./start.sh up。
if [ "${OBSERVABILITY:-0}" = "1" ]; then
    PROD_PROFILES="--profile observability"
    export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4317}"
else
    PROD_PROFILES=""
fi

PROD_COMPOSE="docker compose --project-name investment_advisor -f docker-compose.prod.yml ${PROD_PROFILES}"
PROD_CACHE="advisor_prod_cache"
PROD_DB="advisor_prod_db"
readonly REPORT_QUEUES=("report:daily:queue" "report:weekly:queue" "report:priority:queue")

# Core single-box stack. SigNoz and n8n are opt-in profiles and are deliberately
# absent — a healthy default deployment must report green without them.
# SigNoz 與 n8n 為選配 profile，預設健檢不要求它們。
readonly REQUIRED_PROD_CONTAINERS=(
    advisor_prod_api advisor_prod_ui advisor_prod_db advisor_prod_cache
    advisor_prod_beat advisor_prod_worker advisor_prod_gateway
)

readonly OBSERVABILITY_CONTAINERS=(
    signoz signoz-otel-collector signoz-clickhouse
)

function show_help {
    echo "investment-advisor — single-box control"
    echo ""
    echo "Usage: ./start.sh <command>"
    echo ""
    echo "  up            Build and start the stack (generates secrets on first run)."
    echo "  down          Stop the stack. Add --volumes to destroy data too."
    echo "  logs [svc]    Follow logs (all services, or one)."
    echo "  health        Check the deployment. Exits non-zero when unhealthy."
    echo "  migrate       Apply database migrations."
    echo "  backup        Dump the database and config to backups/."
    echo "  restore [id]  Restore database and config from a backup in backups/."
    echo "  upgrade       Pull, migrate, restart, and health-gate the result."
    echo "  wizard        Run the interactive onboarding and cost-profile wizard."
    echo "  tunnel        Start the ngrok tunnel (webhook endpoints only)."
    echo ""
    echo "Environment:"
    echo "  OBSERVABILITY=1        also run the SigNoz stack"
    echo "  WORKER_CONCURRENCY=N   Celery worker processes (default 4)"
    echo "  SKIP_BUILD=1           skip image builds on 'up'"
}

function redis_cmd {
    # Usage: redis_cmd <container> <redis args...>
    # 2026-07-11: prod redis requires auth (REDIS_PASSWORD in .env, security
    # hardening) — pass it so health checks stop reporting false NOAUTH errors.
    local pass=""
    if [ -f .env ]; then
        pass=$(grep -m1 '^REDIS_PASSWORD=' .env | cut -d= -f2-)
    fi
    if [ -n "$pass" ]; then
        docker exec "$1" redis-cli -a "$pass" --no-auth-warning "${@:2}" 2>/dev/null | tr -d '\r'
    else
        docker exec "$1" redis-cli "${@:2}" 2>/dev/null | tr -d '\r'
    fi
}

function check_env {
    if [ ! -f .env ]; then
        echo "Error: .env file not found! Copying .env.example..."
        cp .env.example .env
        echo "WARNING: Created default .env. Please edit it with your API keys!"
    fi

    # Both compose files bind-mount n8n_workflow_template.json into the n8n
    # container read-only. The file is gitignored, so a fresh `git clone`
    # doesn't have it — and when a bind source is missing Docker silently
    # creates a root-owned DIRECTORY at that path, which then mounts as a
    # directory at /home/node/template.json and quietly breaks the import.
    # Seeding from the tracked example prevents both halves of that.
    #
    # 兩個 compose 都會把 n8n_workflow_template.json 唯讀掛進 n8n 容器；該檔被
    # gitignore，全新 clone 不會有它，而 Docker 在 bind 來源不存在時會自動建立一個
    # root 所有的「目錄」，導致容器裡掛到的是目錄、匯入靜默失效。
    # Only needed for the optional `n8n` profile — n8n's own schedules moved
    # into Celery Beat, so a default deployment never reads this file.
    # 僅選配的 n8n profile 需要；預設部署不會用到。
    if [ "${N8N:-0}" = "1" ] && [ ! -e n8n_workflow_template.json ] && [ -f n8n_workflow_template.example.json ]; then
        cp n8n_workflow_template.example.json n8n_workflow_template.json
        echo "  ✓ Seeded n8n_workflow_template.json from the example."
    elif [ -d n8n_workflow_template.json ]; then
        echo "  ⚠️  n8n_workflow_template.json is a DIRECTORY — Docker auto-created it"
        echo "      from a missing bind source. Remove it manually:"
        echo "        sudo rm -rf n8n_workflow_template.json"
        echo "      then re-run. n8n will not import correctly until you do."
    fi
}

function ensure_secret {
    local var_name="$1"
    local generator="${2:-urlsafe}"
    local current=""
    if [ -f .env ]; then
        current=$(grep -m1 "^${var_name}=" .env | cut -d= -f2-)
    fi
    case "$current" in
        ""|*REPLACE_WITH*|*"<replace-with"*|*your-super-secret-key-for-jwt-signing*)
            current=""
            ;;
    esac
    if [ -n "$current" ]; then
        return 0
    fi

    local new_value=""
    if [ "$generator" = "fernet" ]; then
        new_value=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null)
    else
        new_value=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null)
    fi
    if [ -z "$new_value" ]; then
        echo "  ⚠️  Could not auto-generate ${var_name} (python3/cryptography unavailable) — set it manually in .env"
        return 1
    fi

    if grep -q "^${var_name}=" .env 2>/dev/null; then
        sed -i.bak "s|^${var_name}=.*|${var_name}=${new_value}|" .env && rm -f .env.bak
    else
        echo "${var_name}=${new_value}" >> .env
    fi
    echo "  ✓ Generated ${var_name}"
}

function ensure_literal {
    # Like ensure_secret, but writes a fixed value instead of a generated one.
    local var_name="$1" value="$2" current=""
    [ -f .env ] && current=$(grep -m1 "^${var_name}=" .env | cut -d= -f2-)
    [ -n "$current" ] && return 0
    echo "${var_name}=${value}" >> .env
    echo "  ✓ Set ${var_name}=${value}"
}

function guard_encryption_keys {
    # APP_SECRET_KEY and LLM_CREDENTIAL_KEY encrypt rows *inside Postgres*
    # (settings values, llm_providers.encrypted_api_key). If the database volume
    # survives but .env does not — a lost file, a fresh clone over an old
    # volume — regenerating them turns every stored eToro and LLM credential
    # into undecryptable garbage, and the failure shows up later as
    # "credential invalid", not as an error here.
    #
    # 這兩把金鑰加密的是資料庫內容；DB volume 還在而 .env 不見時重新產生金鑰，
    # 會讓既有 eToro / LLM 憑證永久無法解密，且錯誤要很久以後才浮現。
    local db_volume_exists=0
    if docker volume inspect investment_advisor_advisor_db_data >/dev/null 2>&1 \
       || docker volume inspect advisor_db_data >/dev/null 2>&1; then
        db_volume_exists=1
    fi
    [ "$db_volume_exists" = "0" ] && return 0

    local missing=""
    for key in APP_SECRET_KEY LLM_CREDENTIAL_KEY; do
        local current=""
        [ -f .env ] && current=$(grep -m1 "^${key}=" .env | cut -d= -f2-)
        case "$current" in ""|*REPLACE_WITH*|*"<replace-with"*) missing="$missing $key" ;; esac
    done
    [ -z "$missing" ] && return 0

    echo ""
    echo "❌ Refusing to bootstrap."
    echo "   An existing database volume was found, but these keys are missing from .env:"
    echo "  ${missing}"
    echo ""
    echo "   They decrypt data already stored in that database. Generating new ones"
    echo "   would permanently orphan your saved eToro and LLM provider credentials."
    echo ""
    echo "   Restore the original values into .env (check backups/ or .env.bak-*),"
    echo "   or, if you accept losing those stored credentials, start from a clean"
    echo "   database:  ./start.sh clean   (destroys the volume), then re-run."
    return 1
}

function seed_safe_defaults {
    # Runs inside the API container so it uses the same DB credentials and the
    # same encryption keys the application will use.
    #
    # Two things happen here:
    #   1. the owner row is created under a Postgres advisory lock, BEFORE the
    #      workers/beat start racing for it;
    #   2. auto-trading is pinned off for a fresh install.
    # 在 API 容器內執行：先建立擁有者（advisory lock 序列化），再關閉自動交易。
    docker exec advisor_prod_api python -c "
import sys
from src.config.owner import get_owner_id
owner = get_owner_id()
print(f'  ✓ Owner: {owner}')

from src.services.settings_service import SettingsService
svc = SettingsService(user_id=owner)
existing = svc.get_setting('ai_trading_enabled')
if existing is None:
    svc.save_settings_bulk({'ai_trading_enabled': False})
    print('  ✓ ai_trading_enabled=false (auto-trading held off on a fresh install)')
else:
    print(f'  · ai_trading_enabled already set to {existing!r} — left untouched')
" || echo "  ⚠️  Could not seed defaults — run './start.sh health' and check the API container logs."
}

function fix_redis_queues {
    local cache_container=${1:-$PROD_CACHE}

    if ! docker ps --format '{{.Names}}' | grep -q "$cache_container"; then
        return 0
    fi

    echo "Checking Redis queue key types..."
    local fixed=0

    for queue in "${REPORT_QUEUES[@]}"; do
        local ktype
        ktype=$(redis_cmd "$cache_container" type "$queue")
        if [ "$ktype" = "list" ]; then
            echo "  Fixing $queue (was list, expected zset)..."
            redis_cmd "$cache_container" del "$queue" >/dev/null
            fixed=$((fixed + 1))
        fi
    done

    if [ $fixed -gt 0 ]; then
        echo "  Fixed $fixed queue key(s)."
    else
        echo "  All queue keys OK."
    fi
}

function wait_for_api {
    local api_port=8001
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        api_port=8000
    fi
    local api_url=${1:-"http://localhost:${api_port}/health"}
    local max_wait=${2:-120}
    local waited=0

    echo "Waiting for API to be healthy ($api_url)..."
    while [ $waited -lt $max_wait ]; do
        if curl -sf "$api_url" >/dev/null 2>&1; then
            echo "  API ready (${waited}s)"
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
        printf "."
    done
    echo ""
    echo "  WARNING: API did not become healthy within ${max_wait}s"
    return 1
}

function show_health {
    # Returns 0 when everything checks out, non-zero otherwise, so cold-start
    # verification can gate on it: `./start.sh health && echo GREEN`. Human
    # output is a strict superset of what it printed before.
    #
    # Callers inside cmd_up/cmd_upgrade invoke this as `show_health || true` —
    # under `set -e` a red health check would otherwise abort the command
    # mid-way and skip the steps after it.
    # 內部呼叫加 || true，否則 set -e 下健檢失敗會中斷後續步驟。
    local failed=0
    echo "=== System Health ==="

    echo ""
    echo "Containers:"
    docker ps --filter "name=advisor_prod" --format "  {{.Names}}: {{.Status}}" 2>/dev/null
    docker ps --filter "name=signoz" --format "  {{.Names}}: {{.Status}}" 2>/dev/null

    local running
    running=$(docker ps --format '{{.Names}}')
    local c
    local _required=("${REQUIRED_PROD_CONTAINERS[@]}")
    if [ "${OBSERVABILITY:-0}" = "1" ]; then
        _required+=("${OBSERVABILITY_CONTAINERS[@]}")
    fi
    for c in "${_required[@]}"; do
        if ! printf '%s\n' "$running" | grep -qx "$c"; then
            echo "  ✗ MISSING: $c"
            failed=$((failed + 1))
        fi
    done

    local api_port=8001
    if printf '%s\n' "$running" | grep -qx "advisor_prod_api"; then
        api_port=8000
    fi

    echo ""
    echo "API:"
    if curl -sf "http://localhost:${api_port}/health" >/dev/null 2>&1; then
        echo "  http://localhost:${api_port}/health  OK"
    else
        echo "  http://localhost:${api_port}/health  FAIL"
        failed=$((failed + 1))
    fi

    echo ""
    echo "Gateway:"
    if curl -sf -o /dev/null "http://127.0.0.1:8088/" 2>/dev/null; then
        echo "  http://127.0.0.1:8088/  OK"
    else
        echo "  http://127.0.0.1:8088/  FAIL"
        failed=$((failed + 1))
    fi

    # n8n is an optional connector hub now (compose profile `n8n`), not part of
    # the product. Its three schedules moved into Celery Beat, so a stopped n8n
    # is a normal state and must not fail the health gate. Only report on it
    # when it is actually running.
    # n8n 已降為選配；停用是正常狀態，僅在實際執行時才回報。
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_n8n"; then
        echo ""
        echo "n8n (optional):"
        if curl -sf "http://localhost:5678/healthz" >/dev/null 2>&1; then
            echo "  http://localhost:5678/healthz  OK"
        else
            echo "  http://localhost:5678/healthz  FAIL"
            failed=$((failed + 1))
        fi
    fi

    echo "Redis Queues:"
    if printf '%s\n' "$running" | grep -qx "$PROD_CACHE"; then
        for queue in "${REPORT_QUEUES[@]}"; do
            local ktype
            ktype=$(redis_cmd "$PROD_CACHE" type "$queue")
            if [ "$ktype" = "none" ]; then
                echo "  $queue: empty (ok)"
            elif [ "$ktype" = "zset" ]; then
                local depth
                depth=$(redis_cmd "$PROD_CACHE" zcard "$queue")
                echo "  $queue: $depth jobs (zset ok)"
            else
                echo "  $queue: WRONG TYPE=$ktype (run: ./start.sh fix-redis)"
                failed=$((failed + 1))
            fi
        done
        local dlq_depth
        dlq_depth=$(redis_cmd "$PROD_CACHE" llen "report:dlq:failed")
        echo "  report:dlq:failed: $dlq_depth failed jobs"   # informational, not a gate
    else
        echo "  Redis not running"
        failed=$((failed + 1))
    fi

    # This block used to hardcode database "portfolio", which does not exist
    # (POSTGRES_DB=advisor_prod, docker-compose.prod.yml), so every query
    # silently errored — and the `|| echo` fallback never fired either, because
    # the pipeline's exit status came from sed rather than psql.
    # An empty result set is normal (report_jobs can legitimately have 0 rows);
    # only a psql *error* counts as a failure.
    # 原本寫死的資料庫名 portfolio 並不存在，查詢一直靜默失敗，而 || echo 也永遠
    # 不會觸發（管線的 exit status 來自 sed）。空結果是正常的，只有 psql 出錯才算失敗。
    echo ""
    echo "DB Job Status:"
    local db_name="advisor_prod"
    if [ -f .env ]; then
        db_name=$(grep -m1 '^DB_NAME=' .env | cut -d= -f2-)
        db_name="${db_name:-advisor_prod}"
    fi
    local job_rows
    if job_rows=$(docker exec "$PROD_DB" psql -U "${DB_USER:-postgres}" -d "$db_name" -t -c \
            "SELECT status, COUNT(*) FROM report_jobs GROUP BY status ORDER BY count DESC;" 2>&1); then
        printf '%s\n' "$job_rows" | sed 's/^/  /'
    else
        echo "  ✗ report_jobs query failed on database '${db_name}'"
        failed=$((failed + 1))
    fi

    echo ""
    if [ "$failed" -eq 0 ]; then
        echo "=== HEALTH: PASS ==="
        return 0
    fi
    echo "=== HEALTH: FAIL (${failed} check(s)) ==="
    return 1
}

function run_migrations {
    echo "=== Running Database Migrations & Alignment ==="
    check_env
    
    # 1. Detect environment by running containers
    local target_container=""
    local target_db=""
    
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        echo "Detected: Production Environment"
        target_container="advisor_prod_api"
        target_db="advisor_prod_db"
    elif docker ps --format '{{.Names}}' | grep -q "investment_advisor_mcp"; then
        echo "Detected: Development Environment"
        target_container="investment_advisor_mcp"
        target_db="investment_advisor_db"
    else
        echo "❌ No running backend container detected. Please start the system first (./start.sh dev|prod)."
        exit 1
    fi

    # 2026-07-14: removed a blind `DELETE FROM alembic_version; INSERT ...
    # 'merge_heads_001'` stamp that ran here unconditionally before every
    # upgrade. It targeted the wrong database name ("portfolio" — prod's
    # actual DB is "advisor_prod"/"investment_advisor_db"), so it silently
    # no-op'd via the swallowed `|| true` and never actually did anything on
    # this codebase's real databases. Had the name been correct, it would
    # have blindly rewound alembic_version to an old revision on every run,
    # which is exactly the kind of drift that made prod's tracked version
    # (005) diverge from its real applied schema (011) — fixed by hand via
    # `alembic stamp head` after verifying every intervening table/column/
    # constraint actually existed. The alembic history already has a single
    # head (the two `merge_heads_*` revisions already reconciled the old
    # multi-head branches) — `alembic upgrade head` alone is correct and
    # safe (no-op if already current).
    echo "Upgrading schema in $target_container..."
    docker exec "$target_container" alembic upgrade head
    echo "✅ Migration Successful."
}

function start_tunnel {
    # The tunnel now points at the webhook-only nginx vhost (port 8080), which
    # publishes /webhook/* and /callback/* and 404s everything else. Those
    # endpoints carry their own credentials — X-API-Key for webhooks, provider
    # signatures for callbacks — so the tunnel no longer depends on ADMIN_TOKEN
    # to be safe, and the dashboard stays loopback-only either way.
    #
    # What is still checked: that nobody has repointed ngrok back at :80.
    #
    # 通道已改指向 webhook 專用 vhost（:8080），只公開自帶憑證的端點；
    # 此處仍檢查是否有人把 ngrok 改回 :80。
    if grep -qE '^\s*command:\s*http .*advisor_prod_gateway:80\s*$' docker-compose.prod.yml; then
        echo "❌ Refusing to start the tunnel."
        echo "   docker-compose.prod.yml points ngrok at advisor_prod_gateway:80,"
        echo "   which publishes the unauthenticated dashboard and the whole /api/"
        echo "   surface to the internet. It must target :8080 (webhook-only vhost)."
        return 1
    fi

    if ! grep -q "listen 8080;" infra/nginx/nginx.conf; then
        echo "❌ Refusing to start the tunnel: the webhook-only vhost (listen 8080)"
        echo "   is missing from infra/nginx/nginx.conf."
        return 1
    fi

    echo "✓ Tunnel targets the webhook-only vhost. Starting ngrok."
    $PROD_COMPOSE --profile tunnel up -d ngrok
    echo ""
    echo "  Exposed publicly:  /webhook/*  (X-API-Key)   /callback/*  (signed)"
    echo "  NOT exposed:       dashboard, /api/*, /docs  — loopback only"
}

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

function cmd_up {
    echo "=== Starting investment-advisor ==="
    check_env

    guard_encryption_keys || return 1

    echo "Ensuring secrets (only fills placeholders, never overwrites real values)..."
    ensure_secret "LLM_CREDENTIAL_KEY" "fernet"
    ensure_secret "APP_SECRET_KEY" "fernet"
    ensure_secret "DB_PASS" "urlsafe"
    ensure_secret "REDIS_PASSWORD" "urlsafe"
    ensure_literal "DB_USER" "postgres"
    ensure_literal "DB_NAME" "advisor_prod"

    # TRADING_MODE=paper is NOT a safe default here: the eToro token has no demo
    # permission, so paper mode makes every broker call return
    # InsufficientPermissions — a full stop, not a degraded mode (AGENTS.md
    # 2026-08-23). The brake is the ai_trading_enabled setting, applied by
    # seed_safe_defaults below.
    # paper 模式在本專案是全停而非降級；安全預設用 ai_trading_enabled=false。

    if [ "${SKIP_BUILD:-0}" != "1" ]; then
        echo "Building images..."
        $PROD_COMPOSE build
    fi

    echo "Starting containers..."
    $PROD_COMPOSE up -d --remove-orphans

    wait_for_api || true
    run_migrations
    seed_safe_defaults

    echo ""
    show_health || true
    echo ""
    echo "======================================================================"
    echo "  Dashboard:  http://127.0.0.1:8088   (no login required)"
    echo ""
    echo "  Next: Settings -> configure an LLM provider (OpenRouter key, or a"
    echo "  local Ollama endpoint) before the council/sentinel agents can run."
    echo "======================================================================"
}

function cmd_down {
    if [ "${1:-}" = "--volumes" ]; then
        echo "⚠️  Destroying containers AND data volumes (database, redis, n8n)."
        printf "Type 'destroy' to confirm: "
        read -r reply
        [ "$reply" = "destroy" ] || { echo "Aborted."; return 1; }
        $PROD_COMPOSE --profile observability --profile n8n --profile tunnel down --volumes --remove-orphans
    else
        $PROD_COMPOSE --profile observability --profile n8n --profile tunnel down --remove-orphans
    fi
}

function cmd_logs {
    if [ -n "${1:-}" ]; then
        $PROD_COMPOSE logs -f --tail=200 "$1"
    else
        $PROD_COMPOSE logs -f --tail=100
    fi
}

function cmd_backup {
    local ts
    ts=$(date +%Y%m%d-%H%M%S)
    mkdir -p backups

    echo "Dumping database..."
    local db_name="advisor_prod"
    if [ -f .env ]; then
        db_name=$(grep -m1 '^DB_NAME=' .env | cut -d= -f2-)
        db_name="${db_name:-advisor_prod}"
    fi

    docker exec "$PROD_DB" pg_dump -U "${DB_USER:-postgres}" "$db_name" \
        > "backups/db-${ts}.sql"
    local db_size
    db_size=$(du -h "backups/db-${ts}.sql" | cut -f1)
    echo "  ✓ backups/db-${ts}.sql (${db_size})"

    # config/ holds workflow, agent and settings manifests that the UI writes —
    # product state, not source. A database dump alone would not restore it.
    tar -czf "backups/config-${ts}.tar.gz" config/ 2>/dev/null || true
    echo "  ✓ backups/config-${ts}.tar.gz"

    if [ -f .env ]; then
        cp .env "backups/env-${ts}.bak"
        echo "  ✓ backups/env-${ts}.bak"
    fi

    # Write backup manifest with git SHA and metadata
    local git_sha="unknown"
    if command -v git >/dev/null 2>&1 && [ -d .git ]; then
        git_sha=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    fi
    cat <<EOF > "backups/manifest-${ts}.json"
{
  "timestamp": "${ts}",
  "database": "${db_name}",
  "git_commit": "${git_sha}",
  "files": {
    "db": "db-${ts}.sql",
    "config": "config-${ts}.tar.gz",
    "env": "env-${ts}.bak"
  }
}
EOF
    echo "  ✓ backups/manifest-${ts}.json"
    echo "✅ Backup complete. (ID: ${ts})"
}

function cmd_restore {
    local target="${1:-}"
    if [ -z "$target" ]; then
        # Auto-detect latest backup manifest
        local latest_manifest
        latest_manifest=$(ls -1t backups/manifest-*.json 2>/dev/null | head -n1 || true)
        if [ -n "$latest_manifest" ]; then
            target=$(basename "$latest_manifest" | sed 's/manifest-//' | sed 's/\.json//')
            echo "No backup ID specified. Found latest backup: ${target}"
        else
            echo "❌ No backups found in backups/ directory."
            return 1
        fi
    fi

    # Strip prefixes/suffixes if operator provided a full path
    target=$(echo "$target" | sed 's/.*db-//' | sed 's/.*config-//' | sed 's/.*manifest-//' | sed 's/\..*//')

    local db_file="backups/db-${target}.sql"
    local config_file="backups/config-${target}.tar.gz"

    if [ ! -f "$db_file" ]; then
        echo "❌ Database backup file not found: $db_file"
        return 1
    fi

    echo "⚠️  WARNING: Restoring backup '${target}' will OVERWRITE current database and config/ state!"
    printf "Type 'restore' to confirm: "
    read -r reply
    [ "$reply" = "restore" ] || { echo "Aborted."; return 1; }

    local db_name="advisor_prod"
    if [ -f .env ]; then
        db_name=$(grep -m1 '^DB_NAME=' .env | cut -d= -f2-)
        db_name="${db_name:-advisor_prod}"
    fi

    echo "Restoring database from ${db_file}..."
    docker exec -i "$PROD_DB" psql -U "${DB_USER:-postgres}" -d "$db_name" < "$db_file"
    echo "  ✓ Database restored."

    if [ -f "$config_file" ]; then
        echo "Restoring config/ from ${config_file}..."
        tar -xzf "$config_file"
        echo "  ✓ config/ restored."
    fi

    if [ -f "backups/env-${target}.bak" ]; then
        echo "  · Note: backups/env-${target}.bak preserved (not automatically overwriting active .env)."
    fi

    echo "Restarting services to apply restored configuration..."
    $PROD_COMPOSE restart advisor_prod_api advisor_prod_beat advisor_prod_worker
    wait_for_api || true
    echo "✅ Restore complete."
}

function cmd_upgrade {
    echo "=== Upgrading investment-advisor ==="
    cmd_backup

    if command -v git >/dev/null 2>&1 && [ -d .git ]; then
        echo "Pulling latest code changes via git..."
        if ! git pull --ff-only; then
            echo "⚠️  git pull --ff-only failed (local changes detected). Please resolve manually or stash."
            return 1
        fi
    fi

    echo "Rebuilding images..."
    $PROD_COMPOSE build

    echo "Restarting containers..."
    $PROD_COMPOSE up -d --remove-orphans
    wait_for_api || true
    run_migrations

    echo ""
    if show_health; then
        echo "✅ Upgrade complete and healthy."
    else
        echo ""
        echo "⚠️  Upgrade finished but the health check is RED."
        echo "   Inspect with './start.sh logs', or restore with './start.sh restore ${ts}'."
        return 1
    fi
}

function cmd_wizard {
    echo "=== Running Onboarding Wizard ==="
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        docker exec -it advisor_prod_api python scripts/onboarding_wizard.py "$@"
    else
        python3 scripts/onboarding_wizard.py "$@"
    fi
}

case "${1:-up}" in
    up|start|prod|selfhost)
        cmd_up
        ;;
    down|stop)
        cmd_down "${2:-}"
        ;;
    logs)
        cmd_logs "${2:-}"
        ;;
    health)
        show_health
        ;;
    migrate)
        run_migrations
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore "${2:-}"
        ;;
    upgrade)
        cmd_upgrade
        ;;
    wizard)
        cmd_wizard "${@:2}"
        ;;
    tunnel)
        start_tunnel
        ;;
    fix-redis)
        fix_redis_queues "$PROD_CACHE"
        ;;
    *)
        show_help
        ;;
esac
