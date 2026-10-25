
#!/bin/bash
export PYTHONPATH=$(pwd)
: "${VERIFY_USER_ID:?set VERIFY_USER_ID to the user to verify}"
echo "=== DAILY REPORT VERIFICATION ==="
python3 src/cli.py --mode daily --user_id "$VERIFY_USER_ID" --force-report

echo -e "\n\n=== WEEKLY REPORT VERIFICATION ==="
python3 src/cli.py --mode weekly --user_id "$VERIFY_USER_ID" --force-report
