#!/bin/bash
# start.sh - Unified Orchestration Entry Point for Investment Advisor Platform
# v4.2: Added Redis queue sanity, health wait, and post-deploy verification.

set -e

# Support for environments where docker is in /usr/local/bin
export PATH=$PATH:/usr/local/bin:/usr/bin:/bin

# --- Helper Functions ---
function show_help {
    echo "Quantum AI Platform - Operational Control v4.2 (Enterprise)"
    echo "Usage: ./start.sh [command]"
    echo ""
    echo "Commands:"
    echo "  health         Show live status of all services, queues, and DB."
    echo "  fix-redis      Fix Redis queue key types (list→zset). Run if WRONGTYPE errors appear."
    echo ""
    echo "  dev (default)  Deploy Local Development environment (Docker Compose)."
    echo "                 - Includes SigNoz APM, n8n, and Debugging tools."
    echo "                 - UI: http://localhost:3001   API: http://localhost:8001"
    echo "                 - (dev nginx publishes no host port — reach services directly)"
    echo ""
    echo "  prod           Deploy Hardened Production cluster (B2C SaaS Mode)."
    echo "                 - Includes Worker Pool for async report generation."
    echo "                 - Security hardened, monitoring active."
    echo "                 - If cluster already running: hot-restarts code services only (fast)."
    echo "                 - Gateway: http://127.0.0.1:8088"
    echo ""
    echo "  selfhost       One-command self-host bootstrap (new installs)."
    echo "                 - Auto-generates missing secrets (JWT/Fernet/DB/Redis) into .env."
    echo "                 - Defaults TRADING_MODE=paper (no real orders until you opt in)."
    echo "                 - Deploys the full cluster + runs migrations."
    echo "                 - Safe to re-run: never overwrites secrets you've already set."
    echo ""
    echo "  workers [N]    Scale worker pool to N instances (default: 2)."
    echo "                 - Starts workers for async report processing."
    echo "                 - Must run after: ./start.sh prod"
    echo ""
    echo "  worker-status  Check health status of worker pool."
    echo ""
    echo "  worker-logs    Tail logs from all worker containers."
    echo ""
    echo "  stop|clean     Stop all containers and perform deep cleanup."
    echo ""
    echo "  migrate        Align database heads and run all migrations (Auto-detect Env)."
    echo "                 - Fixes 'Multiple Heads' and syncs schema."
    echo ""
    echo "  patch          Production Hot-Patch (No downtime UI/API update)."
    echo ""
    echo "  ollama         Deploy Local Ollama service (requires pre-downloaded models)."
    echo ""
    echo "  k8s            Deploy to Kubernetes (Minikube / Cloud)."
    echo ""
    echo "Environment flags (set inline or in .env):"
    echo "  SKIP_N8N_IMPORT=1   Skip the n8n workflow auto-import on cold start."
    echo "                      The import UPSERTs onto workflow ID 1 and will"
    echo "                      overwrite edits made in the n8n UI."
    echo "                      e.g. SKIP_N8N_IMPORT=1 ./start.sh prod"
}

PROD_COMPOSE="docker compose --project-name investment_advisor -f docker-compose.prod.yml"
PROD_CACHE="advisor_prod_cache"
PROD_DB="advisor_prod_db"
readonly REPORT_QUEUES=("report:daily:queue" "report:weekly:queue" "report:priority:queue")

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
    if [ ! -e n8n_workflow_template.json ] && [ -f n8n_workflow_template.example.json ]; then
        cp n8n_workflow_template.example.json n8n_workflow_template.json
        echo "  ✓ Seeded n8n_workflow_template.json from the example."
    elif [ -d n8n_workflow_template.json ]; then
        echo "  ⚠️  n8n_workflow_template.json is a DIRECTORY — Docker auto-created it"
        echo "      from a missing bind source. Remove it manually:"
        echo "        sudo rm -rf n8n_workflow_template.json"
        echo "      then re-run. n8n will not import correctly until you do."
    fi
}

# 2026-07-14 (open-source Phase 1 — self-host one-click bootstrap):
# generate a real secret for VAR_NAME in .env if it is missing OR still a
# placeholder from .env.example (REPLACE_WITH_..., <replace-with-...>, or
# the literal known-default JWT secret). Never touches an already-real
# value — idempotent and safe to call on every `selfhost` run, including
# against an existing deployment that already set its own secrets.
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

function selfhost_bootstrap {
    echo "=== Self-Host First-Run Bootstrap ==="
    check_env

    echo "Ensuring required secrets are set (only fills placeholders, never overwrites real values)..."
    ensure_secret "JWT_SECRET" "urlsafe"
    ensure_secret "LLM_CREDENTIAL_KEY" "fernet"
    ensure_secret "APP_SECRET_KEY" "fernet"
    ensure_secret "DB_PASS" "urlsafe"
    ensure_secret "REDIS_PASSWORD" "urlsafe"

    if ! grep -q "^TRADING_MODE=" .env 2>/dev/null; then
        echo "TRADING_MODE=paper" >> .env
        echo "  ✓ Set TRADING_MODE=paper (self-host safe default — no real trades until you explicitly opt in)"
    fi

    echo ""
    echo "Deploying production cluster..."
    deploy_prod

    echo ""
    echo "Applying database migrations..."
    run_migrations

    echo ""
    echo "======================================================================"
    echo "✅ Self-host bootstrap complete."
    echo ""
    echo "  Dashboard:     http://127.0.0.1:8088"
    echo "  Trading mode:  paper (no real orders will be placed)"
    echo ""
    echo "  Next step: open the dashboard → Settings → configure an LLM"
    echo "  provider (OpenRouter API key, or a local Ollama endpoint) before"
    echo "  the council/sentinel agents can run. Nothing else is required to"
    echo "  explore the platform safely."
    echo "======================================================================"
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

# Containers that must be up for the stack to count as green. SigNoz is
# included deliberately: it ships in the same compose project via the
# `include:` at the top of docker-compose.prod.yml, and the old
# `name=advisor_prod` filter missed it entirely.
# 這些容器都起來才算綠燈；SigNoz 也算在內——它經由 compose 的 include 屬於同一個
# project，但舊的 name=advisor_prod 過濾器完全看不到它。
readonly REQUIRED_PROD_CONTAINERS=(
    advisor_prod_api advisor_prod_ui advisor_prod_db advisor_prod_cache
    advisor_prod_n8n advisor_prod_beat advisor_prod_worker_1
    advisor_prod_worker_2 advisor_prod_gateway
    signoz signoz-otel-collector signoz-clickhouse
)

function show_health {
    # Returns 0 when everything checks out, non-zero otherwise, so cold-start
    # verification can gate on it: `./start.sh health && echo GREEN`. Human
    # output is a strict superset of what it printed before.
    #
    # The two internal callers in deploy_prod invoke this as `show_health ||
    # true` — under `set -e` a failing health check would otherwise abort the
    # deploy, and worse, make selfhost_bootstrap skip run_migrations.
    # 回傳 exit code 以便自動化把關；deploy_prod 內部呼叫加 || true，否則 set -e
    # 下健檢失敗會炸掉部署，甚至讓 selfhost 跳過 run_migrations。
    local failed=0
    echo "=== System Health ==="

    echo ""
    echo "Containers:"
    docker ps --filter "name=advisor_prod" --format "  {{.Names}}: {{.Status}}" 2>/dev/null
    docker ps --filter "name=signoz" --format "  {{.Names}}: {{.Status}}" 2>/dev/null

    local running
    running=$(docker ps --format '{{.Names}}')
    local c
    for c in "${REQUIRED_PROD_CONTAINERS[@]}"; do
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

    # NOTE: /rest/health — which scripts/health_check_deep.sh:37 probes — is a
    # 404 on n8n 2.x and has always reported "unavailable". /healthz is the
    # live endpoint. /rest/executions needs an auth cookie, so workflow state
    # is read through the CLI instead.
    # 註：health_check_deep.sh 用的 /rest/health 在 n8n 2.x 是 404，一直都測不到；
    # /healthz 才是活的端點。
    echo ""
    echo "n8n:"
    if curl -sf "http://localhost:5678/healthz" >/dev/null 2>&1; then
        echo "  http://localhost:5678/healthz  OK"
        if docker exec advisor_prod_n8n n8n list:workflow --active=true --onlyId 2>/dev/null \
                | tr -d '\r' | grep -qx "1"; then
            echo "  workflow 1: ACTIVE"
        else
            echo "  workflow 1: NOT ACTIVE (import:workflow deactivates by default on"
            echo "              n8n 2.x — re-import with --activeState=fromJson, or"
            echo "              toggle it back on in the UI)"
            failed=$((failed + 1))
        fi
    else
        echo "  http://localhost:5678/healthz  FAIL"
        failed=$((failed + 1))
    fi

    echo ""
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

function patch_prod {
    echo "=== Mode: Hot-Patching Production Cluster ==="
    check_env
    $PROD_COMPOSE build frontend mcp_server
    $PROD_COMPOSE up -d --no-deps frontend mcp_server
    echo "✅ Patch Applied Successfully"
}

function scale_workers {
    local worker_count=${1:-2}
    echo "=== Scaling Worker Pool to $worker_count instances ==="
    check_env
    source .env 2>/dev/null || true
    
    # Ensure prod cluster is running
    if ! docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        echo "❌ Production cluster not running. Start with: ./start.sh prod"
        exit 1
    fi
    
    # Get worker image name from compose build
    echo "Building worker image..."
    $PROD_COMPOSE build worker_1 2>/dev/null || true
    
    # Get the built image name
    local worker_image
    worker_image=$(docker inspect --format='{{.Config.Image}}' advisor_prod_worker_1 2>/dev/null || echo "investment_advisor-worker_1:latest")

    echo "Starting/updating worker pool..."
    
    # Stop old workers first
    for i in 1 2 3 4; do
        docker stop "advisor_prod_worker_$i" 2>/dev/null || true
        docker rm "advisor_prod_worker_$i" 2>/dev/null || true
    done
    
    # Start new workers with docker run (redis:// URL and correct env vars)
    for i in $(seq 1 $worker_count); do
        echo "  Starting Worker $i..."
        docker run -d \
            --name "advisor_prod_worker_$i" \
            --network "advisor-net" \
            --restart always \
            -u root \
            --env-file .env \
            -e WORKER_ID="worker-$i" \
            -e WORKER_CONCURRENCY=2 \
            -e NODE_ENV=production \
            -e QUEUE_REDIS_URL="redis://advisor_prod_cache:6379/0" \
            -e OTEL_SERVICE_NAME="worker_${i}_prod" \
            -e OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317" \
            -e OTEL_EXPORTER_OTLP_PROTOCOL="grpc" \
            -v "./src/infrastructure:/workspace/src/infrastructure:ro" \
            -v "./src/workflow:/workspace/src/workflow:ro" \
            -v "./src/services:/workspace/src/services:ro" \
            -v "./src/agents:/workspace/src/agents:ro" \
            -v "./services/scheduler:/workspace/services/scheduler:ro" \
            "$worker_image" \
            python services/scheduler/src/app.py --mode worker --concurrency 2
        
        echo "  ✅ Worker $i started"
    done
    
    echo ""
    echo "✅ Worker pool scaled to $worker_count instances"
    worker_status
}

function worker_status {
    echo "=== Worker Pool Status ==="
    
    if ! docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        echo "❌ Production cluster not running"
        return 1
    fi
    
    echo ""
    echo "Worker Containers:"
    docker ps --filter "name=advisor_prod_worker" --format "table {{.Names}}\tSTATUS"
    
    echo ""
    echo "Queue Status (Redis):"
    redis_cmd "$PROD_CACHE" ZCARD report:daily:queue | sed 's/^/  Daily queue depth: /'

    echo ""
    echo "Database Job Status:"
    docker exec "$PROD_DB" psql -U postgres portfolio -c \
        "SELECT status, COUNT(*) as count FROM report_jobs GROUP BY status ORDER BY count DESC;" \
        2>/dev/null | tail -n +3 | sed 's/^/  /'
}

function worker_logs {
    if ! docker ps --filter "name=advisor_prod_worker" --quiet | head -1 >/dev/null; then
        echo "❌ No worker containers running"
        exit 1
    fi
    
    echo "=== Worker Pool Logs ==="
    echo "(Press Ctrl+C to stop)"
    docker logs -f $(docker ps --filter "name=advisor_prod_worker" --quiet)
}

function backup_n8n_workflow {
    # Export a workflow before import:workflow upserts over it.
    #
    # n8n has NO other backup coverage anywhere: it keeps everything in the
    # advisor_n8n_data volume (its own SQLite plus an auto-generated encryption
    # key), and scripts/backup_db.sh only pg_dumps Postgres. Losing a
    # hand-tuned workflow is unrecoverable, so 15 lines is cheap insurance.
    #
    # Silent no-op on a genuine first cold start, where there is nothing to
    # export yet.
    #
    # n8n 目前零備份覆蓋：它的資料全在 advisor_n8n_data（自帶 SQLite 與自動產生
    # 的加密金鑰），而 backup_db.sh 只 dump Postgres。手工調過的 workflow 一旦被
    # 覆寫就救不回來。真正首次冷啟動時沒東西可備份，直接跳過。
    local n8n_container=$1
    local wf_id="${2:-1}"

    if ! docker exec "$n8n_container" n8n list:workflow --onlyId 2>/dev/null \
            | tr -d '\r' | grep -qx "$wf_id"; then
        echo "  (no existing workflow ${wf_id} — nothing to back up)"
        return 0
    fi

    mkdir -p backups
    local ts
    ts=$(date +%Y%m%d_%H%M%S)
    local tmp="/tmp/n8n_wf_${wf_id}_${ts}.json"
    local out="backups/n8n_workflow_${wf_id}_${ts}.json"

    if docker exec "$n8n_container" n8n export:workflow --id="$wf_id" --pretty \
             --output="$tmp" >/dev/null 2>&1 \
       && docker cp "$n8n_container:$tmp" "$out" >/dev/null 2>&1 \
       && [ -s "$out" ]; then
        docker exec "$n8n_container" rm -f "$tmp" 2>/dev/null || true
        echo "  ✓ Backed up n8n workflow ${wf_id} → ${out}"
        find backups -name "n8n_workflow_*.json" -mtime +30 -delete 2>/dev/null || true
        return 0
    fi

    rm -f "$out" 2>/dev/null || true
    echo "  ⚠️  Could not export n8n workflow ${wf_id}."
    return 1
}

function import_n8n_workflow {
    local db_container=$1
    local n8n_container=$2

    # SKIP_N8N_IMPORT — opt out of the destructive re-import.
    #
    # The template carries a top-level "id": "1", so `n8n import:workflow` is an
    # UPSERT onto workflow 1: anything edited in the n8n UI is overwritten. On
    # n8n 2.x it is worse than that — `--activeState` defaults to false, so
    # every cold start also silently DEACTIVATES the workflow.
    #
    # Read the process environment first, then .env, using the same
    # non-sourcing idiom as redis_cmd/ensure_secret. Deliberately placed BEFORE
    # the `source .env` below: sourcing would leak TELEGRAM_BOT_TOKEN, DB_PASS
    # and everything else into the remainder of the run (deploy_prod continues
    # on to show_health after this returns).
    #
    # 模板帶有頂層 "id": "1"，所以 import 是對 workflow 1 的 UPSERT，UI 上的修改
    # 會被覆寫；n8n 2.x 的 --activeState 預設 false，還會順手把它停用。
    # 這段刻意放在 source .env 之前——sourcing 會把 .env 的所有機密洩漏到腳本後續。
    local skip="${SKIP_N8N_IMPORT:-}"
    if [ -z "$skip" ] && [ -f .env ]; then
        skip=$(grep -m1 '^SKIP_N8N_IMPORT=' .env | cut -d= -f2-)
    fi
    case "$(printf '%s' "$skip" | tr '[:upper:]' '[:lower:]')" in
        ""|0|false|no|off)
            ;;
        *)
            echo "⏭️  Skipping n8n workflow import (SKIP_N8N_IMPORT=${skip})."
            echo "    Workflow 1 in ${n8n_container} is left exactly as-is."
            echo "    Unset SKIP_N8N_IMPORT (or set it to 0) to re-enable."
            return 0
            ;;
    esac

    if [ -f n8n_workflow_template.json ]; then
        echo "Attempting to auto-import n8n workflow..."
        source .env 2>/dev/null || true
        
        local db_ready=false
        for i in {1..10}; do
            if docker exec "$db_container" pg_isready -U "${DB_USER:-postgres}" &>/dev/null; then
                db_ready=true
                break
            fi
            sleep 2
        done

        if [ "$db_ready" = true ]; then
            # Resolve API container to query decrypted key from business layer
            local api_container=""
            if [ "$db_container" = "advisor_prod_db" ]; then
                api_container="advisor_prod_api"
            elif [ "$db_container" = "investment_advisor_db" ]; then
                api_container="investment_advisor_mcp"
            fi

            if [ -n "$api_container" ] && docker ps --filter "name=$api_container" --quiet | grep -q .; then
                WEBHOOK_KEY=$(docker exec "$api_container" python -c "from src.services.settings_service import SettingsService; print(SettingsService(user_id='00000000-0000-4000-a000-000000000001').get_setting('webhook_api_key') or '')" 2>/dev/null | tr -d '[:space:]')
            fi

            # Fallback to raw SQL (encrypted value) if API container is not online/responsive
            if [ -z "$WEBHOOK_KEY" ]; then
                local db_name="${DB_NAME:-advisor_prod}"
                WEBHOOK_KEY=$(docker exec "$db_container" psql -U "${DB_USER:-postgres}" -d "$db_name" -t -c "SELECT value::text FROM settings WHERE key='webhook_api_key' LIMIT 1;" 2>/dev/null | sed 's/"//g' | tr -d '[:space:]')
            fi
        fi

        if [ -n "$WEBHOOK_KEY" ]; then
            sed "s/your_api_key_here/$WEBHOOK_KEY/g" n8n_workflow_template.json > /tmp/n8n_workflow_injected.json
            docker cp /tmp/n8n_workflow_injected.json "$n8n_container":/tmp/template_injected.json
            rm -f /tmp/n8n_workflow_injected.json
            N8N_IMPORT_PATH="/tmp/template_injected.json"
        else
            N8N_IMPORT_PATH="/home/node/template.json"
        fi

        # n8n CLI Wait
        MAX_RETRIES=15
        RETRY_COUNT=0
        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if docker exec "$n8n_container" n8n --version >/dev/null 2>&1; then
                if ! backup_n8n_workflow "$n8n_container" 1; then
                    echo "❌ n8n import ABORTED — pre-import backup failed."
                    echo "   Existing workflow left untouched. Re-run with"
                    echo "   SKIP_N8N_IMPORT=1 if you want to proceed without one."
                    # return 0, not 1: the script runs under `set -e` and this is
                    # called from deploy_prod BEFORE show_health, so a non-zero
                    # return would abort the deploy with the cluster already up.
                    # The banner is the signal.
                    # 回 0 而非 1：set -e 下非零會在叢集已起來後炸掉整個部署。
                    return 0
                fi
                # --activeState=fromJson: n8n 2.x defaults this to false, which
                # DEACTIVATES every imported workflow — the template says
                # "active": true and is expected to keep running. n8n 1.x has no
                # such flag, hence the fallback.
                # n8n 2.x 的預設值會停用匯入的 workflow；1.x 沒有這個參數，故 fallback。
                docker exec "$n8n_container" n8n import:workflow --input "$N8N_IMPORT_PATH" --activeState=fromJson \
                    || docker exec "$n8n_container" n8n import:workflow --input "$N8N_IMPORT_PATH"
                echo "✅ n8n Workflow imported."
                break
            fi
            sleep 5
            RETRY_COUNT=$((RETRY_COUNT+1))
        done
    fi
}

function deploy_docker {
    echo "=== Mode: Local Development (Docker) ==="
    check_env
    docker compose up --build -d
    
    echo ""
    echo "✅ Deployment Complete"
    echo "----------------------"
    echo "🌐 Frontend:            http://localhost:3001"
    echo "🔌 API:                 http://localhost:8001"
    echo "📊 Monitoring (SigNoz): http://localhost:8080"
    echo "🌍 Public Access:        $(docker compose port ngrok 4040 2>/dev/null | grep -q . && echo "http://localhost:4040 (ngrok Dashboard)" || echo "Pending...")"
    echo ""
    
    import_n8n_workflow "investment_advisor_db" "investment_advisor_n8n"
}

function ensure_signoz_volumes {
    echo "Ensuring SigNoz external volumes exist..."
    docker volume create signoz-clickhouse >/dev/null 2>&1 || true
    docker volume create signoz-sqlite >/dev/null 2>&1 || true
    docker volume create signoz-zookeeper-1 >/dev/null 2>&1 || true
    return 0
}

function deploy_prod {
    echo "=== Mode: Production Cluster (Hardened) ==="
    check_env

    # Pre-create external volumes required by SigNoz include.
    ensure_signoz_volumes

    # Hot-restart path: cluster already running → stop and restart code services (fast reload).
    # Volume mounts in docker-compose.prod.yml ensure local src/ is live inside containers.
    # 2026-07-14: the `scheduler` service was removed (it ran a SECOND
    # `celery beat` identical to `celery_beat`, double-firing every
    # scheduled task — sentinel ticks, daily reports, the hourly digest,
    # all 2x). `celery_beat` is now the sole beat authority and must be
    # restarted here too, or code/schedule changes never reach it.
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        echo "Cluster running — hot-restarting code services (celery_beat, worker_1, worker_2)..."
        docker rm -f advisor_prod_beat advisor_prod_worker_1 advisor_prod_worker_2 2>/dev/null || true
        sleep 1

        $PROD_COMPOSE up -d --no-build --no-deps celery_beat worker_1 worker_2
        echo ""
        echo "✅ Code services restarted (env reloaded)"
        echo ""
        sleep 5
        # || true: under `set -e` a red health check must not abort the deploy.
        show_health || true
        return
    fi

    # Cold start: stop any stale/conflicting containers then full build.
    docker ps -a --format '{{.Names}}' | grep -E "^(advisor_prod|signoz|schema-migrator|investment_advisor)" \
        | xargs -r docker stop 2>/dev/null || true
    docker ps -a --format '{{.Names}}' | grep -E "^(advisor_prod|signoz|schema-migrator|investment_advisor)" \
        | xargs -r docker rm -f 2>/dev/null || true

    $PROD_COMPOSE up --build -d --remove-orphans

    # Post-deploy: Force-start containers stuck in 'created' state
    # n8n depends on mcp_server healthy, but sometimes gets stuck before the health gate passes.
    echo "🔁 Checking for containers stuck in 'created' state..."
    for i in 1 2 3; do
        STUCK=$(docker ps -a --filter "name=advisor_prod" --filter "status=created" --format "{{.Names}}" 2>/dev/null)
        if [ -z "$STUCK" ]; then
            echo "✅ All containers are running."
            break
        fi
        echo "⚠️  Attempt $i: Force-starting stuck containers: $STUCK"
        echo "$STUCK" | xargs -r docker start
        sleep 15
    done
    # Final explicit check: ensure n8n started (it has a deep depends_on chain)
    if ! docker ps --format '{{.Names}}' | grep -q "advisor_prod_n8n"; then
        echo "⚠️  n8n not running — attempting explicit start..."
        docker start advisor_prod_n8n 2>/dev/null || true
        sleep 10
    fi

    wait_for_api "http://localhost:8000/health" 120 || true
    fix_redis_queues "advisor_prod_cache"

    echo ""
    echo "✅ PRODUCTION Cluster Online"
    echo "---------------------------"
    echo "🌐 Production Gateway:  http://127.0.0.1:8088"
    echo "📊 Monitoring (SigNoz): http://localhost:8080"
    echo "🛡️  Status:             Hardened, APM Active"
    echo ""

    import_n8n_workflow "advisor_prod_db" "advisor_prod_n8n"

    echo ""
    # || true: see above — the dispatcher's `health` case is the gating surface.
    show_health || true
}

function check_shared_ollama {
    echo "Checking for shared Ollama service..."
    if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "⚠️  Shared Ollama not detected at http://localhost:11434"
        echo "   Attempting to start from shared infra..."
        if [ -f "../infra/start-ollama.sh" ]; then
            bash ../infra/start-ollama.sh
        elif [ -f "infra/start-ollama.sh" ]; then
             bash infra/start-ollama.sh
        else
            echo "❌ Error: Shared infra start-ollama.sh not found."
            return 1
        fi
    else
        echo "✅ Shared Ollama is online."
    fi
}

function deploy_ollama {
    echo "=== Mode: Shared Ollama Infrastructure ==="
    check_shared_ollama
    echo ""
    echo "✅ Shared Ollama Service Online"
    echo "---------------------------"
    echo "🌐 Ollama API Gateway: http://localhost:11434"
    echo "To view models: curl http://localhost:11434/api/tags"
    echo ""
}

function telegram_setup {
    local public_url=$1
    if [ -z "$public_url" ]; then
        echo "❌ Error: Public URL (ngrok) is required."
        echo "Usage: ./start.sh telegram-setup https://your-id.ngrok-free.app"
        return 1
    fi
    echo "=== Setting up Telegram Webhook ==="
    docker exec advisor_prod_api python src/setup_telegram_webhook.py "$public_url"
}

function cleanup {
    echo "=== Cleaning Up All Resources ==="
    [ -f docker-compose.yml ] && docker compose down --remove-orphans
    [ -f docker-compose.prod.yml ] && $PROD_COMPOSE down --remove-orphans
    [ -f docker-compose.ollama.yml ] && docker compose -f docker-compose.ollama.yml down --remove-orphans
    
    if [ "$1" == "--prune" ]; then
        echo "🧹 Pruning Docker system (containers, images, volumes, build cache)..."
        docker system prune -af --volumes
    fi
    
    echo "✅ Cleanup Complete"
}

# --- Main Logic ---
case "$1" in
    dev|"")
        deploy_docker
        ;;
    prod)
        deploy_prod
        ;;
    selfhost)
        selfhost_bootstrap
        ;;
    workers)
        scale_workers "$2"
        ;;
    worker-status)
        worker_status
        ;;
    worker-logs)
        worker_logs
        ;;
    stop|clean)
        cleanup
        ;;
    migrate)
        run_migrations
        ;;
    patch)
        patch_prod
        ;;
    ollama)
        deploy_ollama
        ;;
    health)
        show_health
        ;;
    telegram-setup)
        telegram_setup "$2"
        ;;
    prune)
        cleanup "--prune"
        ;;
    fix-redis)
        fix_redis_queues "advisor_prod_cache"
        ;;
    k8s)
        # Assuming k8s logic remains the same
        check_env
        kubectl apply -f k8s/
        ;;
    *)
        show_help
        ;;
esac
