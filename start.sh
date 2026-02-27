#!/bin/bash
# start.sh - Unified Entry Point for Investment Advisor Platform
# v3.1: Supports Docker (default) and Kubernetes modes.

set -e

# --- Helper Functions ---
function show_help {
    echo "Usage: ./start.sh [mode]"
    echo ""
    echo "Modes:"
    echo "  --docker    Deploy using Docker Compose (Default - Recommended for Local)"
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

function deploy_docker {
    echo "=== Starting Mode: Docker Compose (Local) ==="
    check_env
    
    echo "Building and starting containers..."
    docker compose up --build -d
    
    echo ""
    echo "✅ Deployment Complete"
    echo "----------------------"
    echo "📊 Dashboard: http://localhost:8501"
    echo "🩺 APM/Traces: http://localhost:8080 (SigNoz)"
    echo "🗄️  Database:  localhost:5432"
    echo "🔗 n8n:       http://localhost:5678"
    echo ""
    echo "To view logs: docker compose logs -f"
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
        echo "Stopping Docker Compose..."
        docker compose down
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
