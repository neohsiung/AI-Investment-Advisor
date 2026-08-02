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
    echo "                 - Gateway: http://localhost:80"
    echo ""
    echo "  prod           Deploy Hardened Production cluster (B2C SaaS Mode)."
    echo "                 - Includes Worker Pool for async report generation."
    echo "                 - Security hardened, monitoring active."
    echo "                 - If cluster already running: hot-restarts code services only (fast)."
    echo "                 - Gateway: http://localhost:80"
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
    echo "  Dashboard:     http://localhost:80"
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

function show_health {
    echo "=== System Health ==="

    echo ""
    echo "Containers:"
    docker ps --filter "name=advisor_prod" --format "  {{.Names}}: {{.Status}}" 2>/dev/null

    local api_port=8001
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        api_port=8000
    fi

    echo ""
    echo "API:"
    if curl -sf "http://localhost:${api_port}/health" >/dev/null 2>&1; then
        echo "  http://localhost:${api_port}/health  OK"
    else
        echo "  http://localhost:${api_port}/health  FAIL"
    fi

    echo ""
    echo "Redis Queues:"
    if docker ps --format '{{.Names}}' | grep -q "$PROD_CACHE"; then
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
            fi
        done
        local dlq_depth
        dlq_depth=$(redis_cmd "$PROD_CACHE" llen "report:dlq:failed")
        echo "  report:dlq:failed: $dlq_depth failed jobs"
    else
        echo "  Redis not running"
    fi

    echo ""
    echo "DB Job Status:"
    docker exec "$PROD_DB" psql -U postgres portfolio -c \
        "SELECT status, COUNT(*) FROM report_jobs GROUP BY status ORDER BY count DESC;" \
        2>/dev/null | tail -n +3 | sed 's/^/  /' || echo "  (no report_jobs table or DB unavailable)"
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

function import_n8n_workflow {
    local db_container=$1
    local n8n_container=$2

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
                docker exec "$n8n_container" n8n import:workflow --input "$N8N_IMPORT_PATH"
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
    echo "🌐 Unified Gateway:     http://localhost:80"
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
        show_health
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
    echo "🌐 Production Gateway:  http://localhost:80"
    echo "📊 Monitoring (SigNoz): http://localhost:8080"
    echo "🛡️  Status:             Hardened, APM Active"
    echo ""

    import_n8n_workflow "advisor_prod_db" "advisor_prod_n8n"

    echo ""
    show_health
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
