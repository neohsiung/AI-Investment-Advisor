#!/bin/bash
set -e

# setup_monitoring.sh
# Description: Configures GCP Cloud Monitoring Uptime Check and Alert Policy for the Spot VM.
# Usage: ./setup_monitoring.sh <PROJECT_ID> <VM_IP> <EMAIL_ADDRESS>

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <PROJECT_ID> <VM_IP> <EMAIL_ADDRESS>"
    exit 1
fi

PROJECT_ID=$1
VM_IP=$2
EMAIL_ADDRESS=$3
region="global" # Uptime checks are global

echo "=== Setting up GCP Cloud Monitoring for Project: ${PROJECT_ID} ==="

# 1. Create Notification Channel (Email)
echo "Creating Notification Channel for ${EMAIL_ADDRESS}..."
CHANNEL_NAME=$(gcloud beta monitoring channels create \
    --display-name="Investment Advisor Admin (${EMAIL_ADDRESS})" \
    --type=email \
    --channel-labels=email_address=${EMAIL_ADDRESS} \
    --project=${PROJECT_ID} \
    --format="value(name)")

echo "Notification Channel Created: ${CHANNEL_NAME}"

# 2. Create Uptime Check Config
echo "Creating Uptime Check for http://${VM_IP}:8501 ..."
# Display Name: Investment Advisor Dashboard Check
UPTIME_CHECK_NAME=$(gcloud monitoring uptime-check-configs create "investment-advisor-uptime-check" \
    --display-name="Investment Advisor Dashboard Check" \
    --resource-type=uptime-url \
    --resource-labels=host=${VM_IP},project_id=${PROJECT_ID} \
    --http-check-path="/" \
    --http-check-port=8501 \
    --period=5 \
    --timeout=10 \
    --project=${PROJECT_ID} \
    --format="value(name)")

echo "Uptime Check Created: ${UPTIME_CHECK_NAME}"

# 3. Create Alert Policy
# Alert if Uptime Check fails
echo "Creating Alert Policy..."
gcloud alpha monitoring policies create \
    --display-name="Investment Advisor - Spot VM Down Alert" \
    --notification-channels=${CHANNEL_NAME} \
    --project=${PROJECT_ID} \
    --policy-from-file=<(cat <<EOF
{
  "displayName": "Investment Advisor - Spot VM Down Alert",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Uptime Check Failed",
      "conditionThreshold": {
        "filter": "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id = \"${UPTIME_CHECK_NAME##*/}\"",
        "aggregations": [
          {
            "alignmentPeriod": "1200s",
            "perSeriesAligner": "ALIGN_NEXT_OLDER",
            "crossSeriesReducer": "REDUCE_COUNT_FALSE"
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 1,
        "duration": "60s",
        "trigger": {
          "count": 1
        }
      }
    }
  ]
}
EOF
)

echo "============================================================"
echo "Monitoring Setup Complete!"
echo "You will receive an email at ${EMAIL_ADDRESS} to confirm the notification channel."
echo "If the Spot VM is preempted, you will receive an alert."
echo "============================================================"
