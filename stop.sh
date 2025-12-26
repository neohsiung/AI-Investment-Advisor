#!/bin/bash

echo "Stopping Investment Advisor Platform (Kubernetes Mode)..."

echo "Deleting K8s resources..."
kubectl delete -f k8s/ --ignore-not-found

echo ""
echo "=== Services Stopped ==="
echo "Note: Minikube cluster is still running. To stop it, run: minikube stop"
