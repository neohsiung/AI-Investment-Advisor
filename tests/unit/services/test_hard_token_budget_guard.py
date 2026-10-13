"""
Unit Tests for HardTokenBudgetGuardService and DeterministicCouncilService (Phase 47)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from src.services.hard_token_budget_guard_service import (
    HardTokenBudgetGuardService,
    TokenBudgetStatus,
)
from src.services.deterministic_council_service import (
    DeterministicCouncilService,
    DeterministicDecision,
)


@pytest.fixture
def mock_token_logger():
    logger_mock = MagicMock()
    # Default spending: $0.02 daily, $0.80 monthly
    logger_mock.get_user_spending.side_effect = lambda uid, days: {
        "total_cost": 0.02 if days == 1 else 0.80,
        "call_count": 10,
    }
    return logger_mock


@pytest.fixture
def mock_settings_service():
    settings_mock = MagicMock()
    settings_dict = {
        "enable_hard_token_budget_guard": True,
        "daily_llm_budget_usd": 0.10,
        "monthly_llm_budget_usd": 2.50,
        "enable_sentinel_zero_llm_mode": True,
        "enable_deterministic_council_fallback": True,
    }
    settings_mock.get_setting.side_effect = lambda k, default=None: settings_dict.get(k, default)
    return settings_mock


def test_budget_status_normal(mock_token_logger, mock_settings_service):
    guard = HardTokenBudgetGuardService(user_id="test_user")
    guard._token_logger = mock_token_logger
    guard._settings_service = mock_settings_service

    status = guard.get_budget_status()
    assert isinstance(status, TokenBudgetStatus)
    assert not status.is_hard_locked
    assert status.daily_spent_usd == 0.02
    assert status.monthly_spent_usd == 0.80
    assert status.daily_cap_usd == 0.10
    assert status.monthly_cap_usd == 2.50
    assert status.remaining_monthly_usd == 1.70
    assert status.zero_llm_mode_active is True

    # Check should_allow_llm
    allow_sentinel, reason_s = guard.should_allow_llm("sentinel_monitor")
    assert not allow_sentinel
    assert "SENTINEL_ZERO_LLM_ENFORCED" in reason_s

    allow_rebalance, reason_r = guard.should_allow_llm("routine_rebalance")
    assert not allow_rebalance
    assert "DETERMINISTIC_COUNCIL_ENFORCED" in reason_r

    allow_chat, reason_c = guard.should_allow_llm("user_chat", is_user_direct_chat=True)
    assert allow_chat
    assert reason_c == "BUDGET_PERMITTED"


def test_budget_status_daily_lockout(mock_settings_service):
    guard = HardTokenBudgetGuardService(user_id="test_user")
    guard._settings_service = mock_settings_service

    token_logger = MagicMock()
    token_logger.get_user_spending.side_effect = lambda uid, days: {
        "total_cost": 0.15 if days == 1 else 1.20,
    }
    guard._token_logger = token_logger

    status = guard.get_budget_status()
    assert status.is_hard_locked is True
    assert "DAILY_LIMIT_BREACHED" in status.lockout_reason

    # Normal tasks blocked
    allow, reason = guard.should_allow_llm("macro_news")
    assert not allow
    assert "HARD_BUDGET_LOCKOUT" in reason

    # Direct user chat exception permitted
    allow_chat, reason_chat = guard.should_allow_llm("user_chat", is_user_direct_chat=True)
    assert allow_chat is True
    assert reason_chat == "USER_DIRECT_CHAT_EXCEPTION"


def test_budget_status_monthly_lockout(mock_settings_service):
    guard = HardTokenBudgetGuardService(user_id="test_user")
    guard._settings_service = mock_settings_service

    token_logger = MagicMock()
    token_logger.get_user_spending.side_effect = lambda uid, days: {
        "total_cost": 0.05 if days == 1 else 3.10,
    }
    guard._token_logger = token_logger

    status = guard.get_budget_status()
    assert status.is_hard_locked is True
    assert "MONTHLY_LIMIT_BREACHED" in status.lockout_reason
    assert status.pct_used_monthly > 100.0


def test_budget_reset(mock_settings_service):
    guard = HardTokenBudgetGuardService(user_id="test_user")
    guard._settings_service = mock_settings_service

    redis_mock = MagicMock()
    guard._redis_client = redis_mock

    res = guard.reset_budget_lockout()
    assert res.get("status") == "RESET_SUCCESSFUL"
    assert "reset_at" in res
    redis_mock.setex.assert_called_once()


@pytest.mark.asyncio
async def test_deterministic_council_service():
    council = DeterministicCouncilService(user_id="test_user")

    # Mock market data service
    mkt_mock = MagicMock()
    dates = pd.date_range("2026-09-01", periods=30, freq="D")
    prices = np.linspace(100.0, 130.0, 30)  # Strong upward trend
    df = pd.DataFrame({
        "Open": prices * 0.99,
        "High": prices * 1.02,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": 1000000,
    }, index=dates)
    mkt_mock.get_history_df.return_value = df
    council._market_data_service = mkt_mock

    decision = await council.evaluate_ticker_stance("NVDA", current_holding_shares=0)
    assert isinstance(decision, DeterministicDecision)
    assert decision.ticker == "NVDA"
    assert decision.action == "BUY"
    assert decision.confidence_score > 0.60
    assert decision.recommended_allocation_pct > 0.05
    assert "0_LLM_DETERMINISTIC_COUNCIL" in decision.to_dict()["engine"]
