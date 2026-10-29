#!/bin/bash

# 🔍 投資顧問系統 - 深度監控檢查
# Usage: bash scripts/health_check_deep.sh
#
# 每一項檢查找不到目標就記為失敗並讓結尾的 exit code 非零，不印空白當作通過。
# Every check that cannot reach its target counts as a failure and makes the exit code
# non-zero; it never prints a blank and moves on.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

DB_CONTAINER="advisor_prod_db"
DB_NAME="advisor_prod"
CONTAINERS="advisor_prod_api advisor_prod_worker advisor_prod_beat advisor_prod_cache advisor_prod_db advisor_prod_gateway"
GATEWAY="http://localhost:8088"
# 排程停擺門檻：sentinel_tick 每 15 分鐘一次，超過這麼久沒有成功即視為缺口
# Schedule-stall threshold: sentinel_tick runs every 15 minutes
STALE_MINUTES=45

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
FAILED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✅${NC} $*"; }
fail() { echo -e "  ${RED}❌${NC} $*"; FAILED=$((FAILED + 1)); }

# Run SQL against the prod DB; prints the single value, returns non-zero on error.
sql() {
    docker exec "$DB_CONTAINER" psql -U postgres -d "$DB_NAME" -At -c "$1" 2>&1
}

echo "🔍 Investment Advisor - Deep Monitoring Check"
echo "=============================================="
echo "Time: $TIMESTAMP"
echo ""

# === 1. Containers ===
echo -e "${BLUE}1️⃣  Containers:${NC}"
for c in $CONTAINERS; do
    state=$(docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}/restarts={{.RestartCount}}' "$c" 2>/dev/null)
    if [ -z "$state" ]; then
        fail "$c not found"
    elif [[ "$state" == running/* && "$state" != */unhealthy/* ]]; then
        ok "$c $state"
    else
        fail "$c $state"
    fi
done
echo ""

# === 2. Gateway / API ===
echo -e "${BLUE}2️⃣  API via gateway:${NC}"
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$GATEWAY/health" 2>/dev/null)
if [ "$code" = "200" ]; then ok "$GATEWAY/health HTTP $code"; else fail "$GATEWAY/health HTTP ${code:-none}"; fi
echo ""

# === 3. Database ===
echo -e "${BLUE}3️⃣  Database ($DB_NAME):${NC}"
conns=$(sql "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$DB_NAME';")
if [[ "$conns" =~ ^[0-9]+$ ]]; then ok "active connections: $conns"; else fail "pg_stat_activity: $conns"; fi
tx=$(sql "SELECT COUNT(*) FROM transactions;")
if [[ "$tx" =~ ^[0-9]+$ ]]; then ok "transactions rows: $tx"; else fail "transactions: $tx"; fi
echo ""

# === 4. Schedule output (beat -> worker -> task_runs) ===
echo -e "${BLUE}4️⃣  Schedule output:${NC}"
age=$(sql "SELECT COALESCE(ROUND(EXTRACT(EPOCH FROM (NOW() - MAX(finished_at))) / 60), -1) FROM task_runs WHERE status = 'success' AND task_name LIKE '%sentinel_tick';")
if [[ "$age" =~ ^[0-9]+$ ]] && [ "$age" -le "$STALE_MINUTES" ]; then
    ok "last successful sentinel_tick: ${age} min ago"
elif [[ "$age" =~ ^[0-9]+$ ]]; then
    fail "last successful sentinel_tick: ${age} min ago (> ${STALE_MINUTES})"
else
    fail "no successful sentinel_tick found or query failed: $age"
fi
runs=$(sql "SELECT COUNT(*) FROM task_runs WHERE finished_at > NOW() - INTERVAL '1 hour';")
if [[ "$runs" =~ ^[0-9]+$ ]]; then ok "task_runs in last hour: $runs (normal is 78-97)"; else fail "task_runs: $runs"; fi
echo ""

# === 5. Charter state ===
echo -e "${BLUE}5️⃣  Charter state:${NC}"
charter=$(sql "SELECT * FROM charter_state;")
if [ -n "$charter" ] && [[ "$charter" != ERROR* ]]; then ok "$charter"; else fail "charter_state unreadable: ${charter:-empty}"; fi
echo ""

# === 6. Redis ===
echo -e "${BLUE}6️⃣  Redis:${NC}"
# The password is expanded inside the container; it never reaches this shell.
# 密碼在容器內展開，不經過本機 shell。
pong=$(docker exec advisor_prod_cache sh -c 'redis-cli --no-auth-warning -a "$REDIS_PASSWORD" ping' 2>&1)
if [ "$pong" = "PONG" ]; then ok "redis PONG"; else fail "redis: ${pong:-no answer}"; fi
echo ""

# === 7. Errors in the last hour ===
echo -e "${BLUE}7️⃣  Errors in the last hour:${NC}"
for c in advisor_prod_api advisor_prod_worker advisor_prod_beat; do
    if ! docker inspect "$c" >/dev/null 2>&1; then
        fail "$c not found"
        continue
    fi
    n=$(docker logs --since 1h "$c" 2>&1 | grep -ciE "error|exception|critical")
    echo "  $c: $n lines matching error/exception/critical"
done
echo ""

# === 8. Container resource usage ===
echo -e "${BLUE}8️⃣  Container resource usage:${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep advisor_prod \
    || fail "docker stats returned nothing for advisor_prod"
echo ""

echo "=============================================="
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ Deep check passed at $TIMESTAMP${NC}"
    exit 0
fi
echo -e "${RED}❌ Deep check: $FAILED failed item(s) at $TIMESTAMP${NC}"
exit 1
