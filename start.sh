#!/bin/bash
# start.sh - Unified Entry Point for Investment Advisor Platform
# v3.1: Supports Docker (default) and Kubernetes modes.

set -e

# --- Helper Functions ---
function show_help {
    echo "Usage: ./start.sh [mode]"
    echo ""
    echo "Modes:"
    echo "  --docker    Deploy using Docker Compose (Default - Dev Mode)"
    echo "  --prod      Deploy focused Production cluster (Hardened - B2C SaaS)"
    echo "  --patch     Hot-patch Production (Rebuilds UI/API without downtime)"
    echo "  --k8s       Deploy to Kubernetes (Minikube/Cloud - requires kubectl)"
    echo "  --clean     Stop containers and remove K8s resources"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./start.sh             # Starts Docker Compose"
    echo "  ./start.sh --k8s       # Starts K8s Deployment"
    echo "  ./start.sh --clean     # Cleanup"
}

function check_env {
    if [ ! -f .env ]; then
        echo "Error: .env file not found!"
        echo "Copying .env.example to .env..."
        cp .env.example .env
        echo "WARNING: Created default .env. Please edit it with your API keys immediately!"
        read -p "Press Enter to continue (or Ctrl+C to edit .env first)..."
    fi
}

function patch_prod {
    echo "=== Mode: Hot-Patching Production Cluster ==="
    check_env
    echo "Rebuilding Frontend and MCP Server..."
    docker compose -f docker-compose.prod.yml build frontend mcp_server
    echo "Applying patches (no-deps restart)..."
    docker compose -f docker-compose.prod.yml up -d --no-deps frontend mcp_server
    echo "✅ Patch Applied Successfully"
}

function deploy_docker {
    echo "=== Starting Mode: Docker Compose (Local) ==="
    check_env
    
    echo "Building and starting containers..."
    docker compose up --build -d
    
    echo ""
    echo "✅ Deployment Complete"
    echo "----------------------"
    echo "📊 Dashboard (Next.js): http://localhost:3000"
    echo "🧠 Legacy (Streamlit):   http://localhost:8501"
    echo "🩺 APM/Traces (SigNoz):  http://localhost:8080"
    echo "🗄️  Database:           localhost:5432"
    echo "🔗 n8n:                 http://localhost:5678"
    echo ""
    
    # Auto-import n8n workflow with API key injection
    if [ -f n8n_workflow_template.json ]; then
        echo "Attempting to auto-import n8n workflow..."
        # Inject webhook API key from DB into n8n template
        source .env 2>/dev/null
        WEBHOOK_KEY=$(docker exec investment_advisor_db psql -U "${DB_USER:-user}" -d "${DB_NAME:-advisor}" -t -c "SELECT value FROM settings WHERE key='webhook_api_key' LIMIT 1;" 2>/dev/null | tr -d ' \n')
        if [ -n "$WEBHOOK_KEY" ]; then
            echo "Injecting webhook API key into n8n template..."
            sed "s/your_api_key_here/$WEBHOOK_KEY/g" n8n_workflow_template.json > /tmp/n8n_workflow_injected.json
            docker cp /tmp/n8n_workflow_injected.json investment_advisor_n8n:/tmp/template_injected.json
            rm -f /tmp/n8n_workflow_injected.json
            N8N_IMPORT_PATH="/tmp/template_injected.json"
        else
            echo "⚠️  No webhook_api_key found in DB. Using template as-is."
            N8N_IMPORT_PATH="/home/node/template.json"
        fi
        # Robust wait for n8n initialization (v1.x/v2.x CLI compat)
        MAX_RETRIES=12
        RETRY_COUNT=0
        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if docker exec investment_advisor_n8n n8n --version >/dev/null 2>&1; then
                echo "n8n is ready. Importing workflow..."
                docker exec investment_advisor_n8n n8n import:workflow --input "$N8N_IMPORT_PATH" && echo "✅ Workflow imported and activated successfully"
                break
            fi
            echo "Waiting for n8n to initialize (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)..."
            sleep 5
            RETRY_COUNT=$((RETRY_COUNT+1))
        done
        
        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            echo "⚠️  Warning: n8n import timed out. Please check logs with: docker compose logs n8n"
        fi
    fi

    echo "To view logs: docker compose logs -f"
}

function deploy_prod {
    echo "=== Starting Mode: Production Cluster (Hardened) ==="
    check_env
    
    echo "Building and starting production containers..."
    docker compose -f docker-compose.prod.yml up --build -d
    
    echo ""
    echo "✅ PRODUCTION Deployment Complete"
    echo "----------------------"
    echo "📊 Dashboard:       http://localhost:3000"
    echo "🛡️  Auth Gateway:   http://localhost:8000/api/v1/auth"
    echo "🩺 APM/Monitoring: http://localhost:8080 (SigNoz)"
    echo "🔗 Automation:     http://localhost:5678 (n8n)"
    echo ""
    echo "To view production logs: docker compose -f docker-compose.prod.yml logs -f"
}

function deploy_k8s {
    echo "=== Starting Mode: Kubernetes ==="
    check_env
    
    if ! command -v kubectl &> /dev/null; then
        echo "Error: kubectl not found."
        exit 1
    fi

    # Minikube Check
    IS_MINIKUBE=false
    if command -v minikube &> /dev/null; then
        if minikube status | grep -q "Running"; then
            echo "Context: Minikube detected (configuring Docker env)..."
            IS_MINIKUBE=true
            eval $(minikube docker-env)
        fi
    fi

    # Secrets
    echo "Creating Secrets..."
    kubectl delete secret app-secrets --ignore-not-found
    kubectl create secret generic app-secrets --from-env-file=.env

    kubectl delete configmap postgres-init --ignore-not-found
    kubectl create configmap postgres-init --from-file=deployment/postgres/init.sql

    # Build (Minikube only)
    if [ "$IS_MINIKUBE" = true ]; then
        echo "Building images in Minikube..."
        docker build -t investment-advisor-dashboard:latest -f Dockerfile .
        docker build -t investment-advisor-scheduler:latest -f Dockerfile .
    else
        echo "Cloud Mode: Skipping build (assuming images exist in registry)."
    fi

    # Apply
    echo "Applying manifests..."
    kubectl apply -f k8s/

    # Wait
    echo "Waiting for pods..."
    kubectl wait --for=condition=ready pod --all --timeout=120s || echo "Pods pending..."

    echo ""
    echo "✅ Deployment Triggered"
    if [ "$IS_MINIKUBE" = true ]; then
        echo "Run to access: minikube service dashboard"
    else
        echo "Check Ingress IP for access."
    fi
}

function cleanup {
    echo "=== Cleaning Up Resources ==="
    
    # Docker
    if [ -f docker-compose.yml ]; then
        echo "Stopping Docker Compose (Dev)..."
        docker compose down
    fi
    if [ -f docker-compose.prod.yml ]; then
        echo "Stopping Docker Compose (Prod)..."
        docker compose -f docker-compose.prod.yml down
    fi

    # K8s
    if command -v kubectl &> /dev/null; then
        echo "Removing Kubernetes resources..."
        kubectl delete -f k8s/ --ignore-not-found 2>/dev/null
        kubectl delete secret app-secrets --ignore-not-found 2>/dev/null
        kubectl delete configmap postgres-init --ignore-not-found 2>/dev/null
    fi
    
    echo "✅ Cleanup Complete"
}

# --- Main Logic ---

case "$1" in
    --docker)
        deploy_docker
        ;;
    --prod)
        deploy_prod
        ;;
    --patch)
        patch_prod
        ;;
    --k8s)
        deploy_k8s
        ;;
    --clean|--cleanup)
        cleanup
        ;;
    --help)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            # Default behavior
            deploy_docker
        else
            echo "Unknown option: $1"
            show_help
            exit 1
        fi
        ;;
esac
