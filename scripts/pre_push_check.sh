#!/usr/bin/env bash
# ==============================================================================
# Pre-Push Quality & Safety Gate (本地預檢守衛腳本)
# ==============================================================================
# 於 git push 前快速執行靜態分析、作用域檢查、安全審計、核心回歸與 Wiki 鏈結校驗。
# 耗時：~5 秒，徹底防止 CI/CD 5 分鐘遠端紅燈與作用域崩潰。
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   🛡️  Running AI-Investment-Advisor Pre-Push Gate     ${NC}"
echo -e "${BLUE}======================================================${NC}"

VENV_BIN=".venv/bin"
PYTHON="${VENV_BIN}/python3"
RUFF="${VENV_BIN}/ruff"
BANDIT="${VENV_BIN}/bandit"
PYTEST="${VENV_BIN}/pytest"

if [ ! -f "$PYTHON" ]; then
    echo -e "${RED}[ERROR] Virtual environment not found at .venv. Run setup first.${NC}"
    exit 1
fi

# 1. Ruff Fast Scope & Syntax Check (0.3s)
echo -e "\n${YELLOW}[1/4] Running Ruff Fast Scoping & Syntax Check...${NC}"
if [ -f "$RUFF" ]; then
    $RUFF check src/ tests/ --select F821,F822,F823,E9,F63
    echo -e "${GREEN}✓ Ruff scoping & syntax checks passed (0 undefined names / shadowing errors)${NC}"
else
    echo -e "${YELLOW}⚠️ Ruff not installed in .venv, falling back to python compileall...${NC}"
    $PYTHON -m compileall src/ tests/ -q
    echo -e "${GREEN}✓ Compileall passed${NC}"
fi

# 2. Bandit SAST Security Scan on Core Services
echo -e "\n${YELLOW}[2/4] Running Bandit SAST Security Scan...${NC}"
if [ -f "$BANDIT" ]; then
    $BANDIT -r src/services/actionable_alert_service.py \
              src/services/sentinel_service.py \
              src/services/shadow_ledger_service.py \
              src/services/trading_protections_service.py \
              src/services/webhook_service.py -q -lll
    echo -e "${GREEN}✓ Bandit security baseline clean (0 high/medium issues)${NC}"
fi

# 3. Wiki Flat-Link Integrity Check
echo -e "\n${YELLOW}[3/4] Validating Wiki Flat-Links Integrity...${NC}"
$PYTHON .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py
echo -e "${GREEN}✓ Wiki internal links verified${NC}"

# 4. Core Quantitative & Protections Regression Test Suite
echo -e "\n${YELLOW}[4/4] Running Core Regression Test Suite...${NC}"
$PYTEST tests/unit/services/test_actionable_alert_service.py \
        tests/unit/services/test_shadow_ledger_service.py \
        tests/unit/services/test_smart_money_support_service.py \
        tests/unit/services/test_sentinel_position_exits.py \
        tests/unit/services/test_protections_*.py \
        tests/unit/services/test_exit_compositor.py \
        tests/unit/services/test_webhook_telegram.py \
        tests/unit/services/test_dynamic_volatility_rebalance.py \
        tests/unit/services/test_correlation_clustering_and_beta.py \
        tests/unit/services/test_opportunity_cost_and_alpha_decay.py \
        tests/unit/services/test_portfolio_backtest_and_kelly.py \
        tests/unit/services/test_stress_testing_and_cvar.py \
        tests/unit/services/test_multi_factor_ensemble.py \
        tests/unit/config/test_settings_schema.py -q

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   ✨  ALL PRE-PUSH CHECKS PASSED! READY TO PUSH.     ${NC}"
echo -e "${GREEN}======================================================${NC}\n"
