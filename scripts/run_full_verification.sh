
#!/bin/bash
export PYTHONPATH=$(pwd)
echo "=== DAILY REPORT VERIFICATION ==="
python3 src/cli.py --mode daily --user_id supermfb@gmail.com --force-report

echo -e "\n\n=== WEEKLY REPORT VERIFICATION ==="
python3 src/cli.py --mode weekly --user_id supermfb@gmail.com --force-report
