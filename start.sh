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
    echo "  k8s            Deploy to Kubernetes (Minikube / Cloud)."
}

PROD_COMPOSE="docker compose --project-name investment_advisor -f docker-compose.prod.yml"
PROD_CACHE="advisor_prod_cache"
PROD_DB="advisor_prod_db"
readonly REPORT_QUEUES=("report:daily:queue" "report:weekly:queue" "report:priority:queue")

function redis_cmd {
    # Usage: redis_cmd <container> <redis args...>
    docker exec "$1" redis-cli "${@:2}" 2>/dev/null | tr -d '\r'
}

function check_env {
    if [ ! -f .env ]; then
        echo "Error: .env file not found! Copying .env.example..."
        cp .env.example .env
        echo "WARNING: Created default .env. Please edit it with your API keys!"
    fi
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
    local api_url=${1:-"http://localhost:8000/health"}
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

    echo ""
    echo "API:"
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "  http://localhost:8000/health  OK"
    else
        echo "  http://localhost:8000/health  FAIL"
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

    # 2. Fix potential multiple heads (Alembic)
    echo "Aligning database headers in $target_db..."
    docker exec "$target_db" psql -U postgres -d portfolio -c "DELETE FROM alembic_version; INSERT INTO alembic_version (version_num) VALUES ('merge_heads_001');" 2>/dev/null || true
    
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
            WEBHOOK_KEY=$(docker exec "$db_container" psql -U "${DB_USER:-postgres}" -d "portfolio" -t -c "SELECT value FROM settings WHERE key='webhook_api_key' LIMIT 1;" 2>/dev/null | sed 's/\"//g' | tr -d '[:space:]')
        fi

        if [ -n "$WEBHOOK_KEY" ]; then
            sed "s/your_api_key_here/$WEBHOOK_KEY/g" n8n_workflow_template.json > /tmp/n8n_workflow_injected.json
            docker cp /tmp/n8n_workflow_injected.json "$n8n_container":/tmp/template_injected.json
            rm -f /tmp/n8n_workflow_injected.json
            N8N_IMPORT_PATH="/tmp/template_injected.json"
        else
            N8N_IMPORT_PATH="/home/node/.n8n/workflows/template.json"
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
    # NOTE: SigNoz volumes are now pre-configured in docker-compose.prod.yml include.
    # Volume creation is handled automatically by Docker Compose.
    # This function is maintained for backward compatibility.
    return 0
}

function deploy_prod {
    echo "=== Mode: Production Cluster (Hardened) ==="
    check_env

    # Pre-create external volumes required by SigNoz include.
    ensure_signoz_volumes

    # Hot-restart path: cluster already running → stop and restart code services (fast reload).
    # Volume mounts in docker-compose.prod.yml ensure local src/ is live inside containers.
    if docker ps --format '{{.Names}}' | grep -q "advisor_prod_api"; then
        echo "Cluster running — hot-restarting code services (scheduler, worker_1, worker_2)..."
        $PROD_COMPOSE stop scheduler 2>/dev/null || true
        sleep 1
        
        # Remove and restart workers (docker-compose can't replace running containers)
        docker rm -f advisor_prod_worker_1 advisor_prod_worker_2 2>/dev/null || true
        sleep 1
        
        $PROD_COMPOSE up -d --no-build scheduler worker_1 worker_2
        echo ""
        echo "✅ Code services restarted (env reloaded)"
        echo ""
        sleep 5
        show_health
        return
    fi

    # Cold start: stop any stale/conflicting containers then full build.
    docker ps -a --format '{{.Names}}' | grep -E "^(advisor_prod|signoz|schema-migrator|signoz-otel-collector|signoz-clickhouse|signoz-zookeeper)" \
        | xargs -r docker stop 2>/dev/null || true
    docker ps -a --format '{{.Names}}' | grep -E "^(advisor_prod|signoz|schema-migrator|signoz-otel-collector|signoz-clickhouse|signoz-zookeeper)" \
        | xargs -r docker rm 2>/dev/null || true

    $PROD_COMPOSE up --build -d --remove-orphans

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

function cleanup {
    echo "=== Cleaning Up All Resources ==="
    [ -f docker-compose.yml ] && docker compose down --remove-orphans
    [ -f docker-compose.prod.yml ] && $PROD_COMPOSE down --remove-orphans
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
    health)
        show_health
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
