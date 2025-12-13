#!/bin/bash

# Cloud SQL Setup Script for AI Investment Advisor
# Usage: ./setup_cloud_sql.sh [PROJECT_ID] [REGION] [PASSWORD]

PROJECT_ID=$1
REGION=${2:-asia-east1}
DB_PASS=${3:-$(openssl rand -base64 12)}
INSTANCE_NAME="portfolio-prod"
DB_NAME="portfolio"
DB_USER="portfolio_user"

if [ -z "$PROJECT_ID" ]; then
    echo "Usage: ./setup_cloud_sql.sh [PROJECT_ID] [REGION] [PASSWORD]"
    echo "Example: ./setup_cloud_sql.sh my-gcp-project asia-east1"
    exit 1
fi

# Fix: Auto-detect Python 3.11 for gcloud if needed (macOS specific fix)
if [ -z "$CLOUDSDK_PYTHON" ] && command -v python3.11 >/dev/null; then
    echo "🐍 Auto-detected Python 3.11. Setting CLOUDSDK_PYTHON..."
    export CLOUDSDK_PYTHON=$(command -v python3.11)
fi

# Version Check Warning
echo "⚠️  Checking gcloud compatibility..."
# Check signature of gcloud (capture error to see if it's python related)
# Note: Use the target project ID to avoid errors if the currently configured project is invalid
GCLOUD_TEST_ERR=$(gcloud services list --project="$PROJECT_ID" --limit=1 2>&1 >/dev/null)
if [ $? -ne 0 ]; then
    echo "❌ ERROR executing gcloud."
    echo "Debug details: $GCLOUD_TEST_ERR"
    echo "👉 If this is a Python error, ensure CLOUDSDK_PYTHON is set correctly."
    exit 1
fi

echo "🚀 Starting Cloud SQL Setup for Project: $PROJECT_ID in $REGION..."

# 1. Enable APIs
echo "📡 Enabling Service APIs..."
gcloud services enable sqladmin.googleapis.com --project="$PROJECT_ID"

# 2. Create Instance (Smallest tier for cost saving)
echo "🛠 Creating Cloud SQL Instance '$INSTANCE_NAME' (This may take 5-10 minutes)..."
gcloud sql instances create "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --storage-size=10GB \
    --storage-type=SSD \
    --storage-auto-increase \
    --availability-type=ZONAL # Zonal is cheaper than Regional

# Check if creation succeeded
if [ $? -ne 0 ]; then
    echo "❌ Instance creation failed. Please check your permissions or quota."
    exit 1
fi

# 3. Create Database
echo "🗄 Creating Database '$DB_NAME'..."
gcloud sql databases create "$DB_NAME" \
    --instance="$INSTANCE_NAME" \
    --project="$PROJECT_ID"

# 4. Create User
echo "👤 Creating User '$DB_USER'..."
gcloud sql users create "$DB_USER" \
    --instance="$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --password="$DB_PASS"

# 5. Get Connection Name
CONNECTION_NAME=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(connectionName)")

echo ""
echo "✅ Cloud SQL Setup Complete!"
echo "================================================"
echo "🔹 Project:       $PROJECT_ID"
echo "🔹 Instance:      $INSTANCE_NAME"
echo "🔹 Connection:    $CONNECTION_NAME"
echo "🔹 Database:      $DB_NAME"
echo "🔹 User:          $DB_USER"
echo "🔹 Password:      $DB_PASS"
echo "================================================"
echo ""
echo "👉 Next Steps for Cloud Run Deployment:"
echo "   Run the following command during deployment:"
echo "   --set-env-vars DB_TYPE=postgres,DB_USER=$DB_USER,DB_PASS=$DB_PASS,DB_NAME=$DB_NAME,DB_HOST=/cloudsql/$CONNECTION_NAME"
echo ""
