"""
Unit Tests for Portfolio Adaptive Intelligence Service & API (D1 Engine).
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.services.portfolio_adaptive_intelligence_service import (
    PortfolioAdaptiveIntelligenceService,
    AdaptiveDiagnosticReport,
    HealthRating,
    HealthRadarDimensions,
)
from src.services.regime_hmm_service import RegimeState
from src.api.v1.router import api_v1_router


@pytest.fixture
def sample_portfolio_weights():
    return {
        "AAPL": 0.25,
        "MSFT": 0.25,
        "GOOGL": 0.20,
        "AMZN": 0.15,
        "CASH": 0.15,
    }


@pytest.fixture
def sample_prices():
    return {
        "AAPL": 220.0,
        "MSFT": 420.0,
        "GOOGL": 180.0,
        "AMZN": 185.0,
    }


@pytest.fixture
def sample_advs():
    return {
        "AAPL": 50000000.0,
        "MSFT": 25000000.0,
        "GOOGL": 20000000.0,
        "AMZN": 30000000.0,
    }


@pytest.fixture
def adaptive_service():
    return PortfolioAdaptiveIntelligenceService()


def test_full_portfolio_diagnosis_normal_market(
    adaptive_service, sample_portfolio_weights, sample_prices, sample_advs
):
    """驗證正常市場行情下的完整 8 大維度交叉診斷與報告生成"""
    market_obs = {
        "spy_trend_ratio": 1.03,
        "vix": 16.5,
        "return_5d": 0.012,
    }
    report: AdaptiveDiagnosticReport = adaptive_service.diagnose_portfolio(
        current_weights=sample_portfolio_weights,
        portfolio_value=200000.0,
        asset_prices=sample_prices,
        asset_advs=sample_advs,
        market_observation=market_obs,
        current_drawdown=0.03,
    )

    assert isinstance(report, AdaptiveDiagnosticReport)
    assert 0.0 <= report.health_score <= 100.0
    assert report.health_rating in [HealthRating.OPTIMAL, HealthRating.BALANCED, HealthRating.CAUTION]

    # 驗證五維雷達
    radar = report.radar_dimensions
    assert 0.0 <= radar.regime_alignment <= 100.0
    assert 0.0 <= radar.diversification_efficiency <= 100.0
    assert 0.0 <= radar.factor_balance <= 100.0
    assert 0.0 <= radar.tail_risk_resilience <= 100.0
    assert 0.0 <= radar.capital_safety <= 100.0

    # 驗證各子模組診斷字典
    assert "current_regime" in report.regime_analysis
    assert "current_exposures" in report.factor_exposures
    assert "diversification_ratio" in report.diversification_metrics
    assert "cvar_99" in report.tail_risk_analysis
    assert "shrinkage_factor" in report.capital_safety_metrics
    assert "needs_rebalance" in report.rebalance_recommendation
    assert len(report.summary_insights) >= 3


def test_bear_crisis_regime_alignment(adaptive_service, sample_portfolio_weights):
    """驗證熊市危機情境下 O1 HMM 辨識與現金防線拉升"""
    bear_obs = {
        "spy_trend_ratio": 0.88,
        "vix": 38.0,
        "return_5d": -0.065,
    }
    report = adaptive_service.diagnose_portfolio(
        current_weights=sample_portfolio_weights,
        portfolio_value=100000.0,
        market_observation=bear_obs,
        current_drawdown=0.15,
    )

    regime = report.regime_analysis.get("current_regime")
    assert regime == RegimeState.BEAR.value
    # 熊市建議現金防線應顯著拉高 (>= 30%)
    suggested_cash = report.regime_analysis.get("suggested_cash_pct", 0.0)
    assert suggested_cash >= 0.30
    assert report.regime_analysis.get("suggested_target_beta") <= 0.70


def test_concentrated_portfolio_low_diversification_score(adaptive_service):
    """驗證高度集中之單一部位投組在 M2 分散化維度被扣分"""
    concentrated_weights = {
        "TSLA": 0.95,
        "CASH": 0.05,
    }
    report = adaptive_service.diagnose_portfolio(
        current_weights=concentrated_weights,
        portfolio_value=50000.0,
    )

    hhi = report.diversification_metrics.get("herfindahl_index", 0.0)
    assert hhi >= 0.80  # 高度集中
    # 分散化雷達得分應受到懲罰
    assert report.radar_dimensions.diversification_efficiency <= 65.0
    # 洞察清單應包含分散化警告
    assert any("分散化" in insight for insight in report.summary_insights)


def test_factor_exposure_and_quality_bonus(adaptive_service, sample_portfolio_weights):
    """驗證 M6 多因子雷達與熊市/震盪品質因子增益"""
    neutral_obs = {
        "spy_trend_ratio": 1.00,
        "vix": 21.0,
        "return_5d": -0.005,
    }
    report = adaptive_service.diagnose_portfolio(
        current_weights=sample_portfolio_weights,
        portfolio_value=100000.0,
        market_observation=neutral_obs,
    )

    factors = report.factor_exposures.get("current_exposures", {})
    assert "value" in factors
    assert "momentum" in factors
    assert "quality" in factors
    assert "low_vol" in factors
    assert "smart_money" in factors


def test_tail_risk_cvar_and_stress_integration(adaptive_service, sample_portfolio_weights):
    """驗證 M5 蒙地卡羅 99% CVaR 與歷史情境最大回撤計算"""
    report = adaptive_service.diagnose_portfolio(
        current_weights=sample_portfolio_weights,
        portfolio_value=150000.0,
    )

    tail = report.tail_risk_analysis
    assert tail.get("var_95") > 0.0
    assert tail.get("cvar_99") >= tail.get("var_95")
    assert tail.get("worst_historical_drop") < 0.0  # 歷史情境跌幅為負
    assert len(tail.get("worst_scenario_name")) > 0


def test_kelly_capital_safety_shrinkage(adaptive_service, sample_portfolio_weights):
    """驗證深幅回撤時 M4 凱利縮減因子對資本安全評分之調控"""
    deep_dd_report = adaptive_service.diagnose_portfolio(
        current_weights=sample_portfolio_weights,
        portfolio_value=100000.0,
        current_drawdown=0.28,  # 28% 深幅回撤
    )

    cap = deep_dd_report.capital_safety_metrics
    shrinkage = cap.get("shrinkage_factor")
    assert shrinkage < 1.0  # 縮減因子必須啟動保護
    assert cap.get("recommended_leverage") <= 1.0


def test_rebalance_trigger_and_sor_execution_plans(adaptive_service):
    """驗證偏離目標時 M3 換庫緩衝帶突破並透過 E1 SOR 產生拆單排程"""
    unbalanced_weights = {
        "AAPL": 0.60,
        "MSFT": 0.05,
        "GOOGL": 0.05,
        "CASH": 0.30,
    }
    prices = {"AAPL": 220.0, "MSFT": 420.0, "GOOGL": 180.0}
    advs = {"AAPL": 5000000.0, "MSFT": 3000000.0, "GOOGL": 2000000.0}

    report = adaptive_service.diagnose_portfolio(
        current_weights=unbalanced_weights,
        portfolio_value=500000.0,
        asset_prices=prices,
        asset_advs=advs,
    )

    rebal = report.rebalance_recommendation
    assert rebal.get("needs_rebalance") is True
    assert rebal.get("total_turnover") > 0.0
    assert len(rebal.get("trade_signals")) > 0

    # 驗證 E1 SOR 執行計畫
    plans = rebal.get("execution_plans")
    assert len(plans) > 0
    first_plan = plans[0]
    assert "routing_strategy" in first_plan
    assert "approved_quantity" in first_plan


def test_empty_and_zero_holdings_graceful_fallback(adaptive_service):
    """驗證空部位或零部位時的優雅平滑降級"""
    report = adaptive_service.diagnose_portfolio(
        current_weights={},
        portfolio_value=0.0,
    )

    assert report.health_score >= 0.0
    assert report.health_rating in [HealthRating.OPTIMAL, HealthRating.BALANCED, HealthRating.CAUTION, HealthRating.CRITICAL]
    assert report.radar_dimensions.regime_alignment >= 0.0


def test_settings_repo_dynamic_override():
    """驗證由 SettingsRepo 注入之自定義配置生效"""
    mock_repo = MagicMock()
    mock_repo.get.side_effect = lambda k: {
        "adaptive_intelligence_enabled": False,
        "adaptive_health_min_score_alert": 75.0,
    }.get(k, None)

    service = PortfolioAdaptiveIntelligenceService(settings_repo=mock_repo)
    assert service._get_setting("adaptive_health_min_score_alert", 60.0) == 75.0
    assert service._get_setting("adaptive_intelligence_enabled", True) is False


def test_api_endpoints_health_and_diagnose_contract():
    """驗證 FastAPI 端點 /health, /diagnose, /rebalance-plan 之契約調用"""
    app = FastAPI()
    app.include_router(api_v1_router, prefix="/api/v1")

    client = TestClient(app)

    # 1. Test GET /api/v1/adaptive-intelligence/health
    resp_health = client.get("/api/v1/adaptive-intelligence/health")
    assert resp_health.status_code == 200
    data_health = resp_health.json()
    assert data_health["status"] == "success"
    assert "health_score" in data_health
    assert "radar" in data_health
    assert "current_regime" in data_health
    assert "provenance" in data_health
    assert "holdings" in data_health["provenance"]
    assert "market_observation" in data_health["provenance"]
    assert "tail_risk" in data_health["provenance"]

    # 2. Test POST /api/v1/adaptive-intelligence/diagnose
    payload_diag = {
        "current_weights": {"SPY": 0.5, "QQQ": 0.3, "CASH": 0.2},
        "portfolio_value": 150000.0,
    }
    resp_diag = client.post("/api/v1/adaptive-intelligence/diagnose", json=payload_diag)
    assert resp_diag.status_code == 200
    data_diag = resp_diag.json()
    assert data_diag["status"] == "success"
    assert "health_score" in data_diag["data"]
    assert "radar_dimensions" in data_diag["data"]
    assert "rebalance_recommendation" in data_diag["data"]
    assert "provenance" in data_diag["data"]
    assert data_diag["data"]["provenance"]["holdings"] == "live"

    # 3. Test POST /api/v1/adaptive-intelligence/rebalance-plan
    payload_rebal = {
        "current_weights": {"SPY": 0.8, "TLT": 0.1, "CASH": 0.1},
        "portfolio_value": 250000.0,
    }
    resp_rebal = client.post("/api/v1/adaptive-intelligence/rebalance-plan", json=payload_rebal)
    assert resp_rebal.status_code == 200
    data_rebal = resp_rebal.json()
    assert data_rebal["status"] == "success"
    assert "rebalance_recommendation" in data_rebal["data"]
