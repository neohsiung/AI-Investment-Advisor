#!/bin/bash

# 🚀 投資顧問系統 - 快速健康檢查 (2 分鐘)
# Usage: bash scripts/health_check_quick.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
FAILED=0

echo "🚀 Investment Advisor - Quick Health Check"
echo "=========================================="
echo "Time: $TIMESTAMP"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}
    
    response=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null || echo -e "\n000")
    code=$(echo "$response" | tail -n 1)
    
    if [ "$code" = "$expected_code" ]; then
        echo -e "${GREEN}✅${NC} $name (HTTP $code)"
        return 0
    else
        echo -e "${RED}❌${NC} $name (HTTP $code, expected $expected_code)"
        ((FAILED++))
        return 1
    fi
}

check_container() {
    local name=$1
    local pattern=$2
    
    if docker ps | grep -q "$pattern"; then
        echo -e "${GREEN}✅${NC} $name (running)"
        return 0
    else
        echo -e "${RED}❌${NC} $name (NOT RUNNING)"
        ((FAILED++))
        return 1
    fi
}

check_database() {
    if docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} PostgreSQL (connected)"
        return 0
    else
        echo -e "${RED}❌${NC} PostgreSQL (connection failed)"
        ((FAILED++))
        return 1
    fi
}

# === HTTP Endpoints ===
echo "📱 HTTP Endpoints:"
check_endpoint "  Frontend" "http://localhost:3000"
check_endpoint "  API Health" "http://localhost:8000/health"

# === Containers ===
echo ""
echo "🐳 Docker Containers:"
check_container "  Frontend UI" "advisor_prod_ui"
check_container "  API (MCP)" "advisor_prod_api"
check_container "  Scheduler" "advisor_prod_scheduler"
check_container "  n8n" "advisor_prod_n8n"
check_container "  PostgreSQL" "advisor_prod_db"
check_container "  Redis" "advisor_prod_cache"

# === Database ===
echo ""
echo "🗄️  Database:"
check_database

# === Portfolio Data ===
echo ""
echo "💰 Portfolio Data:"
nlv_response=$(curl -s "http://localhost:8000/api/portfolio" 2>/dev/null | jq '.nlv' 2>/dev/null || echo "null")
pnl_response=$(curl -s "http://localhost:8000/api/portfolio" 2>/dev/null | jq '.pnl' 2>/dev/null || echo "null")

if [ "$nlv_response" != "null" ]; then
    echo -e "${GREEN}✅${NC} Portfolio API (NLV: $nlv_response, P&L: $pnl_response)"
else
    echo -e "${RED}❌${NC} Portfolio API (unreachable or invalid response)"
    ((FAILED++))
fi

# === Summary ===
echo ""
echo "=========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILED CHECK(S) FAILED${NC}"
    exit 1
fi
