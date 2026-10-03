"""
Unit and Integration Tests for Extreme Value Theory (EVT) Service (O2).
測試黑天鵝極值理論與超額峰值 (POT) 尾部風險外推引擎。
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from src.services.extreme_value_theory_service import (
    ExtremeValueTheoryService,
    GPDParameters,
    TailDomain,
    BlackSwanAlertLevel,
    EVTTailRiskMetrics,
    PortfolioEVTAssessment,
)
from src.services.stress_testing_service import StressTestingService
from src.services.portfolio_adaptive_intelligence_service import (
    PortfolioAdaptiveIntelligenceService,
)


class MockSettingsRepo:
    def __init__(self, overrides: dict[str, object] | None = None):
        self.overrides = overrides or {}

    def get(self, *args, **kwargs) -> object | None:
        key = args[1] if len(args) > 1 else (args[0] if args else "")
        return self.overrides.get(key)

    def get_setting(self, key: str) -> object | None:
        return self.overrides.get(key)


@pytest.fixture
def evt_service() -> ExtremeValueTheoryService:
    return ExtremeValueTheoryService()


@pytest.fixture
def synthetic_fat_tailed_returns() -> np.ndarray:
    """Generate 500 daily returns with Student-t fat tails (df=3.5)."""
    np.random.seed(42)
    # Student-t with 3.5 df scaled to daily vol ~ 1.5%
    t_samples = np.random.standard_t(df=3.5, size=500)
    returns = 0.0004 + t_samples * 0.012
    return returns


@pytest.fixture
def synthetic_normal_returns() -> np.ndarray:
    """Generate 500 daily returns from thin-tailed Gaussian distribution."""
    np.random.seed(101)
    returns = np.random.normal(loc=0.0005, scale=0.012, size=500)
    return returns


def test_gpd_pwm_parameter_fitting_accuracy(evt_service: ExtremeValueTheoryService):
    """Verify PWM estimation on synthetic GPD sample closely recovers parameters."""
    np.random.seed(123)
    # Generate exceedances directly from GPD(xi=0.20, sigma=0.025)
    # CDF: F(y) = 1 - (1 + xi * y / sigma)^(-1/xi)
    # Inv: y = (sigma / xi) * ((1 - u)^(-xi) - 1)
    xi_true = 0.20
    sigma_true = 0.025
    u_rand = np.random.uniform(0.001, 0.999, size=300)
    exceedances = (sigma_true / xi_true) * (np.power(1.0 - u_rand, -xi_true) - 1.0)
    
    # Prepend baseline losses so threshold u = 0.03
    base_losses = np.random.uniform(0.001, 0.03, size=700)
    full_losses = np.concatenate([base_losses, 0.03 + exceedances])

    params = evt_service.fit_gpd(full_losses, threshold_quantile=0.70, method="pwm")

    assert params.tail_domain == TailDomain.FRECHET_HEAVY
    assert params.estimation_method == "PWM"
    assert params.exceedances_count > 50
    # Parameter accuracy within reasonable statistical confidence
    assert 0.05 < params.xi < 0.40
    assert 0.010 < params.sigma < 0.045
    assert params.standard_error_xi > 0


def test_gpd_mle_parameter_fitting(evt_service: ExtremeValueTheoryService, synthetic_fat_tailed_returns: np.ndarray):
    """Verify MLE optimization method converges and yields valid parameters."""
    losses = -synthetic_fat_tailed_returns
    params = evt_service.fit_gpd(losses, threshold_quantile=0.90, method="mle")

    assert params.estimation_method == "MLE"
    assert params.xi > 0  # Fat-tailed
    assert params.sigma > 0
    assert params.threshold_u > 0
    assert params.exceedances_count >= 10


def test_closed_form_evt_var_extrapolation(evt_service: ExtremeValueTheoryService):
    """Verify mathematical monotonicity and precision of closed-form EVT VaR."""
    params = GPDParameters(
        xi=0.25,
        sigma=0.02,
        threshold_u=0.035,
        exceedances_count=50,
        total_count=500,  # ratio = 0.10
        tail_domain=TailDomain.FRECHET_HEAVY,
        estimation_method="PWM",
    )

    var_95 = evt_service.calculate_evt_var(params, 0.95)
    var_99 = evt_service.calculate_evt_var(params, 0.99)
    var_995 = evt_service.calculate_evt_var(params, 0.995)
    var_999 = evt_service.calculate_evt_var(params, 0.999)

    # Monotonicity check: higher confidence -> higher VaR
    assert params.threshold_u <= var_95 < var_99 < var_995 < var_999

    # Analytical test for alpha=0.99:
    # factor = (1 - 0.99) / 0.10 = 0.10
    # VaR_0.99 = 0.035 + (0.02 / 0.25) * [ (0.10)^(-0.25) - 1 ]
    expected_var_99 = 0.035 + 0.08 * (math.pow(0.10, -0.25) - 1.0)
    assert pytest.approx(var_99, rel=1e-4) == expected_var_99


def test_closed_form_evt_expected_shortfall(evt_service: ExtremeValueTheoryService):
    """Verify Expected Shortfall (CVaR) adheres to the GPD excess mean property."""
    params = GPDParameters(
        xi=0.20,
        sigma=0.018,
        threshold_u=0.030,
        exceedances_count=40,
        total_count=400,
        tail_domain=TailDomain.FRECHET_HEAVY,
        estimation_method="PWM",
    )

    for alpha in [0.95, 0.99, 0.999]:
        var_alpha = evt_service.calculate_evt_var(params, alpha)
        es_alpha = evt_service.calculate_evt_es(params, alpha)

        # ES must strictly exceed VaR for continuous distributions
        assert es_alpha > var_alpha

        # Analytical formula check: ES = (VaR + sigma - xi * u) / (1 - xi)
        expected_es = (var_alpha + 0.018 - 0.20 * 0.030) / (1.0 - 0.20)
        assert pytest.approx(es_alpha, rel=1e-4) == expected_es


def test_tail_fatness_ratio_and_black_swan_alert(
    evt_service: ExtremeValueTheoryService,
    synthetic_fat_tailed_returns: np.ndarray,
    synthetic_normal_returns: np.ndarray,
):
    """Verify that fat-tailed returns trigger elevated alert and high fatness ratio."""
    # 1. Fat-tailed evaluation
    fat_assessment = evt_service.assess_tail_risk(synthetic_fat_tailed_returns)
    assert fat_assessment.portfolio_metrics.tail_fatness_ratio_999 > 1.20
    assert fat_assessment.portfolio_metrics.alert_level in (
        BlackSwanAlertLevel.ELEVATED,
        BlackSwanAlertLevel.HIGH,
        BlackSwanAlertLevel.EXTREME_BLACK_SWAN,
    )
    assert fat_assessment.portfolio_metrics.es_999 > fat_assessment.portfolio_metrics.var_999

    # 2. Gaussian/thin-tailed evaluation
    thin_assessment = evt_service.assess_tail_risk(synthetic_normal_returns)
    # Gaussian tail fatness ratio should be noticeably lower than fat-tailed
    assert (
        fat_assessment.portfolio_metrics.tail_fatness_ratio_999
        > thin_assessment.portfolio_metrics.tail_fatness_ratio_999
    )


def test_small_sample_and_sparse_exceedances_fallback(evt_service: ExtremeValueTheoryService):
    """Verify graceful parametric degradation on tiny sample size without raising exceptions."""
    tiny_returns = [0.01, -0.02, 0.005, -0.01, 0.03]
    assessment = evt_service.assess_tail_risk(tiny_returns)

    assert assessment.portfolio_metrics.var_99 > 0
    assert assessment.portfolio_metrics.es_99 > 0
    assert assessment.gpd_parameters.estimation_method in (
        "FALLBACK_PARAMETRIC",
        "FALLBACK_EXPONENTIAL",
    )


def test_extreme_heavy_tail_infinite_mean_safety_clamp(evt_service: ExtremeValueTheoryService):
    """Verify safety clamping when shape parameter xi approaches or exceeds 1.0."""
    params_extreme = GPDParameters(
        xi=1.15,  # Infinite mean regime
        sigma=0.03,
        threshold_u=0.04,
        exceedances_count=20,
        total_count=200,
        tail_domain=TailDomain.FRECHET_HEAVY,
        estimation_method="PWM",
    )

    # calculate_evt_es should not divide by negative (1 - 1.15) or raise ZeroDivisionError
    es_val = evt_service.calculate_evt_es(params_extreme, 0.99)
    var_val = evt_service.calculate_evt_var(params_extreme, 0.99)

    assert es_val >= var_val
    assert not math.isnan(es_val)
    assert not math.isinf(es_val)


def test_asset_level_tail_profiling(evt_service: ExtremeValueTheoryService):
    """Verify cross-sectional asset tail index extraction and ordering."""
    np.random.seed(999)
    n = 300
    # Safe tech with moderate vol
    aapl_ret = np.random.normal(0.0005, 0.015, n)
    # High-beta high-fat tail asset
    t_shocks = np.random.standard_t(df=2.8, size=n)
    nvda_ret = 0.0008 + t_shocks * 0.035

    weights = {"AAPL": 0.40, "NVDA": 0.60}
    asset_returns = {"AAPL": aapl_ret, "NVDA": nvda_ret}
    port_ret = 0.40 * aapl_ret + 0.60 * nvda_ret

    assessment = evt_service.assess_tail_risk(
        returns=port_ret,
        weights=weights,
        asset_returns=asset_returns,
    )

    assert len(assessment.asset_contributions) == 2
    # NVDA must be diagnosed with fatter tail / higher 99.9% VaR than AAPL
    contrib_map = {c.symbol: c for c in assessment.asset_contributions}
    assert contrib_map["NVDA"].var_999 > contrib_map["AAPL"].var_999
    assert contrib_map["NVDA"].es_999 > contrib_map["AAPL"].es_999


def test_stress_testing_service_evt_integration(synthetic_fat_tailed_returns: np.ndarray):
    """Verify StressTestingService successfully integrates O2 EVT metrics."""
    evt_svc = ExtremeValueTheoryService()
    stress_svc = StressTestingService(evt_service=evt_svc)

    weights = {"AAPL": 0.5, "MSFT": 0.5}
    betas = {"AAPL": 1.1, "MSFT": 1.0}
    sectors = {"AAPL": "Technology", "MSFT": "Technology"}
    vols = {"AAPL": 0.22, "MSFT": 0.20}

    assessment = stress_svc.evaluate_portfolio(
        weights=weights,
        betas=betas,
        sectors=sectors,
        vols=vols,
        historical_portfolio_returns=list(synthetic_fat_tailed_returns),
    )

    assert assessment.evt_var_999 is not None
    assert assessment.evt_cvar_999 is not None
    assert assessment.tail_fatness_ratio is not None
    assert assessment.black_swan_alert is not None
    assert assessment.evt_cvar_999 > assessment.cvar_99

    as_dict = assessment.to_dict()
    assert "evt_var_999" in as_dict
    assert "tail_fatness_ratio" in as_dict
    assert "black_swan_alert" in as_dict


def test_portfolio_adaptive_intelligence_evt_integration(synthetic_fat_tailed_returns: np.ndarray):
    """Verify PortfolioAdaptiveIntelligenceService incorporates EVT into radar and diagnostic report."""
    evt_svc = ExtremeValueTheoryService()
    orchestrator = PortfolioAdaptiveIntelligenceService(evt_service=evt_svc)

    current_weights = {"AAPL": 0.5, "MSFT": 0.5}
    returns_history = {
        "PORTFOLIO": list(synthetic_fat_tailed_returns),
        "AAPL": list(synthetic_fat_tailed_returns),
        "MSFT": list(synthetic_fat_tailed_returns),
    }

    report = orchestrator.diagnose_portfolio(
        current_weights=current_weights,
        portfolio_value=100000.0,
        returns_history=returns_history,
    )

    tail_analysis = report.tail_risk_analysis
    assert "evt_var_999" in tail_analysis
    assert "evt_cvar_999" in tail_analysis
    assert "tail_fatness_ratio" in tail_analysis
    assert "black_swan_alert" in tail_analysis
    assert "tail_domain" in tail_analysis

    # 5D Radar tail risk resilience must remain bounded between 0 and 100
    assert 0.0 <= report.radar_dimensions.tail_risk_resilience <= 100.0
    assert 0.0 <= report.health_score <= 100.0


def test_distribution_comparison_matrix(
    evt_service: ExtremeValueTheoryService, synthetic_fat_tailed_returns: np.ndarray
):
    """Verify compare_distributions matrix calculates Empirical, Gaussian, and EVT side by side."""
    losses = -synthetic_fat_tailed_returns
    matrix = evt_service.compare_distributions(losses)

    assert "comparison" in matrix
    assert len(matrix["comparison"]) == 4  # 95%, 99%, 99.5%, 99.9%
    for row in matrix["comparison"]:
        assert "alpha" in row
        assert "empirical_var" in row
        assert "gaussian_var" in row
        assert "evt_gpd_var" in row
        assert "evt_gpd_es" in row
        assert "tail_fatness_multiplier" in row
        assert row["evt_gpd_es"] >= row["evt_gpd_var"]
