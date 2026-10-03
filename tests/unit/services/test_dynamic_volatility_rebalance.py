"""
Unit Tests for M1: Dynamic Volatility Targeting & Regime Cash Buffer
====================================================================
Tests:
  1. MarketRegimeService boundary classifications (Bull, Neutral, Bear Crisis).
  2. ConfidenceRebalanceService dynamic cash defense under Bull (5%), Neutral (20%), Bear (50%).
  3. Strict buy halt during BEAR_CRISIS (allow_new_buys=False) to safeguard capital.
  4. Inverse-volatility risk parity sizing (Equal Risk Contribution) in TickerUniverseService.
  5. Target portfolio volatility scaling (linear scaling down when portfolio vol > target vol).
  6. Maximum single position hard cap (20%).
  7. Robust graceful fallback of get_current_regime when market data is unavailable.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.market_regime_service import (
    MarketRegimeService,
    MarketRegime,
    RegimePolicy,
)
from src.services.confidence_rebalance_service import ConfidenceRebalanceService
from src.services.ticker_universe_service import TickerUniverseService


class TestMarketRegimeService:
    """Test macro regime classification and policy generation."""

    def test_classify_bull_momentum(self):
        service = MarketRegimeService()
        # SPY well above SMA200 (ratio 500/450 = 1.11 >= 1.02), calm VIX (14 < 20)
        policy = service.classify_regime(spy_price=500.0, spy_sma200=450.0, vix=14.0)
        assert policy.regime == MarketRegime.BULL_MOMENTUM
        assert policy.cash_reserve_pct == 5.0
        assert policy.allow_new_buys is True
        assert policy.max_leverage == 1.2
        assert policy.buy_confidence_threshold == 6.5

    def test_classify_bear_crisis_price_break(self):
        service = MarketRegimeService()
        # SPY below SMA200 (ratio 430/450 = 0.955 < 0.98), normal VIX
        policy = service.classify_regime(spy_price=430.0, spy_sma200=450.0, vix=18.0)
        assert policy.regime == MarketRegime.BEAR_CRISIS
        assert policy.cash_reserve_pct == 50.0
        assert policy.allow_new_buys is False
        assert policy.max_leverage == 0.0

    def test_classify_bear_crisis_vix_spike(self):
        service = MarketRegimeService()
        # SPY slightly above SMA200, but VIX spiking (> 28.0)
        policy = service.classify_regime(spy_price=460.0, spy_sma200=450.0, vix=35.0)
        assert policy.regime == MarketRegime.BEAR_CRISIS
        assert policy.cash_reserve_pct == 50.0
        assert policy.allow_new_buys is False

    def test_classify_neutral_range(self):
        service = MarketRegimeService()
        # SPY near SMA200 (ratio 452/450 = 1.004) and VIX = 22
        policy = service.classify_regime(spy_price=452.0, spy_sma200=450.0, vix=22.0)
        assert policy.regime == MarketRegime.NEUTRAL_RANGE
        assert policy.cash_reserve_pct == 20.0
        assert policy.allow_new_buys is True

    @pytest.mark.asyncio
    async def test_get_current_regime_fallback_without_market_data(self):
        service = MarketRegimeService(market_data_service=None)
        policy = await service.get_current_regime()
        assert policy.regime == MarketRegime.NEUTRAL_RANGE
        assert policy.cash_reserve_pct == 20.0
        assert policy.allow_new_buys is True


class TestConfidenceRebalanceRegimeBuffer:
    """Test dynamic regime cash buffer enforcement in ConfidenceRebalanceService."""

    @pytest.fixture
    def rebalance_service(self):
        return ConfidenceRebalanceService(user_id="test_user")

    @pytest.mark.asyncio
    async def test_bull_regime_deploys_capital_with_5pct_buffer(self, rebalance_service):
        bull_policy = RegimePolicy(
            regime=MarketRegime.BULL_MOMENTUM,
            cash_reserve_pct=5.0,
            buy_confidence_threshold=6.5,
            stop_atr_multiplier=2.5,
            max_leverage=1.2,
            allow_new_buys=True,
            rationale="Bull test",
        )
        rebalance_service.regime_service = MagicMock()
        rebalance_service.regime_service.get_current_regime = AsyncMock(return_value=bull_policy)

        # 2 active targets: AAPL (50%), MSFT (45%)
        rebalance_service.ticker_service = MagicMock()
        rebalance_service.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [
                {"ticker": "AAPL", "target_weight": 0.50, "confidence_score": 0.85},
                {"ticker": "MSFT", "target_weight": 0.45, "confidence_score": 0.80},
            ],
        }

        # Current portfolio: $1000 total, $100 cash (10%), AAPL $200 (20%), MSFT $100 (10%), OVER $600 (60%)
        mock_weights = {
            "weights": {"AAPL": 20.0, "MSFT": 10.0, "OVER": 60.0},
            "cash_weight": 10.0,
            "total_value": 1000.0,
        }

        with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rebalance_service.get_rebalance_plan()

        assert plan["success"] is True
        assert plan["regime"] == "BULL_MOMENTUM"
        assert plan["summary"]["target_cash_pct"] == 5.0
        assert plan["summary"]["allow_new_buys"] is True
        assert len(plan["trades"]["buys"]) == 2  # Both AAPL and MSFT bought

    @pytest.mark.asyncio
    async def test_bear_crisis_halts_all_buys_and_locks_cash(self, rebalance_service):
        bear_policy = RegimePolicy(
            regime=MarketRegime.BEAR_CRISIS,
            cash_reserve_pct=50.0,
            buy_confidence_threshold=9.0,
            stop_atr_multiplier=1.5,
            max_leverage=0.0,
            allow_new_buys=False,
            rationale="Bear Crisis defense",
        )
        rebalance_service.regime_service = MagicMock()
        rebalance_service.regime_service.get_current_regime = AsyncMock(return_value=bear_policy)

        # Targets exist
        rebalance_service.ticker_service = MagicMock()
        rebalance_service.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [
                {"ticker": "AAPL", "target_weight": 0.50, "confidence_score": 0.85},
            ],
        }

        # Current portfolio: OVER is liquidated to free cash
        mock_weights = {
            "weights": {"AAPL": 10.0, "DEAD_STOCK": 50.0},
            "cash_weight": 40.0,
            "total_value": 1000.0,
        }

        with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rebalance_service.get_rebalance_plan()

        assert plan["success"] is True
        assert plan["regime"] == "BEAR_CRISIS"
        assert plan["summary"]["allow_new_buys"] is False
        assert plan["summary"]["target_cash_pct"] == 50.0

        # DEAD_STOCK must be sold
        sell_tickers = [s["ticker"] for s in plan["trades"]["sells"]]
        assert "DEAD_STOCK" in sell_tickers

        # BUYS MUST BE COMPLETELY EMPTY (Catching falling knives prohibited!)
        assert len(plan["trades"]["buys"]) == 0
        assert plan["summary"]["buys"] == 0


class TestInverseVolatilityRiskParity:
    """Test inverse-volatility weighting and target portfolio volatility scaling."""

    @pytest.fixture
    def ticker_service(self):
        svc = TickerUniverseService(user_id="test_user")
        svc.repo = MagicMock()
        return svc

    def test_inverse_volatility_gives_more_weight_to_lower_volatility_stock(self, ticker_service):
        """
        Two stocks with identical confidence (0.8) and expected return (0.10):
        - LOW_VOL: sigma = 0.15
        - HIGH_VOL: sigma = 0.45
        LOW_VOL should receive 3x the raw score of HIGH_VOL, leading to higher allocation.
        """
        ticker_service.repo.get_all.return_value = [
            {"ticker": "LOW_VOL", "sector": "Tech", "volatility": 0.15},
            {"ticker": "HIGH_VOL", "sector": "Tech", "volatility": 0.45},
        ]
        ticker_service.repo.get_research.return_value = [
            {"confidence_score": 0.80, "expected_return": 0.10}
        ]
        ticker_service.repo.upsert_target.return_value = True

        ticker_service._settings = MagicMock()
        ticker_service._settings.get_setting.side_effect = lambda k, default=None: {
            "alloc_min_position": 0.03,
            "alloc_max_position": 0.60,
            "alloc_sector_cap": 1.0,
            "alloc_target_sum": 0.95,
            "alloc_max_holdings": 10,
            "alloc_target_volatility": 0.40,
        }.get(k, default)

        res = ticker_service.optimize_allocations()
        assert res["success"] is True
        target_map = {t["ticker"]: t["target_weight"] for t in res["targets"]}

        # LOW_VOL must have higher target weight than HIGH_VOL due to inverse-volatility weighting
        assert target_map["LOW_VOL"] > target_map["HIGH_VOL"]
        assert target_map["LOW_VOL"] / target_map["HIGH_VOL"] >= 2.0

    def test_portfolio_target_volatility_scaling(self, ticker_service):
        """
        When portfolio projected volatility exceeds target volatility (14%),
        effective target sum is scaled down proportionally and cash is retained.
        """
        # Both high volatility stocks (0.40)
        ticker_service.repo.get_all.return_value = [
            {"ticker": "TECH1", "sector": "Tech", "volatility": 0.40},
            {"ticker": "TECH2", "sector": "Tech", "volatility": 0.40},
        ]
        ticker_service.repo.get_research.return_value = [
            {"confidence_score": 0.85, "expected_return": 0.15}
        ]
        ticker_service.repo.upsert_target.return_value = True

        # Mock settings: target volatility = 14% (0.14)
        ticker_service._settings = MagicMock()
        ticker_service._settings.get_setting.side_effect = lambda k, default=None: {
            "alloc_min_position": 0.03,
            "alloc_max_position": 0.50,
            "alloc_sector_cap": 0.90,
            "alloc_target_sum": 0.95,
            "alloc_max_holdings": 10,
            "alloc_target_volatility": 0.14,
        }.get(k, default)

        res = ticker_service.optimize_allocations()
        assert res["success"] is True
        assert res["portfolio_volatility"] > 0.20  # Well above 14%
        assert res["target_volatility"] == 0.14
        assert res["volatility_scale_factor"] < 1.0  # Scaled down!
        assert res["effective_target_sum"] < 0.95    # Equity trimmed!

        # Total invested weight must equal effective_target_sum
        total_invested = sum(t["target_weight"] for t in res["targets"])
        assert abs(total_invested - res["effective_target_sum"]) < 0.01

    def test_single_position_hard_cap_at_20pct(self, ticker_service):
        """No single position should exceed alloc_max_position (default 0.20)."""
        ticker_service.repo.get_all.return_value = [
            {"ticker": "MEGA", "sector": "Tech", "volatility": 0.12},
            {"ticker": "SMALL", "sector": "Utilities", "volatility": 0.20},
        ]
        # MEGA has massive confidence
        def mock_research(uid, ticker, limit=5):
            if ticker == "MEGA":
                return [{"confidence_score": 0.99, "expected_return": 0.30}]
            return [{"confidence_score": 0.40, "expected_return": 0.02}]

        ticker_service.repo.get_research.side_effect = mock_research
        ticker_service.repo.upsert_target.return_value = True

        ticker_service._settings = MagicMock()
        ticker_service._settings.get_setting.side_effect = lambda k, default=None: {
            "alloc_min_position": 0.03,
            "alloc_max_position": 0.20,  # 20% hard cap
            "alloc_sector_cap": 0.50,
            "alloc_target_sum": 0.95,
            "alloc_max_holdings": 10,
            "alloc_target_volatility": 0.40,
        }.get(k, default)

        res = ticker_service.optimize_allocations()
        assert res["success"] is True
        for t in res["targets"]:
            assert t["target_weight"] <= 0.21, f"{t['ticker']} weight {t['target_weight']} exceeded 20% cap!"
