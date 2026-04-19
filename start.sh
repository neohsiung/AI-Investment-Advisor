#!/bin/bash
# start.sh - Unified Orchestration Entry Point for Investment Advisor Platform
# v4.1: Harmonized Dev/Prod migration and gateway reporting.

set -e

# Support for environments where docker is in /usr/local/bin
export PATH=$PATH:/usr/local/bin:/usr/bin:/bin

# --- Helper Functions ---
function show_help {
    echo "Quantum AI Platform - Operational Control v4.1"
    echo "Usage: ./start.sh [command]"
    echo ""
    echo "Commands:"
    echo "  dev (default)  Deploy Local Development environment (Docker Compose)."
    echo "                 - Includes SigNoz APM, n8n, and Debugging tools."
    echo "                 - Gateway: http://localhost:80"
    echo ""
    echo "  prod           Deploy Hardened Production cluster (B2C SaaS Mode)."
    echo "                 - Security hardened, monitoring active."
    echo "                 - Gateway: http://localhost:80"
    echo ""
    echo "  stop           Stop all containers and perform deep cleanup."
    echo ""
    echo "  migrate        Align database heads and run all migrations (Auto-detect Env)."
    echo "                 - Fixes 'Multiple Heads' and syncs schema."
    echo ""
    echo "  patch          Production Hot-Patch (No downtime UI/API update)."
    echo ""
    echo "  k8s            Deploy to Kubernetes (Minikube / Cloud)."
}

function check_env {
    if [ ! -f .env ]; then
        echo "Error: .env file not found! Copying .env.example..."
        cp .env.example .env
        echo "WARNING: Created default .env. Please edit it with your API keys!"
    fi
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
    docker compose -f docker-compose.prod.yml build frontend mcp_server
    docker compose -f docker-compose.prod.yml up -d --no-deps frontend mcp_server
    echo "✅ Patch Applied Successfully"
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

function deploy_prod {
    echo "=== Mode: Production Cluster (Hardened) ==="
    check_env
    docker compose -f docker-compose.prod.yml up --build -d
    
    echo ""
    echo "✅ PRODUCTION Cluster Online"
    echo "---------------------------"
    echo "🌐 Production Gateway:  http://localhost:80"
    echo "📊 Monitoring (SigNoz): http://localhost:8080"
    echo "🛡️  Status:             Hardened, APM Active"
    echo ""

    import_n8n_workflow "advisor_prod_db" "advisor_prod_n8n"
}

function cleanup {
    echo "=== Cleaning Up All Resources ==="
    [ -f docker-compose.yml ] && docker compose down --remove-orphans
    [ -f docker-compose.prod.yml ] && docker compose -f docker-compose.prod.yml down --remove-orphans
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
    stop|clean)
        cleanup
        ;;
    migrate)
        run_migrations
        ;;
    patch)
        patch_prod
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
