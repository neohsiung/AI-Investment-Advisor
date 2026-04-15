#!/bin/bash

# 🔍 投資顧問系統 - 深度監控檢查 (10 分鐘)
# Usage: bash scripts/health_check_deep.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo "🔍 Investment Advisor - Deep Monitoring Check"
echo "=============================================="
echo "Time: $TIMESTAMP"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# === 1. API Error Logs ===
echo -e "${BLUE}1️⃣  API Error Logs (last 15):${NC}"
docker logs advisor_prod_api 2>&1 | grep -i "error\|failed\|exception\|critical" | tail -15 || echo "  No errors found"
echo ""

# === 2. Scheduler Status ===
echo -e "${BLUE}2️⃣  Scheduler Status (last 10):${NC}"
docker logs advisor_prod_scheduler 2>&1 | tail -10
echo ""

# === 3. n8n Status ===
echo -e "${BLUE}3️⃣  n8n Workflow Status:${NC}"
n8n_status=$(curl -s http://localhost:5678/rest/health 2>/dev/null | jq '.status' 2>/dev/null || echo "unavailable")
echo "  Status: $n8n_status"
echo ""

# === 4. Database Health ===
echo -e "${BLUE}4️⃣  Database Health:${NC}"
conn_count=$(docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT COUNT(*) FROM pg_stat_activity;" 2>/dev/null | tail -1)
echo "  Active connections: $conn_count"

# Check for slow queries
echo "  Checking for transactions..."
tx_count=$(docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null | tail -1 | tr -d ' ')
echo "  Total transactions: $tx_count"

# Verify billing_cycle_start column exists
billing_col=$(docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='current_billing_cycle_start');" 2>/dev/null | tail -1)
echo "  current_billing_cycle_start exists: $billing_col"
echo ""

# === 5. Redis Cache Status ===
echo -e "${BLUE}5️⃣  Redis Cache Status:${NC}"
redis_info=$(docker exec advisor_prod_cache redis-cli INFO stats 2>/dev/null | grep -E "total_commands_processed|connected_clients" || echo "unavailable")
echo "$redis_info"
echo ""

# === 6. SigNoz Tracing ===
echo -e "${BLUE}6️⃣  SigNoz APM Status:${NC}"
signoz_status=$(curl -s http://localhost:8080/api/v1/health 2>/dev/null | jq '.status' 2>/dev/null || echo "unavailable")
echo "  Status: $signoz_status"
echo ""

# === 7. Portfolio Data Drift ===
echo -e "${BLUE}7️⃣  Portfolio Data Stability:${NC}"
portfolio=$(curl -s "http://localhost:8000/api/portfolio" 2>/dev/null | jq '.' 2>/dev/null)
if [ -n "$portfolio" ] && [ "$portfolio" != "null" ]; then
    nlv=$(echo "$portfolio" | jq '.nlv')
    pnl=$(echo "$portfolio" | jq '.pnl')
    echo "  NLV: $nlv (target: $1,105.33)"
    echo "  P&L: $pnl (target: $314.64)"
    
    # Calculate drift
    nlv_expected=1105.33
    nlv_current=$(echo "$nlv" | tr -d '$' | tr -d ',')
    if (( $(echo "$nlv_current - $nlv_expected" | bc | sed 's/-//g') > 10 )); then
        echo -e "  ${RED}⚠️  NLV drift detected (> $10)${NC}"
    else
        echo -e "  ${GREEN}✅ NLV within tolerance${NC}"
    fi
else
    echo "  Portfolio API unavailable"
fi
echo ""

# === 8. Container Resource Usage ===
echo -e "${BLUE}8️⃣  Container Resource Usage:${NC}"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep advisor || echo "  No stats available"
echo ""

# === 9. Recent Errors Summary ===
echo -e "${BLUE}9️⃣  Error Summary (all containers):${NC}"
api_errors=$(docker logs advisor_prod_api 2>&1 | grep -i "error" | wc -l)
scheduler_errors=$(docker logs advisor_prod_scheduler 2>&1 | grep -i "error" | wc -l)
n8n_errors=$(docker logs advisor_prod_n8n 2>&1 | grep -i "error" | wc -l)

echo "  API errors (last 100 lines): $api_errors"
echo "  Scheduler errors: $scheduler_errors"
echo "  n8n errors: $n8n_errors"
echo ""

# === 10. Webhook Execution History (n8n) ===
echo -e "${BLUE}🔟 n8n Webhook Executions (last 5):${NC}"
n8n_execs=$(curl -s "http://localhost:5678/rest/executions?limit=5" 2>/dev/null | jq '.[] | {id, status, startedAt, finishedAt}' 2>/dev/null || echo "unavailable")
echo "$n8n_execs"
echo ""

echo "=============================================="
echo "✅ Deep check completed at $TIMESTAMP"
