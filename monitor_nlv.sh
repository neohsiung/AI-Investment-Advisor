#!/bin/bash

# 24-Hour NLV/P&L Monitoring Script
# Logs eToro account equity every 5 minutes

LOG_FILE="./nlv_monitoring_$(date +%Y%m%d_%H%M%S).log"
API_BASE="http://localhost:8000"
USER_ID="90693c07-6177-42df-97d9-915f3ce7c573"

echo "🔍 Starting 24-Hour NLV/P&L Monitoring"
echo "📊 Logging to: $LOG_FILE"
echo "---" | tee -a "$LOG_FILE"

# Function to fetch current eToro account equity
fetch_nlv() {
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Query database directly for current portfolio values
    NLV=$(docker exec advisor_prod_db psql -U postgres -d portfolio -t -c "
        SELECT COALESCE(SUM(pl.quantity * pl.open_price), 0)
        FROM position_lots pl
        WHERE pl.user_id = '$USER_ID' AND pl.is_open = true;
    " 2>/dev/null)
    
    # Query unrealized P&L
    UNREALIZED=$(docker exec advisor_prod_db psql -U postgres -d portfolio -t -c "
        SELECT COALESCE(SUM((pl.close_price - pl.open_price) * pl.quantity), 0)
        FROM position_lots pl
        WHERE pl.user_id = '$USER_ID' AND pl.is_open = true AND pl.close_price IS NOT NULL;
    " 2>/dev/null)
    
    # Query total transactions for realized P&L
    REALIZED=$(docker exec advisor_prod_db psql -U postgres -d portfolio -t -c "
        SELECT COALESCE(SUM(
            CASE 
                WHEN t.action IN ('SELL') THEN (t.price - 
                    (SELECT AVG(open_price) FROM position_lots WHERE source_tx_id = t.id)
                ) * t.quantity
                ELSE 0
            END
        ), 0)
        FROM transactions t
        WHERE t.user_id = '$USER_ID' AND t.action IN ('SELL');
    " 2>/dev/null)
    
    # Expected values from Issue #4 fix
    EXPECTED_NLV="1105.33"
    EXPECTED_PL="314.64"
    
    # Format output
    LOG_ENTRY="[$TIMESTAMP] NLV: \$$NLV | Unrealized: \$$UNREALIZED | Realized: \$$REALIZED | Status: ✓"
    
    echo "$LOG_ENTRY" | tee -a "$LOG_FILE"
    
    # Check for significant drift (>1% variance)
    if (( $(echo "$NLV < 1094" | bc -l) )); then
        echo "⚠️  WARNING: NLV drift detected! Value: \$$NLV (Expected: \$$EXPECTED_NLV)" | tee -a "$LOG_FILE"
    fi
}

# Main monitoring loop (24 hours = 288 * 5-minute intervals)
INTERVAL=300  # 5 minutes
DURATION=$((24 * 60 * 60))  # 24 hours
ELAPSED=0

while [ $ELAPSED -lt $DURATION ]; do
    fetch_nlv
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    
    # Print progress
    HOURS_REMAINING=$((($DURATION - $ELAPSED) / 3600))
    echo "⏱️  Time remaining: ${HOURS_REMAINING}h | Next check in 5m..." >> "$LOG_FILE"
done

echo "---" | tee -a "$LOG_FILE"
echo "✅ 24-Hour Monitoring Complete" | tee -a "$LOG_FILE"
echo "📊 Results saved to: $LOG_FILE"
