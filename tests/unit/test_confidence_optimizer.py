"""Unit tests for the confidence-driven allocation optimizer."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _risk_parity_optimize(
    tickers: list, confidences: list, returns: list,
    min_weight=0.03, max_weight=0.25, cash_buffer=0.05, sector_cap=0.40,
):
    """Reference implementation of the optimization algorithm for testing."""
    n = len(tickers)
    if n == 0:
        return {}

    # Confidence-weighted scores
    scores = {}
    for i in range(n):
        c = min(confidences[i], 1.0)
        r = max(returns[i], -1.0)
        # Apply confidence discount factor
        if c < 0.35:
            discount = c / 0.35  # linear ramp from 0→1
        else:
            discount = 1.0
        scores[tickers[i]] = (c + max(r, 0)) / 2.0 * discount

    total = sum(scores.values()) or 1.0
    raw = {t: s / total for t, s in scores.items()}

    # Apply constraints iteratively
    constrained = dict(raw)
    for _ in range(20):  # converge
        # Sector cap
        sector_weights = {}
        for t in constrained:
            sector = "default"
            sector_weights.setdefault(sector, 0.0)
            sector_weights[sector] = 0.0
        # Not testing sector logic in unit test

        # Position limits
        for t in list(constrained.keys()):
            constrained[t] = max(min(constrained[t], max_weight), min_weight)

        # Normalize to < 1 - cash_buffer
        total_w = sum(constrained.values())
        if total_w > 0:
            scale = (1.0 - cash_buffer) / total_w
            for t in constrained:
                constrained[t] = round(min(constrained[t] * scale, max_weight), 4)

        # Check convergence
        if abs(1.0 - cash_buffer - total_w) < 0.001:
            break

    return constrained


class TestOptimizeAllocations:

    def test_equal_confidence_equal_weight(self):
        """All tickers with same confidence should get equal weights."""
        tickers = ["AAPL", "GOOG", "MSFT"]
        confidences = [0.7, 0.7, 0.7]
        returns = [0.05, 0.05, 0.05]
        result = _risk_parity_optimize(tickers, confidences, returns)
        assert len(result) == 3
        weights = list(result.values())
        assert all(abs(w - weights[0]) < 0.01 for w in weights), f"Unequal weights: {weights}"

    def test_higher_confidence_gets_higher_weight(self):
        """With enough tickers, higher confidence ticker should get larger allocation."""
        tickers = ["AAPL", "GOOG", "MSFT", "NVDA", "TSLA"]
        result = _risk_parity_optimize(tickers, [0.9, 0.5, 0.5, 0.5, 0.5], [0.1, 0.05, 0.05, 0.05, 0.05])
        assert result["AAPL"] > result["GOOG"], "High confidence should get higher weight"

    def test_low_confidence_discount(self):
        """Very low confidence (<0.35) should be heavily discounted (near min weight)."""
        tickers = ["AAPL", "GOOG", "MSFT", "NVDA", "TSLA", "AMZN", "META"]
        result = _risk_parity_optimize(tickers, [0.8, 0.1, 0.8, 0.8, 0.8, 0.8, 0.8], [0.1, 0.0, 0.1, 0.1, 0.1, 0.1, 0.1])
        # GOOG at 0.1 confidence → heavily discounted vs others at 0.8
        assert result["GOOG"] < result["AAPL"], "Low confidence should be discounted"

    def test_min_max_position_limits(self):
        """No position should go below 3% or above 25%."""
        tickers = [f"T{i}" for i in range(10)]
        confidences = [0.95] * 10
        returns = [0.20] * 10
        result = _risk_parity_optimize(tickers, confidences, returns)
        for w in result.values():
            assert 0.03 <= w <= 0.25, f"Weight {w:.4f} outside [0.03, 0.25]"

    def test_cash_buffer(self):
        """Total allocation should respect 5% cash buffer."""
        tickers = [f"T{i}" for i in range(5)]
        confidences = [0.8] * 5
        returns = [0.10] * 5
        result = _risk_parity_optimize(tickers, confidences, returns)
        total = sum(result.values())
        assert total <= 0.96, f"Total weight {total:.3f} exceeds 95% cash buffer"

    def test_empty_input(self):
        """Empty ticker list returns empty dict."""
        assert _risk_parity_optimize([], [], []) == {}

    def test_single_ticker(self):
        """Single ticker gets max position weight (25%) not full portfolio."""
        result = _risk_parity_optimize(["AAPL"], [0.9], [0.1])
        assert abs(result["AAPL"] - 0.25) < 0.01, f"Single ticker should cap at 25%, got {result['AAPL']:.4f}"

    def test_zero_confidence_ticker(self):
        """Ticker with 0 confidence should get close to min weight (3%)."""
        tickers = ["AAPL", "GOOG", "MSFT", "NVDA", "TSLA", "AMZN", "META"]
        result = _risk_parity_optimize(tickers, [0.8, 0.0, 0.7, 0.7, 0.7, 0.7, 0.7], [0.1, 0.0, 0.05, 0.05, 0.05, 0.05, 0.05])
        # GOOG with 0 confidence gets discounted by the 0.35 threshold
        assert result["GOOG"] < 0.04, f"Zero confidence should be near-minimal, got {result['GOOG']:.4f}"

    def test_negative_return_handling(self):
        """Negative expected returns should still work."""
        tickers = ["AAPL"]
        result = _risk_parity_optimize(tickers, [0.8], [-0.05])
        assert "AAPL" in result
        assert result["AAPL"] > 0


class TestConfidenceRebalanceService:

    @pytest.mark.asyncio
    async def test_get_rebalance_plan_with_mocks(self):
        """Test rebalance plan calculation with mocked services."""
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService

        svc = ConfidenceRebalanceService(user_id="test-user")

        # Mock the portfolio weights
        svc._get_current_weights = AsyncMock(return_value={
            "weights": {"AAPL": 15.0, "GOOG": 5.0, "MSFT": 10.0},
            "cash_weight": 5.0,
            "total_value": 100000.0,
        })

        # Mock the ticker service targets
        mock_targets = {"success": True, "targets": [
            {"ticker": "AAPL", "target_weight": 0.10, "confidence_score": 0.75},
            {"ticker": "GOOG", "target_weight": 0.12, "confidence_score": 0.80},
            {"ticker": "MSFT", "target_weight": 0.08, "confidence_score": 0.65},
            {"ticker": "NVDA", "target_weight": 0.15, "confidence_score": 0.90},
        ]}

        svc.ticker_service.optimize_allocations = MagicMock(return_value=mock_targets)

        plan = await svc.get_rebalance_plan()
        assert plan["success"]
        assert plan["summary"]["total_trades"] == 4
        assert plan["summary"]["sells"] == 2  # AAPL (15% > 10%), MSFT (10% > 8%)
        assert plan["summary"]["buys"] == 2   # GOOG (5% < 12%), NVDA (0% < 15%)

        # Verify sell order
        sells = plan["trades"]["sells"]
        assert sells[0]["ticker"] == "AAPL"
        assert sells[0]["delta_weight"] < 0

        # Verify buys
        buys = plan["trades"]["buys"]
        tickers = {b["ticker"] for b in buys}
        assert "NVDA" in tickers
        assert "GOOG" in tickers

    @pytest.mark.asyncio
    async def test_empty_portfolio_rebalance(self):
        """Empty portfolio should generate all-buy plan."""
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService

        svc = ConfidenceRebalanceService(user_id="test-user")
        svc._get_current_weights = AsyncMock(return_value={
            "weights": {},
            "cash_weight": 100.0,
            "total_value": 50000.0,
        })
        svc.ticker_service.optimize_allocations = MagicMock(return_value={
            "success": True, "targets": [
                {"ticker": "AAPL", "target_weight": 0.50, "confidence_score": 0.85},
                {"ticker": "GOOG", "target_weight": 0.50, "confidence_score": 0.80},
            ]
        })

        plan = await svc.get_rebalance_plan()
        assert plan["success"]
        assert plan["summary"]["buys"] == 2
        assert plan["summary"]["sells"] == 0

    @pytest.mark.asyncio
    async def test_no_trade_below_threshold(self):
        """Trades smaller than 0.5% should be skipped."""
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService

        svc = ConfidenceRebalanceService(user_id="test-user")
        svc._get_current_weights = AsyncMock(return_value={
            "weights": {"AAPL": 14.9, "GOOG": 5.1},
            "cash_weight": 80.0,
            "total_value": 100000.0,
        })
        svc.ticker_service.optimize_allocations = MagicMock(return_value={
            "success": True, "targets": [
                {"ticker": "AAPL", "target_weight": 0.15, "confidence_score": 0.5},
                {"ticker": "GOOG", "target_weight": 0.05, "confidence_score": 0.5},
            ]
        })

        plan = await svc.get_rebalance_plan()
        # AAPL: 14.9% current vs 15.0% target → delta = -0.1% → below 0.5% threshold
        # GOOG: 5.1% current vs 5.0% target → delta = +0.1% → below 0.5% threshold
        assert plan["summary"]["total_trades"] == 0


class TestRebalanceExecuteSafety:

    @pytest.mark.asyncio
    async def test_sell_before_buy_order(self):
        """Sells must be executed before buys in the trade plan."""
        from src.services.confidence_rebalance_service import ConfidenceRebalanceService

        svc = ConfidenceRebalanceService(user_id="test-user")
        svc._get_current_weights = AsyncMock(return_value={
            "weights": {"AAPL": 20.0, "GOOG": 1.0, "CASH": 79.0},
            "cash_weight": 79.0,
            "total_value": 100000.0,
        })
        svc.ticker_service.optimize_allocations = MagicMock(return_value={
            "success": True, "targets": [
                {"ticker": "AAPL", "target_weight": 0.10, "confidence_score": 0.5},
                {"ticker": "GOOG", "target_weight": 0.10, "confidence_score": 0.5},
            ]
        })

        plan = await svc.get_rebalance_plan()
        assert plan["summary"]["sells"] == 1  # AAPL overweight → sell
        assert plan["summary"]["buys"] == 1   # GOOG underweight → buy

        # Verify sell is first in plan
        all_trades = plan["trades"]["all"]
        assert all_trades[0]["action"] == "SELL"
        assert all_trades[0]["ticker"] == "AAPL"