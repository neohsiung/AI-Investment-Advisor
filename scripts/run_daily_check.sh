#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Navigate to project root
cd "$PROJECT_ROOT"

# Set PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT"

# Run Workflow in Daily Mode
echo "Starting Daily Momentum Scan (v3.2)..."
# Using test_user for verification
python3 src/cli.py --mode daily --user_id test_user --force-report

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Daily Scan Completed."
else
    echo "Daily Scan Failed. Exit Code: $EXIT_CODE"
    osascript -e 'display notification "Daily Scan Failed" with title "AI Advisor Error"'
fi
