"""
Unit tests for MicrostructureOrderFlowImbalanceService (Phase 61B).
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.services.microstructure_order_flow_imbalance_service import (
    MicrostructureOrderFlowImbalanceService,
    OFITickerMetric,
)


@pytest.fixture
def mock_settings_service():
    svc = MagicMock()
    svc.get_setting = AsyncMock(side_effect=lambda key, default=None: default)
    return svc


@pytest.mark.asyncio
async def test_ofi_metric_serialization():
    metric = OFITickerMetric(
        ticker="NVDA",
        regime="BUY_PRESSURE_ACCUMULATION",
        best_bid=125.00,
        best_ask=125.04,
        spread_usd=0.04,
        spread_ratio=1.0,
        ofi_value=2500.0,
        ofi_ratio=0.65,
        bid_depth=3500.0,
        ask_depth=1000.0,
        is_vacuum_frozen=False,
        recommended_action="AGGRESSIVE_FILL",
        freeze_remaining_seconds=0,
        rationale="買方主動吃單抬價",
    )
    d = metric.to_dict()
    assert d["ticker"] == "NVDA"
    assert d["regime"] == "BUY_PRESSURE_ACCUMULATION"
    assert d["ofi_ratio"] == 0.65
    assert d["recommended_action"] == "AGGRESSIVE_FILL"

    restored = OFITickerMetric.from_dict(d)
    assert restored.ticker == "NVDA"
    assert restored.ofi_ratio == 0.65
    assert restored.is_vacuum_frozen is False


@pytest.mark.asyncio
async def test_cont_et_al_ofi_calculation(mock_settings_service):
    svc = MicrostructureOrderFlowImbalanceService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Cont et al. sequence:
    # t0: Bid 100.00 (sz 100), Ask 100.10 (sz 100)
    # t1: Bid 100.00 (sz 150 -> delta_b = +50), Ask 100.10 (sz 100 -> delta_a = 0) => OFI = 50
    # t2: Bid 100.05 (sz 120 -> pb > pb_prev -> delta_b = 120), Ask 100.10 (sz 80 -> pa == pa_prev -> delta_a = -20) => OFI = 140
    history = [
        {"bid": 100.00, "bid_size": 100, "ask": 100.10, "ask_size": 100},
        {"bid": 100.00, "bid_size": 150, "ask": 100.10, "ask_size": 100},
        {"bid": 100.05, "bid_size": 120, "ask": 100.10, "ask_size": 80},
    ]
    cum_ofi, ofi_ratio = svc._calculate_ofi_from_history(history)
    assert cum_ofi == pytest.approx(190.0, abs=1e-2)
    assert ofi_ratio > 0.45


@pytest.mark.asyncio
async def test_spread_shock_triggers_vacuum_freeze(mock_settings_service):
    svc = MicrostructureOrderFlowImbalanceService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Median spread 0.04, current quote spread is 0.20 (5.0x expansion >= 2.5x shock threshold)
    quote = {
        "bid": 124.80,
        "ask": 125.00,
        "bid_size": 100.0,
        "ask_size": 80.0,
        "median_spread": 0.04,
    }
    metric = await svc.evaluate_order_flow_imbalance("NVDA", current_quote=quote)
    assert metric.regime == "LIQUIDITY_VACUUM_FREEZE"
    assert metric.is_vacuum_frozen is True
    assert metric.recommended_action == "BLOCK_AND_COOLDOWN"
    assert metric.spread_ratio == pytest.approx(5.0, abs=1e-2)


@pytest.mark.asyncio
async def test_sell_pressure_drain_regime(mock_settings_service):
    svc = MicrostructureOrderFlowImbalanceService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    # Heavy ask depth vs minimal bid depth -> negative OFI ratio < -0.45
    quote = {
        "bid": 100.00,
        "ask": 100.04,
        "bid_size": 100.0,
        "ask_size": 900.0,
        "median_spread": 0.04,
    }
    metric = await svc.evaluate_order_flow_imbalance("TSM", current_quote=quote)
    assert metric.regime == "SELL_PRESSURE_DRAIN"
    assert metric.recommended_action == "DEFENSIVE_DRIFT"
    assert metric.ofi_ratio < -0.45


@pytest.mark.asyncio
async def test_format_ofi_report(mock_settings_service):
    svc = MicrostructureOrderFlowImbalanceService(
        user_id="test_user",
        settings_service=mock_settings_service,
    )
    metric = OFITickerMetric(
        ticker="NVDA",
        regime="LIQUIDITY_VACUUM_FREEZE",
        best_bid=124.80,
        best_ask=125.00,
        spread_usd=0.20,
        spread_ratio=5.0,
        ofi_value=-500.0,
        ofi_ratio=-0.65,
        bid_depth=100.0,
        ask_depth=80.0,
        is_vacuum_frozen=True,
        recommended_action="BLOCK_AND_COOLDOWN",
        freeze_remaining_seconds=115,
        rationale="做市商流動性真空防禦中",
    )

    tg_report = svc.format_ofi_report([metric], channel="telegram")
    assert "<b>NVDA</b>" in tg_report
    assert "LIQUIDITY_VACUUM_FREEZE" in tg_report
    assert "Spread $0.200 | <code>5.0x</code>" in tg_report
    assert "流動性真空冷凍進行中" in tg_report

    email_report = svc.format_ofi_report([metric], channel="email")
    assert "NVDA" in email_report
    assert "<b>" not in email_report
