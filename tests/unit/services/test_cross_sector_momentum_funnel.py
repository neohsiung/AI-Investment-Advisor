"""
Unit Tests for Cross-Sector Momentum Funnel, HHI De-concentration, and Workflow Deduplication
=============================================================================================
Tests:
1. Portfolio sector holdings analysis & HHI index calculation
2. Cross-sector contender dynamic scouting & blackout avoidance
3. Batch cash deployment cross-sector injection & quota scaling
4. Workflow deduplication & single-execution pipeline (staggered dip delegation)
5. 0-LLM /sector system command & multi-channel formatting
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.sector_drift_guard_service import (
    SECTOR_THEME_LEADERS,
    PortfolioSectorReport,
    SectorDistribution,
    SectorDriftGuardService,
    SectorDriftStatus,
)
from src.services.batch_cash_deployment_service import BatchCashDeploymentService


class DummySettingsService:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def get(self, user_id: str, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


class MockPosition:
    def __init__(self, symbol: str, market_value: float):
        self.symbol = symbol
        self.market_value = market_value


# ============================================================================
# 1. Portfolio Sector Holdings & HHI Tests
# ============================================================================

class TestPortfolioSectorHoldings:
    @pytest.fixture
    def drift_guard(self):
        settings = DummySettingsService({
            "enable_sector_drift_guard": True,
            "sector_concentration_cap_pct": 0.30,
            "sector_drift_warning_pct": 0.25,
            "portfolio_hhi_breach_threshold": 0.25,
            "tech_sector_concentration_cap_pct": 0.30,
            "enable_cross_sector_momentum_injection": True,
            "cross_sector_injection_quota_pct": 0.35,
        })
        repo = MagicMock()
        repo.get_all.return_value = []
        repo.get.return_value = None
        market = MagicMock()
        market.get_financials.return_value = None
        return SectorDriftGuardService(
            user_id="test_user",
            settings_service=settings,
            repo=repo,
            market=market,
        )

    def test_analyze_portfolio_holdings_balanced(self, drift_guard):
        # 6 diverse sectors: Technology, Financials, Energy, Healthcare, Consumer Staples, Industrials
        positions = [
            MockPosition("AAPL", 150.0),    # Technology (16.7%)
            MockPosition("JPM", 150.0),     # Financials (16.7%)
            MockPosition("XOM", 150.0),     # Energy (16.7%)
            MockPosition("JNJ", 150.0),     # Healthcare (16.7%)
            MockPosition("WMT", 150.0),     # Consumer Staples (16.7%)
            MockPosition("CAT", 150.0),     # Industrials (16.7%)
        ]
        total_equity = 1500.0  # stock value 900 (60%), cash 600 (40%)
        report = drift_guard.analyze_portfolio_holdings(positions, total_equity=total_equity)

        assert report.status == SectorDriftStatus.BALANCED
        assert report.total_stock_value == 900.0
        assert report.total_equity == 1500.0
        assert len(report.over_concentrated_sectors) == 0
        assert len(report.warning_sectors) == 0
        # 6 sectors equal weight (0.1667 each): HHI = 6 * (0.1667^2) = ~0.167 (< 0.18)
        assert report.hhi_index < 0.18

    def test_analyze_portfolio_holdings_tech_breach(self, drift_guard):
        # 100% tech holdings mimicking production
        positions = [
            MockPosition("NVDA", 250.0),
            MockPosition("AAPL", 200.0),
            MockPosition("MSFT", 150.0),
            MockPosition("TSM", 100.0),
        ]
        total_equity = 1600.0  # stock value 700, cash 900
        report = drift_guard.analyze_portfolio_holdings(positions, total_equity=total_equity)

        assert report.status == SectorDriftStatus.DRIFT_BREACH
        assert "Technology" in report.sector_weights
        assert report.sector_weights["Technology"] == 1.0  # 100% of stock equity
        assert report.nlv_sector_weights["Technology"] == 700.0 / 1600.0  # 43.75% of NLV (>30%)
        assert report.hhi_index == 1.0  # Single sector HHI = 1.0
        assert "Technology" in report.over_concentrated_sectors
        assert len(report.recommendations) > 0
        assert any("實盤板塊過度集中警告" in r for r in report.recommendations)

    def test_analyze_portfolio_holdings_defensive_unpacking(self, drift_guard):
        # Position objects, dicts, None values
        mixed_positions = [
            {"symbol": "COP.US", "market_value": 150.0},
            MockPosition("ECL", 100.0),
            {"ticker": "CASH", "market_value": 500.0},  # should be skipped
            None,
        ]
        report = drift_guard.analyze_portfolio_holdings(mixed_positions, total_equity=1000.0)
        assert report.total_stock_value == 250.0
        assert "Energy" in report.sector_weights
        assert "Materials" in report.sector_weights


# ============================================================================
# 2. Cross-Sector Contender Scouting & Blackout Tests
# ============================================================================

class TestCrossSectorScouting:
    @pytest.fixture
    def drift_guard(self):
        settings = DummySettingsService({
            "enable_cross_sector_momentum_injection": True,
            "cross_sector_injection_quota_pct": 0.35,
        })
        repo = MagicMock()
        return SectorDriftGuardService(
            user_id="test_user",
            settings_service=settings,
            repo=repo,
        )

    def test_discover_cross_sector_injection_contender_curated(self, drift_guard):
        # Current holdings are 100% Tech
        positions = [MockPosition("NVDA", 300.0), MockPosition("AAPL", 200.0)]
        contender = drift_guard.discover_cross_sector_injection_contender(
            current_positions=positions,
            total_equity=1000.0,
        )
        assert contender is not None
        assert contender["ticker"] not in ("NVDA", "AAPL")
        assert contender["sector"] not in ("Technology", "Communication Services")
        assert "role" in contender

    def test_discover_cross_sector_injection_contender_with_exclusions(self, drift_guard):
        # Current holdings are Tech
        positions = [MockPosition("NVDA", 300.0)]
        # Exclude JPM and V
        contender = drift_guard.discover_cross_sector_injection_contender(
            current_positions=positions,
            total_equity=1000.0,
            excluded_tickers={"JPM", "V"},
        )
        assert contender is not None
        assert contender["ticker"] not in ("NVDA", "JPM", "V")
        assert contender["sector"] not in ("Technology", "Communication Services")


# ============================================================================
# 3. Batch Cash Deployment Cross-Sector Injection Tests
# ============================================================================

class TestBatchCashDeploymentInjection:
    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock()
        broker.get_account = AsyncMock(return_value=MagicMock(
            total_equity=1685.0,
            available_cash=1058.0,
        ))
        broker.get_positions = AsyncMock(return_value=[
            MockPosition("NVDA", 250.0),
            MockPosition("TSM", 200.0),
            MockPosition("AAPL", 177.0),
        ])
        return broker

    @pytest.fixture
    def batch_service(self, mock_broker):
        settings = DummySettingsService({
            "enable_cross_sector_momentum_injection": True,
            "cross_sector_injection_quota_pct": 0.35,
            "tech_sector_concentration_cap_pct": 0.30,
            "portfolio_hhi_breach_threshold": 0.25,
            "enable_staggered_dip_buying": True,
        })
        blackout = MagicMock()
        # Default: no blackout
        blackout.evaluate_candidate = AsyncMock(return_value=MagicMock(is_blackout=False, reason=None))
        blackout.get_upcoming_calendar_summary = AsyncMock(return_value={})

        slippage = MagicMock()
        slippage.get_ticker_quote = AsyncMock(return_value={"bid": 100.0, "ask": 100.1, "last": 100.05, "spread_pct": 0.001})

        return BatchCashDeploymentService(
            user_id="test_user",
            settings_service=settings,
            broker=mock_broker,
            blackout_guard=blackout,
            slippage_guard=slippage,
        )

    @pytest.mark.asyncio
    async def test_get_deployment_plan_injects_cross_sector(self, batch_service):
        # Portfolio is 100% tech, Batch 2 is MSFT, MU, AMD (all Tech)
        plan = await batch_service.get_deployment_plan(batch_number=2)

        assert plan["cross_sector_injection"] is not None
        inj_info = plan["cross_sector_injection"]
        assert inj_info["injected_sector"] not in ("Technology", "Communication Services")
        assert inj_info["injected_amount"] > 10.0

        # Plan items should contain the injected contender
        plan_tickers = [item["ticker"] for item in plan["items"]]
        assert inj_info["injected_ticker"] in plan_tickers
        assert any(item.get("is_cross_sector_injected") for item in plan["items"])

    @pytest.mark.asyncio
    async def test_get_deployment_plan_rotates_on_blackout(self, batch_service):
        # Simulate JPM having an active blackout, while subsequent candidates do not
        async def mock_blackout_eval(ticker):
            if ticker == "JPM":
                return MagicMock(is_blackout=True, reason="Q3 Earnings Announcement in 5 hours")
            return MagicMock(is_blackout=False, reason=None)

        batch_service.blackout_guard.evaluate_candidate = AsyncMock(side_effect=mock_blackout_eval)

        plan = await batch_service.get_deployment_plan(batch_number=2)
        assert plan["cross_sector_injection"] is not None
        # JPM should have been rotated out
        assert plan["cross_sector_injection"]["injected_ticker"] != "JPM"
        assert plan["cross_sector_injection"]["injected_ticker"] in [item["ticker"] for item in plan["items"]]


# ============================================================================
# 4. Workflow Deduplication & Staggered Delegation Tests
# ============================================================================

class TestWorkflowDeduplication:
    @pytest.fixture
    def batch_service(self):
        settings = DummySettingsService({
            "enable_staggered_dip_buying": True,
        })
        staggered_mock = MagicMock()
        staggered_mock.execute_staggered_dip_deployment = AsyncMock(return_value={
            "success": True,
            "status": "orders_placed",
            "order_count": 6,
        })
        return BatchCashDeploymentService(
            user_id="test_user",
            settings_service=settings,
            staggered_dip_service=staggered_mock,
        )

    @pytest.mark.asyncio
    async def test_execute_batch_delegates_to_staggered(self, batch_service):
        res = await batch_service.execute_batch(batch_number=2, deployment_mode="STAGGERED_LIMIT")
        assert res["status"] == "orders_placed"
        batch_service.staggered_dip_service.execute_staggered_dip_deployment.assert_awaited_once_with(
            batch_number=2,
            force=False,
        )

    def test_market_open_task_skips_when_staggered_active(self):
        from src.infrastructure.tasks import run_market_open_cash_deployment

        # Mock StaggeredDipBuyingService returning active pending orders
        with patch("src.services.staggered_dip_buying_service.StaggeredDipBuyingService") as mock_staggered_cls, \
             patch("src.utils.market_clock.MarketClock.is_market_open", return_value=True):
            instance = mock_staggered_cls.return_value
            instance.get_active_staggered_orders = AsyncMock(return_value=[
                {"ticker": "NVDA", "status": "PENDING", "limit_price": 110.0}
            ])

            res = run_market_open_cash_deployment(user_id="test_user", batch_number=1)
            assert isinstance(res, dict)
            assert res["status"] == "skipped"
            assert res["reason"] == "staggered_dip_orders_active"
            assert res["pending_orders_count"] == 1


# ============================================================================
# 5. 0-LLM /sector Command Formatting Tests
# ============================================================================

class TestSectorCommandFormatting:
    @pytest.mark.asyncio
    async def test_sector_command_response(self):
        from src.services.conversation_router import ConversationRouter

        router = ConversationRouter()

        mock_broker = MagicMock()
        mock_broker.get_account = AsyncMock(return_value=MagicMock(total_equity=1685.71, available_cash=1058.38))
        mock_broker.get_positions = AsyncMock(return_value=[
            MockPosition("AAPL", 250.0),
            MockPosition("NVDA", 200.0),
            MockPosition("MSFT", 150.0),
        ])

        with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker):
            res = await router._handle_system_command(
                adapter=MagicMock(),
                channel_user_id="test_tg",
                text="/sector",
                resolved_user_id="00000000-0000-4000-a000-000000000001",
            )
            assert res is not None

            # Verify standard notification formatting elements
            assert "實盤投資組合板塊集中度與 HHI 診斷" in res
            assert "實盤板塊 HHI 指數" in res
            assert "Technology" in res
            assert "▓" in res  # visual progress bar
            assert "跨板塊自癒配額" in res
