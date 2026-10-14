import pytest
import math
from unittest.mock import MagicMock
from src.services.option_gamma_exposure_gex_service import (
    OptionGammaExposureGEXService,
    GEXExposureMetric,
)

@pytest.fixture
def anyio_backend():
    return 'asyncio'

def test_bsm_gamma_calculation():
    """Verify BSM Gamma calculation matches standard financial formulas."""
    spot = 100.0
    strike = 100.0
    t = 0.25  # 3 months
    iv = 0.20
    r = 0.05

    gamma = OptionGammaExposureGEXService.calculate_bsm_gamma(spot, strike, t, iv, r)
    assert gamma > 0.0
    # For ATM option S=K=100, t=0.25, iv=0.2, gamma is roughly 0.038 ~ 0.040
    assert 0.035 <= gamma <= 0.045

    # Boundary conditions
    assert OptionGammaExposureGEXService.calculate_bsm_gamma(0.0, 100.0, t, iv) == 0.0
    assert OptionGammaExposureGEXService.calculate_bsm_gamma(100.0, 0.0, t, iv) == 0.0
    assert OptionGammaExposureGEXService.calculate_bsm_gamma(100.0, 100.0, 0.0, iv) == 0.0

def test_dollar_gex_call_vs_put():
    """Call GEX should be positive (dealer long gamma), Put GEX should be negative."""
    spot = 150.0
    strike = 150.0
    oi = 500.0
    t = 0.1
    iv = 0.25

    call_gex = OptionGammaExposureGEXService.calculate_dollar_gex_for_contract("CALL", spot, strike, oi, t, iv)
    put_gex = OptionGammaExposureGEXService.calculate_dollar_gex_for_contract("PUT", spot, strike, oi, t, iv)

    assert call_gex > 0.0
    assert put_gex < 0.0
    assert math.isclose(call_gex, -put_gex, rel_tol=1e-5)

def test_aggregate_gex_profile_and_pin_strike():
    """Verify aggregation across option chain correctly computes net GEX and pin strike."""
    spot = 200.0
    chain = [
        {"type": "CALL", "strike": 200.0, "open_interest": 1000.0, "implied_volatility": 0.20, "days_to_expiry": 2},
        {"type": "CALL", "strike": 210.0, "open_interest": 5000.0, "implied_volatility": 0.22, "days_to_expiry": 2},
        {"type": "PUT", "strike": 190.0, "open_interest": 800.0, "implied_volatility": 0.25, "days_to_expiry": 2},
        {"type": "PUT", "strike": 200.0, "open_interest": 1200.0, "implied_volatility": 0.20, "days_to_expiry": 2},
    ]

    profile = OptionGammaExposureGEXService.compute_aggregate_gex_profile(spot, chain)
    assert "net_gex" in profile
    assert profile["call_gex"] > 0
    assert profile["put_gex"] < 0
    # Strike 210 has highest OI (5000)
    assert profile["max_oi_pin_strike"] == 210.0
    assert profile["days_to_opex"] == 2

def test_estimate_zero_gamma_flip_point():
    """Verify zero-gamma flip point root finding converges."""
    spot = 100.0
    # Create chain with large Call OI above 100 and large Put OI below 100
    chain = [
        {"type": "CALL", "strike": 105.0, "open_interest": 2000.0, "implied_volatility": 0.20, "days_to_expiry": 14},
        {"type": "CALL", "strike": 110.0, "open_interest": 1500.0, "implied_volatility": 0.20, "days_to_expiry": 14},
        {"type": "PUT", "strike": 95.0, "open_interest": 2500.0, "implied_volatility": 0.25, "days_to_expiry": 14},
        {"type": "PUT", "strike": 90.0, "open_interest": 3000.0, "implied_volatility": 0.25, "days_to_expiry": 14},
    ]
    flip = OptionGammaExposureGEXService.estimate_zero_gamma_flip_point(spot, chain)
    assert 75.0 <= flip <= 125.0

@pytest.mark.anyio
async def test_evaluate_ticker_gex_regimes():
    """Verify regime classification logic."""
    service = OptionGammaExposureGEXService(user_id="test_user")

    # Positive Gamma Regime (default synthetic with balanced OI)
    metric = await service.evaluate_ticker_gex("NVDA", spot_price=230.0)
    assert metric.ticker == "NVDA"
    assert metric.spot_price == 230.0
    assert metric.regime in (
        OptionGammaExposureGEXService.REGIME_POSITIVE_GAMMA,
        OptionGammaExposureGEXService.REGIME_FLIP_WARNING,
        OptionGammaExposureGEXService.REGIME_NEGATIVE_GAMMA,
        OptionGammaExposureGEXService.REGIME_OPEX_PIN,
    )

    # Format report verification
    report = service.format_gex_report(metric)
    assert "做市商淨伽馬暴露" in report
    assert "NVDA" in report
    assert "$230.00" in report
    assert "Net GEX" in report

def test_metric_serialization():
    """Verify to_dict and from_dict roundtrip."""
    m = GEXExposureMetric(
        ticker="SPY",
        spot_price=580.0,
        net_gex=12500000.0,
        call_gex=20000000.0,
        put_gex=-7500000.0,
        zero_gamma_flip_point=572.5,
        distance_to_flip_pct=0.0129,
        max_oi_pin_strike=580.0,
        pinning_gravity_score=0.85,
        days_to_opex=2,
        regime=OptionGammaExposureGEXService.REGIME_OPEX_PIN,
        volatility_damping_multiplier=0.70,
        requires_protection=False,
        rationale="OpEx Pin test",
    )
    d = m.to_dict()
    m2 = GEXExposureMetric.from_dict(d)
    assert m2.ticker == "SPY"
    assert m2.spot_price == 580.0
    assert m2.regime == OptionGammaExposureGEXService.REGIME_OPEX_PIN
    assert m2.days_to_opex == 2
