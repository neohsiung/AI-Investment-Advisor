#!/bin/bash

# Configuration
SERVICE_NAME="investment-dashboard"
REGION="asia-east1"

# 1. Deploy the service
# This uses the current directory as source
echo "🚀 Deploying $SERVICE_NAME to $REGION..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --allow-unauthenticated

# 2. Get the assigned URL
echo "🔍 Fetching Service URL..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')

if [ -z "$SERVICE_URL" ]; then
  echo "❌ Failed to get Service URL."
  exit 1
fi

echo "✅ Detected URL: $SERVICE_URL"

# 3. Update REDIRECT_URI environment variable
# This ensures the app knows its own URL for OAuth
echo "⚙️  Setting REDIRECT_URI to match service URL..."
gcloud run services update $SERVICE_NAME \
  --region $REGION \
  --update-env-vars REDIRECT_URI=$SERVICE_URL

echo "🎉 Deployment Complete!"
echo "---------------------------------------------------"
echo "Your app is live at: $SERVICE_URL"
echo "Make sure to add this URL to 'Authorized redirect URIs' in Google Cloud Console:"
echo "👉 $SERVICE_URL"
echo "---------------------------------------------------"
