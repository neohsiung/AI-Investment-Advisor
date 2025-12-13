#!/bin/bash

# GCP Teardown Script
# Deletes Cloud Run Service and Jobs to stop billing.

PROJECT_ID=$(gcloud config get-value project)
REGION="asia-east1" # Default region, adjust if needed
SERVICE_NAME="investment-dashboard"
JOBS=("daily-check" "weekly-report" "monthly-refinement")
REPO_NAME="investment-advisor"

echo "⚠️  WARNING: This script will DELETE the following GCP resources in project '$PROJECT_ID':"
echo "   - Cloud Run Service: $SERVICE_NAME"
echo "   - Cloud Run Jobs: ${JOBS[*]}"
echo ""
read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo "--- Deleting Cloud Run Service ---"
gcloud run services delete $SERVICE_NAME --region=$REGION --quiet || echo "Service $SERVICE_NAME not found or already deleted."

echo "--- Deleting Cloud Run Jobs ---"
for JOB in "${JOBS[@]}"; do
    gcloud run jobs delete $JOB --region=$REGION --quiet || echo "Job $JOB not found or already deleted."
done

echo "--- Teardown Complete ---"
echo "Note: Cloud SQL and Artifact Registry images represent data and were NOT deleted."
echo "To delete them, manually run:"
echo "  gcloud sql instances delete [INSTANCE_NAME]"
echo "  gcloud artifacts repositories delete $REPO_NAME --location=$REGION"
