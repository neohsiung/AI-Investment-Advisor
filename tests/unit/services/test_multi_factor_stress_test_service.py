"""
Unit tests for MultiFactorStressTestService (Phase 68).
Validates multi-scenario stress simulation, correlation shrinkage,
liquidity squeeze, cash buffer resilience, and dashboard formatting.
"""

import pytest
from src.services.multi_factor_stress_test_service import (
    MultiFactorStressTestService,
    StressScenarioType,
    PortfolioResilienceTier,
    MultiFactorStressTestReport,
)


@pytest.fixture
def stress_service():
    return MultiFactorStressTestService(user_id="test_user_p68")


def test_default_scenarios_exist(stress_service):
    """Ensure all 4 core historical and synthetic scenarios are defined."""
    scenarios = stress_service.DEFAULT_SCENARIOS
    assert len(scenarios) == 4
    assert StressScenarioType.QUANT_QUAKE_2007.value in scenarios
    assert StressScenarioType.COVID_LIQUIDITY_CRUNCH_2020.value in scenarios
    assert StressScenarioType.RATE_SHOCK_STAGFLATION_2022.value in scenarios
    assert StressScenarioType.FLASH_CRASH_SPREAD_BLOWOUT.value in scenarios


def test_run_stress_test_synthetic_fallback(stress_service):
    """Ensure 0-latency synthetic baseline executes properly when portfolio is empty."""
    report = stress_service.run_stress_test(portfolio=None)

    assert isinstance(report, MultiFactorStressTestReport)
    assert report.portfolio_nlv == 10000.0
    assert report.available_cash == 2000.0
    assert report.cash_ratio == 0.20
    assert len(report.scenarios) == 4
    assert report.worst_case_scenario is not None
    assert report.capital_preservation_score >= 0.0


def test_run_stress_test_custom_portfolio(stress_service):
    """Test stress test with a custom tech-heavy portfolio."""
    portfolio = {
        "total_nlv": 50000.0,
        "available_cash": 10000.0,
        "positions": [
            {"ticker": "NVDA", "shares": 100.0, "current_price": 200.0, "weight": 0.40},
            {"ticker": "QQQ", "shares": 40.0, "current_price": 400.0, "weight": 0.32},
            {"ticker": "GLD", "shares": 20.0, "current_price": 200.0, "weight": 0.08},
        ],
    }
    report = stress_service.run_stress_test(portfolio=portfolio)

    assert report.portfolio_nlv == 50000.0
    covid_res = report.scenarios.get(StressScenarioType.COVID_LIQUIDITY_CRUNCH_2020.value)
    assert covid_res is not None
    # High-beta tech portfolio suffers severe drawdown during COVID shock
    assert covid_res.total_loss_pct < -0.20
    assert covid_res.stressed_var_99_pct > 0.0
    assert covid_res.stressed_cvar_99_pct > covid_res.stressed_var_99_pct


def test_scenario_filter(stress_service):
    """Test filtering for a specific scenario by id or keyword."""
    report = stress_service.run_stress_test(scenario_id_filter="covid")
    assert len(report.scenarios) == 1
    assert StressScenarioType.COVID_LIQUIDITY_CRUNCH_2020.value in report.scenarios

    report_quake = stress_service.run_stress_test(scenario_id_filter="quake")
    assert len(report_quake.scenarios) == 1
    assert StressScenarioType.QUANT_QUAKE_2007.value in report_quake.scenarios


def test_liquidity_squeeze_and_spread_penalty(stress_service):
    """Verify that FLASH_CRASH_SPREAD_BLOWOUT applies high slippage penalty."""
    report = stress_service.run_stress_test(scenario_id_filter="flash")
    flash_res = report.scenarios.get(StressScenarioType.FLASH_CRASH_SPREAD_BLOWOUT.value)

    assert flash_res is not None
    # High spread multiplier (10x) and 85% haircut should result in noticeable slippage loss
    assert flash_res.liquidity_slippage_loss_pct > 0.001


def test_cash_depletion_risk(stress_service):
    """Verify cash depletion warning when cash ratio is near zero."""
    zero_cash_portfolio = {
        "total_nlv": 10000.0,
        "available_cash": 0.0,
        "positions": [
            {"ticker": "SPY", "shares": 20.0, "current_price": 500.0, "weight": 1.0},
        ],
    }
    report = stress_service.run_stress_test(portfolio=zero_cash_portfolio)
    covid_res = report.scenarios.get(StressScenarioType.COVID_LIQUIDITY_CRUNCH_2020.value)

    assert covid_res.cash_depletion_risk is True
    assert covid_res.remaining_cash_ratio == 0.0


def test_resilience_classification(stress_service):
    """Verify resilience classification tiers."""
    # Defensive portfolio: 50% Cash, 25% GLD, 25% TLT
    defensive_portfolio = {
        "total_nlv": 20000.0,
        "available_cash": 10000.0,
        "positions": [
            {"ticker": "GLD", "shares": 25.0, "current_price": 200.0, "weight": 0.25},
            {"ticker": "TLT", "shares": 50.0, "current_price": 100.0, "weight": 0.25},
        ],
    }
    report = stress_service.run_stress_test(portfolio=defensive_portfolio)
    assert report.overall_resilience in (PortfolioResilienceTier.RESILIENT, PortfolioResilienceTier.VULNERABLE)
    assert report.capital_preservation_score > 60.0


def test_format_stress_test_dashboard(stress_service):
    """Verify dashboard output contains all key sections."""
    report = stress_service.run_stress_test()
    dashboard = stress_service.format_stress_test_dashboard(report)

    assert "跨市場多因子極端情境壓力測試與流動性擠壓模擬" in dashboard
    assert "資本保全評分" in dashboard
    assert "四大歷史與合成極端衝擊壓力測試總覽" in dashboard
    assert "20% 現金儲備防護" in dashboard
    assert "25% 換手率約束門禁" in dashboard


def test_format_scenario_deep_dive(stress_service):
    """Verify deep-dive breakdown output."""
    report = stress_service.run_stress_test()
    deep_dive = stress_service.format_scenario_deep_dive(report, "covid")

    assert "極端情境深層穿透剖析" in deep_dive
    assert "損益衝擊與風險分解" in deep_dive
    assert "風控應對方針" in deep_dive
