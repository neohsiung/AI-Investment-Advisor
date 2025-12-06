#!/bin/bash

# Configuration
PROJECT_ID="your-project-id"
REGION="asia-east1"
SERVICE_ACCOUNT="investment-scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Create Service Account if not exists
gcloud iam service-accounts create investment-scheduler-sa \
    --display-name "Investment Scheduler Service Account" || true

# Grant permission to invoke Cloud Run Jobs
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member "serviceAccount:${SERVICE_ACCOUNT}" \
    --role "roles/run.invoker"

# 1. Daily Check (Every day at 09:00 Taipei Time = 01:00 UTC)
gcloud scheduler jobs create http daily-check-trigger \
    --location ${REGION} \
    --schedule "0 1 * * *" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/daily-check:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei" || \
gcloud scheduler jobs update http daily-check-trigger \
    --schedule "0 1 * * *" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/daily-check:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei"

# 2. Weekly Report (Every Saturday at 09:00 Taipei Time)
gcloud scheduler jobs create http weekly-report-trigger \
    --location ${REGION} \
    --schedule "0 9 * * 6" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/weekly-report:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei" || \
gcloud scheduler jobs update http weekly-report-trigger \
    --schedule "0 9 * * 6" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/weekly-report:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei"

# 3. Monthly Refinement (1st day of month at 00:00 Taipei Time)
gcloud scheduler jobs create http monthly-refinement-trigger \
    --location ${REGION} \
    --schedule "0 0 1 * *" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/monthly-refinement:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei" || \
gcloud scheduler jobs update http monthly-refinement-trigger \
    --schedule "0 0 1 * *" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/monthly-refinement:run" \
    --http-method POST \
    --oauth-service-account-email ${SERVICE_ACCOUNT} \
    --time-zone "Asia/Taipei"

echo "Cloud Scheduler triggers created/updated successfully."
