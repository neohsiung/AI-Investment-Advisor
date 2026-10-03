"""
Unit Tests for M2: Dynamic Correlation Clustering & Portfolio Beta Shielder
=============================================================================
Tests:
  1. calculate_ticker_returns: returns accurate daily percentage changes.
  2. calculate_ticker_beta: calculates accurate 60-day market beta against SPY.
  3. build_correlation_clusters: groups highly correlated tickers into connected clusters.
  4. apply_cluster_caps: enforces strict cluster cap ceiling (e.g. 30%) on multi-ticker clusters.
  5. optimize_allocations with correlation cluster capping: limits concentrated correlated risk.
  6. optimize_allocations with portfolio market beta dampening: protects capital when portfolio beta exceeds target beta.
  7. MarketRegimeService RegimePolicy target_beta integration across Bull, Neutral, and Bear Crisis.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from src.services.ticker_universe_service import TickerUniverseService
from src.services.market_regime_service import MarketRegimeService, MarketRegime


class TestReturnsAndBetaCalculation:
    """Test price return and beta extraction math."""

    @pytest.fixture
    def service(self):
        s = TickerUniverseService(user_id="test_m2_user")
        s._market_data = MagicMock()
        return s

    def test_calculate_ticker_returns_success(self, service):
        # 6 prices -> 5 percentage returns: 100 -> 105 (+5%), 105 -> 102 (-2.86%), etc.
        closes = [100.0, 105.0, 102.0, 108.0, 110.0, 115.0]
        service.market_data_service.get_ohlcv.return_value = {"close": closes}

        rets = service.calculate_ticker_returns("AAPL", days=6)
        assert len(rets) == 5
        assert round(rets[0], 4) == 0.05
        assert round(rets[1], 4) == round((102.0 - 105.0) / 105.0, 4)

    def test_calculate_ticker_returns_empty_fallback(self, service):
        service.market_data_service.get_ohlcv.return_value = {"close": []}
        rets = service.calculate_ticker_returns("UNKNOWN")
        assert rets == []

    def test_calculate_ticker_beta_high_beta_stock(self, service):
        # Construct synthetic SPY returns and 2.0x leveraged ticker returns
        np.random.seed(42)
        spy_rets = list(np.random.normal(0.001, 0.01, 30))
        # Ticker has 2.0x sensitivity to SPY + small noise
        ticker_rets = [2.0 * r + float(np.random.normal(0, 0.002)) for r in spy_rets]

        service.calculate_ticker_returns = MagicMock(return_value=ticker_rets)
        beta = service.calculate_ticker_beta("GROWTH", spy_returns=spy_rets, days=30)
        # Beta should be close to 2.0 (e.g. 1.7 ~ 2.3)
        assert 1.7 <= beta <= 2.3

    def test_calculate_ticker_beta_low_beta_stock(self, service):
        np.random.seed(42)
        spy_rets = list(np.random.normal(0.001, 0.01, 30))
        # Defensive utility stock: 0.5x SPY
        ticker_rets = [0.5 * r + float(np.random.normal(0, 0.001)) for r in spy_rets]

        # Mock calculate_ticker_returns to return ticker_rets
        service.calculate_ticker_returns = MagicMock(return_value=ticker_rets)
        beta = service.calculate_ticker_beta("DEFENSE", spy_returns=spy_rets, days=30)
        assert 0.4 <= beta <= 0.6

    def test_calculate_ticker_beta_fallback_default(self, service):
        service.calculate_ticker_returns = MagicMock(return_value=[])
        beta = service.calculate_ticker_beta("NO_DATA", spy_returns=None, default_beta=1.0)
        assert beta == 1.0


class TestCorrelationClustering:
    """Test Pearson correlation matrix construction and connected component clustering."""

    @pytest.fixture
    def service(self):
        return TickerUniverseService(user_id="test_m2_user")

    def test_build_correlation_clusters_high_and_low_corr(self, service):
        # 3 tickers:
        # NVDA and MSFT have 0.95 correlation
        # JNJ is uncorrelated (rho ~ 0.0)
        np.random.seed(123)
        common_factor = np.random.normal(0, 0.02, 40)
        noise1 = np.random.normal(0, 0.002, 40)
        noise2 = np.random.normal(0, 0.002, 40)
        noise3 = np.random.normal(0, 0.02, 40)

        r_nvda = list(common_factor + noise1)
        r_msft = list(common_factor + noise2)
        r_jnj = list(noise3)

        returns_map = {
            "NVDA": r_nvda,
            "MSFT": r_msft,
            "JNJ": r_jnj,
        }

        corr_matrix, clusters = service.build_correlation_clusters(
            ["NVDA", "MSFT", "JNJ"],
            ticker_returns_map=returns_map,
            threshold=0.70,
        )

        assert corr_matrix["NVDA"]["MSFT"] >= 0.85
        assert corr_matrix["NVDA"]["JNJ"] < 0.40

        # Clusters: NVDA and MSFT should be grouped together into a 2-ticker cluster
        # JNJ should be in its own single-ticker cluster
        multi_clusters = [c for c in clusters if len(c) > 1]
        assert len(multi_clusters) == 1
        assert sorted(multi_clusters[0]) == ["MSFT", "NVDA"]

    def test_apply_cluster_caps_scales_down_concentrated_cluster(self, service):
        clusters = [["AAPL", "MSFT", "NVDA"], ["JNJ"]]
        weights = {
            "AAPL": 0.20,
            "MSFT": 0.20,
            "NVDA": 0.20,
            "JNJ": 0.20,
        }
        # Multi-ticker cluster total = 0.60, cap = 0.30 -> ratio = 0.50
        capped = service.apply_cluster_caps(weights, clusters, cluster_cap=0.30)

        assert round(capped["AAPL"], 4) == 0.10
        assert round(capped["MSFT"], 4) == 0.10
        assert round(capped["NVDA"], 4) == 0.10
        # Single-ticker cluster JNJ remains untouched
        assert round(capped["JNJ"], 4) == 0.20


class TestOptimizeAllocationsM2:
    """Test full portfolio allocation optimization with correlation clusters and beta dampening."""

    @pytest.fixture
    def service(self):
        s = TickerUniverseService(user_id="test_m2_user")
        s.repo = MagicMock()
        s._settings = MagicMock()
        # Default mock settings
        s._settings.get_setting.side_effect = lambda key, default=None: {
            "alloc_min_position": 0.03,
            "alloc_max_position": 0.20,
            "alloc_sector_cap": 0.60,
            "alloc_cluster_cap": 0.30,
            "alloc_correlation_cluster_threshold": 0.70,
            "alloc_target_beta": 0.90,
            "alloc_target_sum": 0.95,
            "alloc_max_holdings": 10,
            "alloc_target_volatility": 0.25,
        }.get(key, default)
        return s

    def test_cluster_cap_enforcement_in_optimize_allocations(self, service):
        # 3 tickers: TECH_A and TECH_B are in different sectors on paper,
        # but have high correlation 0.90 -> grouped in one cluster.
        # DEFENSE is uncorrelated.
        service.repo.get_all.return_value = [
            {"ticker": "TECH_A", "sector": "Technology", "volatility": 0.20, "beta": 1.0},
            {"ticker": "TECH_B", "sector": "Communication", "volatility": 0.20, "beta": 1.0},
            {"ticker": "DEFENSE", "sector": "Healthcare", "volatility": 0.20, "beta": 0.8},
        ]
        service.repo.get_research.return_value = [
            {"confidence_score": 0.85, "expected_return": 0.10}
        ]

        np.random.seed(99)
        common = np.random.normal(0, 0.02, 50)
        service.calculate_ticker_returns = MagicMock(side_effect=lambda t, days=60: {
            "SPY": list(np.random.normal(0, 0.01, 50)),
            "TECH_A": list(common + np.random.normal(0, 0.001, 50)),
            "TECH_B": list(common + np.random.normal(0, 0.001, 50)),
            "DEFENSE": list(np.random.normal(0, 0.02, 50)),
        }.get(t, []))

        res = service.optimize_allocations()
        assert res["success"] is True

        targets_by_ticker = {t["ticker"]: t for t in res["targets"]}
        # Cluster cap is 0.30. TECH_A and TECH_B together should not dominate
        cluster_sum = targets_by_ticker["TECH_A"]["target_weight"] + targets_by_ticker["TECH_B"]["target_weight"]
        # In preliminary weights, TECH_A + TECH_B was ~ 0.66, scaled to cluster cap 0.30
        assert cluster_sum <= 0.40  # Well below unconstrained ~ 0.65
        assert targets_by_ticker["TECH_A"]["cluster_id"] is not None
        assert targets_by_ticker["TECH_A"]["cluster_id"] == targets_by_ticker["TECH_B"]["cluster_id"]
        assert targets_by_ticker["DEFENSE"]["cluster_id"] is None

    def test_target_beta_scaling_dampens_high_beta_portfolio(self, service):
        # 2 aggressive high-beta tickers (beta = 1.80)
        # target_beta = 0.90 -> beta_scale = 0.90 / 1.80 = 0.50
        service.repo.get_all.return_value = [
            {"ticker": "HIGH_BETA_1", "sector": "Tech", "volatility": 0.20, "beta": 1.80},
            {"ticker": "HIGH_BETA_2", "sector": "Consumer", "volatility": 0.20, "beta": 1.80},
        ]
        service.repo.get_research.return_value = [
            {"confidence_score": 0.80, "expected_return": 0.12}
        ]
        service.calculate_ticker_returns = MagicMock(return_value=[])

        res = service.optimize_allocations()
        assert res["success"] is True
        assert res["portfolio_beta"] == 1.80
        assert res["target_beta"] == 0.90
        assert res["beta_scale_factor"] == 0.50
        # effective target sum should be roughly 0.95 * 0.50 = 0.475
        assert res["effective_target_sum"] == pytest.approx(0.475, abs=0.01)

        total_weight = sum(t["target_weight"] for t in res["targets"])
        assert total_weight <= 0.48


class TestMarketRegimeTargetBeta:
    """Test RegimePolicy target_beta specifications."""

    def test_regime_policy_target_beta(self):
        service = MarketRegimeService()
        bull_policy = service.classify_regime(spy_price=500.0, spy_sma200=450.0, vix=15.0)
        assert bull_policy.regime == MarketRegime.BULL_MOMENTUM
        assert bull_policy.target_beta == 1.10

        neutral_policy = service.classify_regime(spy_price=450.0, spy_sma200=450.0, vix=22.0)
        assert neutral_policy.regime == MarketRegime.NEUTRAL_RANGE
        assert neutral_policy.target_beta == 0.85

        bear_policy = service.classify_regime(spy_price=420.0, spy_sma200=450.0, vix=30.0)
        assert bear_policy.regime == MarketRegime.BEAR_CRISIS
        assert bear_policy.target_beta == 0.40
