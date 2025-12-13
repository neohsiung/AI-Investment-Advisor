#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Navigate to project root
cd "$PROJECT_ROOT"

# Set PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT"

# Run Workflow in Weekly Mode
echo "Starting Weekly Investment Report Generation..."
python3 src/workflow.py --mode weekly

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Weekly Report Generated Successfully."
    # Optional: Send system notification on macOS
    osascript -e 'display notification "Investment Report Ready" with title "AI Advisor"'
else
    echo "Error generating report. Exit Code: $EXIT_CODE"
    osascript -e 'display notification "Report Generation Failed" with title "AI Advisor Error"'
fi
