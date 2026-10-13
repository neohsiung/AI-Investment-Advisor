"""
Unit tests for Net Alpha & Cash Drag Attribution Service
測試實時淨 Alpha 歸因與現金拖累量化服務 (Phase 44)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.services.net_alpha_attribution_service import (
    CashDragMetrics,
    NetAlphaAttributionReport,
    NetAlphaAttributionService,
)


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    account = MagicMock()
    account.total_equity = 1800.00
    account.available_cash = 1000.00
    broker.get_account.return_value = account
    return broker


@pytest.fixture
def mock_settings_service():
    settings = MagicMock()
    settings.get_setting.side_effect = lambda key, default=None: {
        "initial_capital_deposited_usd": 1711.00,
        "target_annual_net_alpha_pct": 0.10,
        "monthly_saas_subscription_cost_usd": 0.0,
        "enable_net_alpha_attribution": True,
    }.get(key, default)
    return settings


@pytest.fixture
def mock_market_data_service():
    mkt = MagicMock()
    # 模擬 SPY 報酬率：30 天前 500 -> 現價 510 (+2.0%)
    df_spy = pd.DataFrame(
        {"close": [500.0, 505.0, 510.0]},
        index=pd.date_range("2026-09-01", periods=3, freq="D"),
    )
    # 模擬候選標的報酬率：30 天前 100 -> 現價 108 (+8.0%)
    df_cand = pd.DataFrame(
        {"close": [100.0, 104.0, 108.0]},
        index=pd.date_range("2026-09-01", periods=3, freq="D"),
    )

    def _get_history(sym, days=30):
        if sym == "SPY":
            return df_spy
        return df_cand

    mkt.get_history_df.side_effect = _get_history
    return mkt


@pytest.fixture
def mock_token_logger_service():
    token_svc = MagicMock()
    token_svc.get_user_spending.return_value = {
        "total_cost": 0.50,
        "total_tokens": 150000,
    }
    return token_svc


def test_calculate_complete_report_bull_market(
    mock_broker, mock_settings_service, mock_market_data_service, mock_token_logger_service
):
    """驗證一般行情下完整淨 Alpha 與現金拖累計算"""
    async def _test():
        svc = NetAlphaAttributionService(
            user_id="test_user",
            settings_service=mock_settings_service,
            broker=mock_broker,
            market_data_service=mock_market_data_service,
            token_logger_service=mock_token_logger_service,
        )

        report = await svc.calculate_complete_report(lookback_days=30)

        assert report.user_id == "test_user"
        assert report.lookback_days == 30
        assert report.initial_capital_usd == 1711.00
        assert report.current_equity_usd == 1800.00
        assert report.portfolio_pnl_usd == 89.00
        assert round(report.portfolio_return_pct, 4) == round(89.0 / 1711.0, 4)

        # SPY 報酬率: (510 - 500) / 500 = 0.02 (2.0%)
        assert round(report.spy_return_pct, 4) == 0.02
        assert round(report.gross_alpha_pct, 4) == round(report.portfolio_return_pct - 0.02, 4)

        # LLM 成本: $0.50, cost_drag = 0.50 / 1711.0
        assert report.llm_cost_usd == 0.50
        assert report.cost_drag_pct > 0
        assert round(report.net_alpha_pct, 4) == round(report.gross_alpha_pct - report.cost_drag_pct, 4)

        # 現金指標
        cm = report.cash_metrics
        assert cm.total_cash_usd == 1000.00
        assert round(cm.cash_ratio_pct, 4) == round(1000.0 / 1800.0, 4)
        assert cm.defensive_reserve_usd == 1800.0 * 0.20
        assert cm.excess_idle_cash_usd == 1000.0 - 360.0
        assert cm.cash_drag_usd > 0  # 候選股漲 8% > 國庫券，產生拖累

    asyncio.run(_test())


def test_cash_downside_protection_bear_market(
    mock_settings_service, mock_token_logger_service
):
    """驗證市場大跌時，現金提供顯著的下行保護與 OPTIMAL_DEFENSE 評級"""
    async def _test():
        broker = AsyncMock()
        account = MagicMock()
        account.total_equity = 1700.00
        account.available_cash = 1200.00  # 高現金
        broker.get_account.return_value = account

        mkt = MagicMock()
        # SPY 大跌 -5.0%: 500 -> 475
        df_spy_down = pd.DataFrame(
            {"close": [500.0, 485.0, 475.0]},
            index=pd.date_range("2026-09-01", periods=3, freq="D"),
        )
        # 候選標的亦回檔 -2.0%
        df_cand_down = pd.DataFrame(
            {"close": [100.0, 99.0, 98.0]},
            index=pd.date_range("2026-09-01", periods=3, freq="D"),
        )

        def _get_history(sym, days=30):
            if sym == "SPY":
                return df_spy_down
            return df_cand_down

        mkt.get_history_df.side_effect = _get_history

        svc = NetAlphaAttributionService(
            user_id="test_user",
            settings_service=mock_settings_service,
            broker=broker,
            market_data_service=mkt,
            token_logger_service=mock_token_logger_service,
        )

        report = await svc.calculate_complete_report(lookback_days=30)
        cm = report.cash_metrics

        assert report.spy_return_pct == -0.05
        assert cm.downside_saved_usd == 1200.0 * 0.05  # 挽回 $60.00 虧損
        assert cm.cash_drag_usd == 0.0                 # 標的回檔無機會成本
        assert cm.cash_health_rating == "OPTIMAL_DEFENSE"
        assert "下行保護" in cm.health_rationale

    asyncio.run(_test())


def test_format_telegram_report(
    mock_broker, mock_settings_service, mock_market_data_service, mock_token_logger_service
):
    """驗證 Telegram HTML 戰報格式排版合規"""
    async def _test():
        svc = NetAlphaAttributionService(
            user_id="test_user",
            settings_service=mock_settings_service,
            broker=mock_broker,
            market_data_service=mock_market_data_service,
            token_logger_service=mock_token_logger_service,
        )

        report = await svc.calculate_complete_report(lookback_days=30)
        html_text = svc.format_telegram_report(report)

        assert "實時淨 Alpha 歸因與現金拖累儀表" in html_text
        assert "初始本金" in html_text
        assert "當前權益" in html_text
        assert "毛超額報酬 (Gross Alpha)" in html_text
        assert "總運營成本折損率" in html_text
        assert "扣費後實時淨 Alpha 財務指標" in html_text
        assert "現金配置度量與機會成本分析" in html_text
        assert "/dipbuy plan" in html_text

    asyncio.run(_test())


def test_conversation_router_alpha_command(
    mock_broker, mock_settings_service, mock_market_data_service, mock_token_logger_service
):
    """驗證 ConversationRouter 的 /alpha 0-LLM 指令與週期解析"""
    async def _test():
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        assert router._is_system_command("/alpha") is True
        assert router._is_system_command("/alpha 7") is True
        assert router._is_system_command("/alpha ytd") is True
        assert router._is_system_command("/netalpha") is True
        assert router._is_system_command("成本歸因") is True

        mock_svc = MagicMock()
        mock_report = MagicMock()
        mock_svc.calculate_complete_report = AsyncMock(return_value=mock_report)
        mock_svc.format_telegram_report.return_value = "<b>TEST_ALPHA_REPORT</b>"

        with patch("src.services.net_alpha_attribution_service.NetAlphaAttributionService", return_value=mock_svc):
            reply = await router._handle_system_command(
                adapter=None,
                channel_user_id="test_channel",
                text="/alpha 7",
                resolved_user_id="test_user",
            )
            assert reply == "<b>TEST_ALPHA_REPORT</b>"
            mock_svc.calculate_complete_report.assert_awaited_once_with(lookback_days=7)

    asyncio.run(_test())
