#!/bin/bash
# Worker Pool Startup Script for Enterprise Version
# Starts multiple worker instances to process queued jobs

set -e

echo "🚀 Portfolio Advisor Enterprise Worker Pool Startup"
echo "=================================================="
echo "Timestamp: $(date)"

# Configuration
WORKER_COUNT=${WORKER_COUNT:-2}
CONCURRENCY=${CONCURRENCY:-2}
REDIS_URL=${REDIS_URL:-"redis://advisor_prod_cache:6379"}
# No default password: DB_PASS must come from the environment (see DD-2026-1026).
# 不帶預設密碼：DB_PASS 必須由環境變數提供。
if [ -z "${DATABASE_URL:-}" ]; then
    DATABASE_URL="postgresql://postgres:${DB_PASS:?DB_PASS is required when DATABASE_URL is unset}@advisor_prod_db:5432/portfolio"
fi

echo "Configuration:"
echo "  Workers: $WORKER_COUNT"
echo "  Concurrency: $CONCURRENCY"
echo "  Redis: $REDIS_URL"
echo "  Database: (set; URL not printed because it contains the password)"
echo ""

# Function to start a single worker
start_worker() {
    local worker_id=$1
    local container_name="advisor_prod_worker_$worker_id"

    echo "Starting worker $worker_id ($container_name)..."

    docker run -d
        --name "$container_name"
        --network advisor_network
        -e PYTHONUNBUFFERED=1
        -e QUEUE_REDIS_URL="$REDIS_URL"
        -e DATABASE_URL="$DATABASE_URL"
        -e WORKER_ID="worker-$worker_id"
        -e WORKER_CONCURRENCY="$CONCURRENCY"
        -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
        --restart unless-stopped
        --log-driver json-file
        --log-opt max-size=10m
        --log-opt max-file=3
        advisor:lates
        python /workspace/services/scheduler/src/app.py
            --worker
            --worker-id worker-$worker_id
            --concurrency $CONCURRENCY

    echo "  ✅ Worker $worker_id started (container: $container_name)"
}

# Start all workers
for i in $(seq 1 "$WORKER_COUNT"); do
    start_worker "$i"
    sleep 2  # Stagger startup
done

echo ""
echo "✅ All $WORKER_COUNT workers started"
echo ""
echo "Monitoring worker health..."
sleep 3

# Check worker status
for i in $(seq 1 "$WORKER_COUNT"); do
    container_name="advisor_prod_worker_$i"
    status=$(docker inspect "$container_name" --format='{{.State.Status}}' 2>/dev/null || echo "unknown")
    echo "  Worker $i: $status"
done

echo ""
echo "View logs with:"
echo "  docker logs -f advisor_prod_worker_1"
echo "  docker logs -f advisor_prod_worker_2"
echo ""
echo "Check queue status:"
echo "  docker exec advisor_prod_cache redis-cli ZCARD report:daily:queue"
