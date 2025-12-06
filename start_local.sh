#!/bin/bash

# Ensure .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your credentials."
    exit 1
fi

echo "Starting Investment Advisor Platform (Local Mode)..."

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Running Data Migration (if configured)..."
# Check DB_TYPE in .env
if grep -q "DB_TYPE=postgres" .env; then
    python3 scripts/migrate_data.py
    echo "Migration script executed."
else
    echo "DB_TYPE not set to postgres in .env. Skipping data migration."
fi

echo "Starting Dashboard..."
# Run Streamlit in background or foreground? Usually foreground for local dev.
echo "Access Dashboard at http://localhost:8501"
export PYTHONPATH=$PYTHONPATH:.
streamlit run src/dashboard.py
