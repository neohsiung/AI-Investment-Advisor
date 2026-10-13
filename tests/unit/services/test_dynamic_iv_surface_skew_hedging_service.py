"""
Unit tests for DynamicIVSurfaceSkewHedgingService (Phase 61A).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.dynamic_iv_surface_skew_hedging_service import (
    DynamicIVSurfaceSkewHedgingService,
    IVSurfaceTickerMetric,
)


@pytest.fixture
def mock_settings_service():
    svc = MagicMock()
    svc.get_setting = AsyncMock(side_effect=lambda key, default=None: default)
    return svc


@pytest.mark.asyncio
async def test_iv_surface_metric_serialization():
    metric = IVSurfaceTickerMetric(
        ticker="NVDA",
        regime="EXTREME_TAIL_INVERSION",
        put_iv_25d=0.55,
        call_iv_25d=0.32,
        skew_ratio=1.7188,
        front_month_iv=0.48,
        back_month_iv=0.42,
        term_structure_slope=-0.06,
        tail_risk_index=0.88,
        risk_budget_multiplier=0.40,
        recommended_downward_shift_pct=0.0068,
        rationale="Test extreme tail panic",
    )
    d = metric.to_dict()
    assert d["ticker"] == "NVDA"
    assert d["regime"] == "EXTREME_TAIL_INVERSION"
    assert d["skew_ratio"] == 1.7188
    assert d["term_structure_slope"] == -0.06
    assert d["tail_risk_index"] == 0.88

    restored = IVSurfaceTickerMetric.from_dict(d)
    assert restored.ticker == "NVDA"
    assert restored.regime == "EXTREME_TAIL_INVERSION"
    assert restored.skew_ratio == pytest.approx(1.7188, abs=1e-4)


@pytest.mark.asyncio
async def test_iv_surface_normal_regime(mock_settings_service):
    svc = DynamicIVSurfaceSkewHedgingService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Put IV 24%, Call IV 22% -> Skew = 1.09, Front 22%, Back 24% -> Slope = +0.02 (Contango)
    options_data = {
        "put_iv_25d": 0.24,
        "call_iv_25d": 0.22,
        "front_month_iv": 0.22,
        "back_month_iv": 0.24,
    }
    metric = await svc.assess_iv_surface("AAPL", options_chain_data=options_data)
    assert metric.regime == "NORMAL_SMILE"
    assert metric.risk_budget_multiplier == 1.0
    assert metric.recommended_downward_shift_pct == 0.0


@pytest.mark.asyncio
async def test_iv_surface_elevated_skew_warning(mock_settings_service):
    svc = DynamicIVSurfaceSkewHedgingService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Put IV 32%, Call IV 24% -> Skew = 1.33 (> 1.25 warning), Front 24%, Back 25% -> Slope = +0.01
    options_data = {
        "put_iv_25d": 0.32,
        "call_iv_25d": 0.24,
        "front_month_iv": 0.24,
        "back_month_iv": 0.25,
    }
    metric = await svc.assess_iv_surface("TSM", options_chain_data=options_data)
    assert metric.regime == "ELEVATED_SKEW_WARNING"
    assert metric.risk_budget_multiplier == 0.75
    assert metric.recommended_downward_shift_pct > 0.0


@pytest.mark.asyncio
async def test_iv_surface_extreme_tail_inversion(mock_settings_service):
    svc = DynamicIVSurfaceSkewHedgingService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Put IV 45%, Call IV 26% -> Skew = 1.73 (> 1.50 extreme), Front 38%, Back 32% -> Slope = -0.06 (Backwardation)
    options_data = {
        "put_iv_25d": 0.45,
        "call_iv_25d": 0.26,
        "front_month_iv": 0.38,
        "back_month_iv": 0.32,
    }
    metric = await svc.assess_iv_surface("NVDA", options_chain_data=options_data)
    assert metric.regime == "EXTREME_TAIL_INVERSION"
    assert metric.risk_budget_multiplier == 0.40
    assert metric.recommended_downward_shift_pct >= 0.0050


@pytest.mark.asyncio
async def test_iv_surface_call_euphoria(mock_settings_service):
    svc = DynamicIVSurfaceSkewHedgingService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Put IV 20%, Call IV 30% -> Skew = 0.67 (< 0.88 reverse skew)
    options_data = {
        "put_iv_25d": 0.20,
        "call_iv_25d": 0.30,
        "front_month_iv": 0.28,
        "back_month_iv": 0.29,
    }
    metric = await svc.assess_iv_surface("SPY", options_chain_data=options_data)
    assert metric.regime == "CALL_EUPHORIA_OVERHEATED"
    assert metric.risk_budget_multiplier == 0.85
    assert "Call 隱含波動率溢價顯著" in metric.rationale


@pytest.mark.asyncio
async def test_format_iv_skew_report(mock_settings_service):
    svc = DynamicIVSurfaceSkewHedgingService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    metric = IVSurfaceTickerMetric(
        ticker="NVDA",
        regime="EXTREME_TAIL_INVERSION",
        put_iv_25d=0.50,
        call_iv_25d=0.30,
        skew_ratio=1.67,
        front_month_iv=0.45,
        back_month_iv=0.40,
        term_structure_slope=-0.05,
        tail_risk_index=0.82,
        risk_budget_multiplier=0.40,
        recommended_downward_shift_pct=0.0064,
        rationale="極端避險恐慌",
    )

    tg_report = svc.format_iv_skew_report([metric], channel="telegram")
    assert "<b>NVDA</b>" in tg_report
    assert "EXTREME_TAIL_INVERSION" in tg_report
    assert "25Δ Skew Ratio: <code>1.67</code>" in tg_report
    assert "防禦平移建議: <code>-64 bps</code>" in tg_report

    email_report = svc.format_iv_skew_report([metric], channel="email")
    assert "NVDA" in email_report
    assert "<b>" not in email_report
    assert "`1.67`" in email_report
