"""
Tests for Autonomous Reporting Service, Confidence Optimizer, and Pseudo-Ticker Filtering.
自主通報服務、置信度優化器與非權益標的過濾單元測試。
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.domain.trading import Order, OrderAction, OrderType
from src.services.autonomous_reporting_service import (
    AutonomousReportingService,
    AutonomousConfidenceOptimizer,
)
from src.services.automated_trading_service import (
    AutomatedTradingService,
    RESERVED_NON_EQUITY_SYMBOLS,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def allow_trading_protections():
    with patch("src.services.trading_protections_service.TradingProtectionsService") as MockProt:
        MockProt.return_value.check.return_value = None
        yield MockProt


class TestPseudoTickerFiltering:
    """Test that non-equity pseudo symbols (CASH, USD, etc.) are strictly filtered."""

    @pytest.mark.parametrize("pseudo_sym", ["CASH", "cash", "USD", "usd", "USDT", "CURRENCY", "RESERVE", "HOLDING", "PORTFOLIO", "INDEX", "MONEY"])
    @pytest.mark.anyio
    async def test_pseudo_ticker_skipped_in_evaluate_and_execute_trade(self, pseudo_sym):
        repo = MagicMock()
        repo.get.return_value = "true"
        svc = AutomatedTradingService(settings_repo=repo)
        res = await svc.evaluate_and_execute_trade(
            user_id="u1",
            ticker=pseudo_sym,
            action="BUY",
            quantity=100.0,
            confidence_score=9.0,
            rationale="Hold cash reserve"
        )
        assert res["status"] == "skipped"
        assert "Non-equity pseudo symbol" in res["reason"]

    def test_reserved_symbols_set_completeness(self):
        assert "CASH" in RESERVED_NON_EQUITY_SYMBOLS
        assert "USD" in RESERVED_NON_EQUITY_SYMBOLS
        assert "USDT" in RESERVED_NON_EQUITY_SYMBOLS


class TestAutonomousConfidenceOptimizer:
    """Test conviction self-optimization for marginal trade signals."""

    def test_stop_loss_exit_boost(self):
        score, boosts = AutonomousConfidenceOptimizer.optimize_confidence(
            base_confidence=5.0,
            action="SELL",
            threshold=6.0,
            rationale="Triggered stop loss due to high drawdown",
            strategy_name="stop_loss"
        )
        assert score == 7.0
        assert any("停損" in b for b in boosts)

    def test_rebalance_exit_boost(self):
        score, boosts = AutonomousConfidenceOptimizer.optimize_confidence(
            base_confidence=5.0,
            action="SELL",
            threshold=6.0,
            rationale="Rebalancing portfolio to converge watchlist to top 5-8",
            strategy_name="rebalance_diversification"
        )
        assert score == 6.2
        assert any("再平衡" in b for b in boosts)

    def test_excess_cash_buy_boost(self):
        score, boosts = AutonomousConfidenceOptimizer.optimize_confidence(
            base_confidence=6.8,
            action="BUY",
            threshold=7.5,
            rationale="High cash balance, deploy excess cash",
            cash_ratio=0.35
        )
        assert score == 7.8
        assert any("流動性優化" in b for b in boosts)

    def test_multi_agent_consensus_boost(self):
        breakdown = [
            {"agent": "Fundamental", "score": 8.0},
            {"agent": "Risk", "score": 8.5},
            {"agent": "Momentum", "score": 6.0},
        ]
        score, boosts = AutonomousConfidenceOptimizer.optimize_confidence(
            base_confidence=6.8,
            action="BUY",
            threshold=7.5,
            rationale="Quality conviction",
            confidence_breakdown=breakdown
        )
        assert score == 7.6
        assert any("多智能體共識協同" in b for b in boosts)


class TestAutonomousReportingModeFlow:
    """Test the end-to-end autonomous reporting mode execution and skip behavior."""

    @pytest.mark.anyio
    async def test_autonomous_mode_auto_executes_when_optimized(self):
        repo = MagicMock()
        def get_setting(uid, key):
            if key == "ai_trading_enabled": return "true"
            if key == "auto_trade_threshold": return "7.5"
            if key == "auto_trade_threshold_sell": return "6.0"
            if key == "auto_trade_min_threshold": return "3.0"
            if key == "autonomous_reporting_mode": return "true"
            if key == "tradable_capital_usd": return "500.0"
            return None
        repo.get.side_effect = get_setting

        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "eToro"
        mock_broker.execute_order = AsyncMock(return_value={"status": "success", "order_id": "ord_999"})
        mock_account = MagicMock(total_equity=1200.0, available_cash=200.0)
        mock_broker.get_account = AsyncMock(return_value=mock_account)
        mock_pos = MagicMock(symbol="NKE", quantity=5.0, market_value=400.0)
        mock_broker.get_positions = AsyncMock(return_value=[mock_pos])

        svc = AutomatedTradingService(settings_repo=repo)
        with patch("src.services.automated_trading_service.BrokerFactory.get_broker", return_value=mock_broker), \
             patch.object(svc, "_notify_via_api", new_callable=AsyncMock) as mock_notify:
            # Base confidence 5.2 < 6.0, but rebalance boost (+1.2) raises it to 6.4 >= 6.0!
            res = await svc.evaluate_and_execute_trade(
                user_id="u1",
                ticker="NKE",
                action="SELL",
                quantity=2.0,
                confidence_score=5.2,
                rationale="Rebalancing portfolio to tighten top holdings",
                strategy_name="rebalance_diversification"
            )

        assert res["status"] == "success"
        mock_broker.execute_order.assert_called_once()
        mock_notify.assert_called_once()
        call_content = mock_notify.call_args[1]["content"]
        assert "一、 行動 (The Action Taken)" in call_content
        assert "二、 行動後的狀況影響 (Post-Action Impact & Condition)" in call_content
        assert "三、 交易策略改變的行動 (Actions from Strategy Shift & Adaptive Stance)" in call_content

    @pytest.mark.anyio
    async def test_autonomous_mode_skips_low_confidence_without_approval_blocking(self):
        repo = MagicMock()
        def get_setting(uid, key):
            if key == "ai_trading_enabled": return "true"
            if key == "auto_trade_threshold": return "7.5"
            if key == "auto_trade_min_threshold": return "3.0"
            if key == "autonomous_reporting_mode": return "true"
            return None
        repo.get.side_effect = get_setting

        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "eToro"
        mock_account = MagicMock(total_equity=1000.0, available_cash=500.0)
        mock_broker.get_account = AsyncMock(return_value=mock_account)

        mock_interaction = AsyncMock()
        svc = AutomatedTradingService(settings_repo=repo, interaction_service=mock_interaction)
        with patch("src.services.automated_trading_service.BrokerFactory.get_broker", return_value=mock_broker):
            res = await svc.evaluate_and_execute_trade(
                user_id="u1",
                ticker="AAPL",
                action="BUY",
                quantity=20.0,
                confidence_score=4.0,  # Below 7.5, even if in [3.0, 7.5)
                rationale="Uncertain signal"
            )

        assert res["status"] == "skipped"
        assert "Autonomous evaluation" in res["reason"]
        # In autonomous reporting mode, user is NEVER bothered by request_approval
        mock_interaction.request_approval.assert_not_called()


class TestAutonomousReportingServiceStructure:
    """Test that the 3-pillar report strictly conforms to the requested structure."""

    @pytest.mark.anyio
    async def test_generate_report_three_pillars(self):
        mock_broker = MagicMock()
        mock_broker.get_name.return_value = "eToro"
        mock_account = MagicMock(total_equity=1280.0, available_cash=180.0)
        mock_broker.get_account = AsyncMock(return_value=mock_account)
        mock_pos = MagicMock(symbol="NKE", quantity=0.0, market_value=0.0)
        mock_broker.get_positions = AsyncMock(return_value=[mock_pos])

        service = AutonomousReportingService(broker=mock_broker)
        order = Order(
            symbol="NKE",
            action=OrderAction.SELL,
            quantity=2.0,
            order_type=OrderType.MARKET,
            reason="Prune weak position"
        )
        result = {"status": "success", "order_id": "etoro_ord_456"}

        report = await service.generate_report(
            user_id="u1",
            order=order,
            result=result,
            confidence_score=8.2,
            threshold=6.0,
            rationale="Prune weak momentum position and reallocate to core assets",
            approval_type="自主執行",
            strategy_name="rebalance_diversification",
            confidence_breakdown=[
                {"agent": "Fundamental", "score": 4.5, "key_factor": "Weak margin guidance"},
                {"agent": "Momentum", "score": 3.8, "key_factor": "Below 50MA"},
                {"agent": "Risk", "score": 8.5, "key_factor": "Recommend exit to protect capital"},
            ]
        )

        assert "🤖 [自主行動通報] SELL NKE" in report["title"]
        content = report["content"]

        # Pillar 1: Action
        assert "### 一、 行動 (The Action Taken)" in content
        assert "SELL NKE" in content
        assert "2.00 股" in content
        assert "分數 8.2/10 ｜ 自動門檻 6.0" in content
        assert "**Fundamental**: 4.5/10" in content
        assert "**Risk**: 8.5/10" in content

        # Pillar 2: Post-action impact
        assert "### 二、 行動後的狀況影響 (Post-Action Impact & Condition)" in content
        assert "$180.00 USD" in content
        assert "14.1%" in content
        assert "核心活躍持倉退出並移入觀察池" in content

        # Pillar 3: Strategy shift
        assert "### 三、 交易策略改變的行動 (Actions from Strategy Shift & Adaptive Stance)" in content
        assert "標的池收斂與定期再平衡" in content
        assert "動態防護停損線" in content
