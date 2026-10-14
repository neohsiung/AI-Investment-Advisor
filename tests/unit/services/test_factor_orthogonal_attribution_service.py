"""
Unit Tests for FactorOrthogonalAttributionService (Phase 66).
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.factor_orthogonal_attribution_service import (
    FactorOrthogonalAttributionService,
    FactorHealthStatus,
    FactorDecayMetric,
    FactorAttributionComponent,
    PortfolioAttributionReport,
)


class TestFactorOrthogonalAttributionService:
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.get_setting.side_effect = lambda k, default=None: {
            "enable_factor_orthogonal_attribution": True,
            "factor_attribution_lookback_days": 60,
            "factor_decay_haircut_threshold": 0.02,
            "min_factor_half_life_days": 5,
        }.get(k, default)
        return settings

    @pytest.fixture
    def service(self, mock_settings):
        return FactorOrthogonalAttributionService(
            user_id="user_test_p66",
            settings_service=mock_settings,
        )

    def test_initialization_and_settings(self, service, mock_settings):
        assert service.is_attribution_enabled is True
        assert service.lookback_days == 60
        assert service.decay_haircut_threshold == 0.02
        assert service.min_half_life_days == 5

    def test_compute_autocorrelation_lag1(self):
        # Short series fallback
        assert FactorOrthogonalAttributionService.compute_autocorrelation_lag1([1.0, 2.0]) == 0.90

        # Highly persistent series
        persistent = [1.0, 1.1, 1.2, 1.25, 1.3, 1.35, 1.4]
        rho = FactorOrthogonalAttributionService.compute_autocorrelation_lag1(persistent)
        assert rho > 0.70

        # Mean-reverting / alternating series
        alternating = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
        rho_neg = FactorOrthogonalAttributionService.compute_autocorrelation_lag1(alternating)
        assert rho_neg < 0.0

        # Flat constant series fallback
        flat = [5.0, 5.0, 5.0, 5.0, 5.0]
        assert FactorOrthogonalAttributionService.compute_autocorrelation_lag1(flat) == 0.90

    def test_compute_half_life(self):
        # High persistence rho=0.90
        hl_high = FactorOrthogonalAttributionService.compute_half_life(0.90)
        assert 5.0 < hl_high < 10.0

        # Low persistence rho=0.20
        hl_low = FactorOrthogonalAttributionService.compute_half_life(0.20)
        assert hl_low < 2.0

        # Negative rho (collapsed)
        hl_neg = FactorOrthogonalAttributionService.compute_half_life(-0.50)
        assert hl_neg == FactorOrthogonalAttributionService.compute_half_life(0.50)

    def test_evaluate_factor_health_and_tilting(self, service):
        # 1. Active Healthy: High IC, Long Half-Life
        m_healthy = service.evaluate_factor_health_and_tilting(
            factor_name="momentum",
            rolling_ic=0.06,
            ic_ir=1.2,
            autocorr_lag1=0.92,
            half_life_days=8.3,
        )
        assert m_healthy.health_status == FactorHealthStatus.ACTIVE_HEALTHY
        assert m_healthy.tilting_multiplier >= 1.0
        assert "🟢" in m_healthy.recommendation

        # 2. Decaying Crowded: Moderate IC, Short Half-Life (< 5d)
        m_crowded = service.evaluate_factor_health_and_tilting(
            factor_name="value",
            rolling_ic=0.025,
            ic_ir=0.4,
            autocorr_lag1=0.75,
            half_life_days=3.2,
        )
        assert m_crowded.health_status == FactorHealthStatus.DECAYING_CROWDED
        assert 0.50 <= m_crowded.tilting_multiplier <= 0.75
        assert "🟡" in m_crowded.recommendation

        # 3. Exhausted Inverted: Negative IC or Half-Life < 2d
        m_exhausted = service.evaluate_factor_health_and_tilting(
            factor_name="low_vol",
            rolling_ic=-0.01,
            ic_ir=-0.3,
            autocorr_lag1=0.30,
            half_life_days=1.2,
        )
        assert m_exhausted.health_status == FactorHealthStatus.EXHAUSTED_INVERTED
        assert m_exhausted.tilting_multiplier == 0.0
        assert "🔴" in m_exhausted.recommendation

    def test_calculate_factor_decay_metrics_prior_fallback(self, service):
        metrics = service.calculate_factor_decay_metrics()
        assert len(metrics) >= 8
        assert "market" in metrics
        assert "momentum" in metrics
        assert "value" in metrics
        assert "execution_spread" in metrics
        assert "currency_fx" in metrics

        for fname, m in metrics.items():
            assert isinstance(m, FactorDecayMetric)
            assert m.half_life_days > 0
            assert m.health_status in (
                FactorHealthStatus.ACTIVE_HEALTHY,
                FactorHealthStatus.DECAYING_CROWDED,
                FactorHealthStatus.EXHAUSTED_INVERTED,
            )

    def test_calculate_factor_decay_metrics_custom_series(self, service):
        factor_ts = {
            "momentum": [0.01, 0.02, 0.015, 0.018, 0.022, 0.025],
            "value": [0.005, 0.004, 0.006, 0.005, 0.007, 0.006],
        }
        fwd_returns = [0.008, 0.012, 0.011, 0.015, 0.018, 0.020]
        metrics = service.calculate_factor_decay_metrics(factor_ts, fwd_returns)
        assert "momentum" in metrics
        assert "value" in metrics
        assert len(metrics["momentum"].historical_ic_series) > 0

    def test_decompose_orthogonal_returns_prior_fallback(self, service):
        report = service.decompose_orthogonal_returns()
        assert isinstance(report, PortfolioAttributionReport)
        assert 0.0 <= report.r_squared <= 1.0
        assert len(report.components) >= 8

        # Verify key component types
        comp_names = [c.component_name for c in report.components]
        assert any("市場大盤" in n for n in comp_names)
        assert any("動能風格" in n for n in comp_names)
        assert any("微觀造市利差" in n for n in comp_names)
        assert any("跨幣匯差損益" in n for n in comp_names)
        assert any("純特異超額 Alpha" in n for n in comp_names)

        # Verify serialization
        d = report.to_dict()
        assert "total_portfolio_return_pct" in d
        assert "r_squared" in d
        assert "components" in d
        assert "factor_decay_metrics" in d

    def test_decompose_orthogonal_returns_custom_vectors(self, service):
        p_returns = [0.01, 0.02, -0.005, 0.015, 0.008, 0.012]
        mkt_returns = [0.008, 0.015, -0.004, 0.010, 0.006, 0.009]
        factors = {
            "momentum": [0.005, 0.007, -0.002, 0.008, 0.004, 0.005],
            "value": [0.002, 0.003, 0.001, 0.002, 0.001, 0.002],
        }

        report = service.decompose_orthogonal_returns(
            portfolio_returns=p_returns,
            market_returns=mkt_returns,
            factor_returns_matrix=factors,
            lookback_days=30,
        )

        assert report.lookback_days == 30
        assert len(report.components) >= 8
        assert 0.0 <= report.r_squared <= 1.0

    def test_format_attribution_report(self, service):
        report = service.decompose_orthogonal_returns()
        card = service.format_attribution_report(report)
        assert "投組多因子正交殘差收益歸因儀表" in card
        assert "多因子施密特正交分解" in card
        assert "純特異超額 Alpha" in card
        assert "|" in card

    def test_format_decay_board(self, service):
        metrics = service.calculate_factor_decay_metrics()
        board = service.format_decay_board(metrics)
        assert "量化多因子風險衰減與半衰期監控看板" in board
        assert "半衰期" in board
        assert "動態調倉與權重防守建議" in board
        assert "滾動 IC" in board

    def test_redis_persistence(self, service):
        report = service.decompose_orthogonal_returns()

        with patch("src.infrastructure.cache.redis_client.get_redis_sync") as mock_redis_func:
            mock_r = MagicMock()
            mock_redis_func.return_value = mock_r
            mock_r.get.return_value = '{"total_portfolio_return_pct": 5.25}'

            service._save_report_to_redis(report)
            mock_r.set.assert_called()

            # Memory hit
            cached = service.load_latest_report()
            assert cached is not None
            assert cached["total_portfolio_return_pct"] == round(report.total_portfolio_return_pct, 4)

            # Force redis fetch
            service._MEMORY_CACHE.clear()
            redis_cached = service.load_latest_report()
            assert redis_cached is not None
            assert redis_cached["total_portfolio_return_pct"] == 5.25
