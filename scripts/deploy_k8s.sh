#!/bin/bash
set -e

# Configuration
NAMESPACE="investment-advisor"

echo "Deploying to Kubernetes (Context: $(kubectl config current-context))..."

# Create Namespace
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Create ConfigMap for Init SQL if needed
# We assume the init.sql file is at deployment/postgres/init.sql
kubectl create configmap postgres-init \
  --from-file=init.sql=deployment/postgres/init.sql \
  -n $NAMESPACE \
  --dry-run=client -o yaml | kubectl apply -f -

# Create Secrets (Interactive or Dummy for Dev)
if ! kubectl get secret app-secrets -n $NAMESPACE > /dev/null 2>&1; then
    echo "Creating 'app-secrets' (using dummy values for LOCAL DEV)..."
    kubectl create secret generic app-secrets \
    --from-literal=POSTGRES_USER=postgres \
    --from-literal=POSTGRES_PASSWORD=postgres \
    --from-literal=POSTGRES_DB=portfolio \
    --from-literal=DB_HOST=postgres \
    --from-literal=DB_NAME=portfolio \
    --from-literal=DB_USER=postgres \
    --from-literal=DB_PASS=postgres \
    --from-literal=API_KEY=dummy_key \
    --from-literal=AI_PROVIDER=Google \
    -n $NAMESPACE
else
    echo "Secret 'app-secrets' already exists. Skipping."
fi

# Apply Manifests
echo "Applying Manifests..."
kubectl apply -f k8s/postgres.yaml -n $NAMESPACE
kubectl apply -f k8s/dashboard.yaml -n $NAMESPACE
kubectl apply -f k8s/scheduler.yaml -n $NAMESPACE

echo "Waiting for deployments..."
kubectl rollout status deployment/postgres -n $NAMESPACE --timeout=60s
kubectl rollout status deployment/dashboard -n $NAMESPACE --timeout=60s

echo "Deployment Complete! Port forward with:"
echo "kubectl port-forward svc/dashboard 8501:8501 -n $NAMESPACE"
