import pytest
import math
from unittest.mock import MagicMock
from src.services.kalman_pairs_cointegration_service import (
    KalmanPairsCointegrationService,
    KalmanPairsMetric,
)

@pytest.fixture
def anyio_backend():
    return 'asyncio'

def test_kalman_filter_recursion():
    """Verify 2D Kalman filter correctly tracks dynamic beta on linear relationship y = 2.5 * x + 5."""
    # Generate linear synthetic data with small noise
    x_series = [10.0 + i * 0.5 for i in range(50)]
    y_series = [5.0 + 2.5 * x + 0.1 * math.sin(i) for i, x in enumerate(x_series)]

    alphas, betas, spreads = KalmanPairsCointegrationService.run_kalman_filter_series(y_series, x_series)

    assert len(alphas) == 50
    assert len(betas) == 50
    assert len(spreads) == 50

    # Beta should converge toward 2.5
    final_beta = betas[-1]
    assert 2.0 <= final_beta <= 3.0
    # Spreads should be small
    assert abs(spreads[-1]) < 2.0

def test_ou_half_life_calculation():
    """Verify Ornstein-Uhlenbeck AR(1) half life calculation on stationary vs explosive series."""
    # 1. Strongly mean-reverting series (b < 0)
    # e_t = 0.5 * e_{t-1} -> Δe_t = -0.5 * e_{t-1} -> b = -0.5 -> t_1/2 = -ln(2)/ln(0.5) = 1.0
    spread_stationary = []
    val = 1.0
    for i in range(40):
        val = 0.5 * val + 0.05 * math.cos(i)
        spread_stationary.append(val)

    hl_stat = KalmanPairsCointegrationService.calculate_ou_half_life(spread_stationary)
    assert 0.5 <= hl_stat <= 5.0

    # 2. Explosive / trending series (b >= 0)
    spread_explosive = [1.0 + i * 2.0 for i in range(40)]
    hl_exp = KalmanPairsCointegrationService.calculate_ou_half_life(spread_explosive)
    assert hl_exp >= 999.0

def test_spread_zscore_calculation():
    """Verify rolling Z-score computation on spread."""
    spreads = [0.0] * 20
    spreads.extend([0.0, 1.0, -1.0, 0.5, -0.5] * 3)
    # Add extreme positive shock
    spreads.append(4.0)

    z = KalmanPairsCointegrationService.calculate_spread_zscore(spreads, lookback=20)
    assert z > 2.0

@pytest.mark.anyio
async def test_evaluate_pairs_cointegration():
    """Verify full pairs evaluation and report generation."""
    service = KalmanPairsCointegrationService(user_id="test_user")

    metric = await service.evaluate_pairs_cointegration("NVDA", "AMD")
    assert metric.ticker_y == "NVDA"
    assert metric.ticker_x == "AMD"
    assert metric.regime in (
        KalmanPairsCointegrationService.REGIME_EQUILIBRIUM,
        KalmanPairsCointegrationService.REGIME_DIVERGENCE,
        KalmanPairsCointegrationService.REGIME_REVERSION,
        KalmanPairsCointegrationService.REGIME_STRUCTURAL_BREAK,
    )
    assert metric.target_hedge_ratio_x_per_y > 0.0

    # Format report
    report = service.format_pairs_report(metric)
    assert "卡爾曼濾波動態協整" in report
    assert "NVDA" in report
    assert "AMD" in report
    assert "動態對沖比率" in report

def test_kalman_metric_serialization():
    """Verify to_dict and from_dict roundtrip."""
    m = KalmanPairsMetric(
        ticker_y="GOOGL",
        ticker_x="MSFT",
        price_y=180.0,
        price_x=450.0,
        dynamic_beta=0.40,
        dynamic_alpha=2.5,
        residual_spread=1.2,
        spread_zscore=1.85,
        ou_half_life_days=8.5,
        regime=KalmanPairsCointegrationService.REGIME_DIVERGENCE,
        arbitrage_action=KalmanPairsCointegrationService.ACTION_SHORT_Y_LONG_X,
        target_hedge_ratio_x_per_y=0.40,
        requires_circuit_breaker=False,
        rationale="Test pairs rationale",
    )
    d = m.to_dict()
    m2 = KalmanPairsMetric.from_dict(d)
    assert m2.ticker_y == "GOOGL"
    assert m2.ticker_x == "MSFT"
    assert m2.dynamic_beta == 0.40
    assert m2.spread_zscore == 1.85
    assert m2.regime == KalmanPairsCointegrationService.REGIME_DIVERGENCE
