"""
Unit Tests for VixPanicReboundStrategy
======================================
驗證 VIX 極端恐慌逆勢抄底策略 (別人恐懼我貪婪) 之金字塔分批建倉與退場邏輯。
"""
import pytest
from src.services.vix_panic_rebound_strategy import (
    VixPanicReboundStrategy,
    VixPanicAction,
    VixPanicSignal,
)


def test_vix_idle_when_below_35():
    # VIX 22.0 < 35.0 -> IDLE
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=22.0, current_stage=0)
    assert sig.action == VixPanicAction.IDLE
    assert sig.current_stage == 0
    assert sig.recommended_leverage == 1
    assert sig.target_cumulative_weight == 0.0


def test_vix_stage1_spot_entry():
    # VIX 36.5 in [35, 40) -> BUY_STAGE1, 30% weight, 1.0x spot
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=36.5, current_stage=0)
    assert sig.action == VixPanicAction.BUY_STAGE1
    assert sig.current_stage == 1
    assert sig.incremental_weight == 0.30
    assert sig.target_cumulative_weight == 0.30
    assert sig.recommended_leverage == 1  # 現貨 X1，防早期流動性黑天鵝爆倉
    assert sig.is_trailing_stop_loss is True
    assert sig.stop_loss_pct == 8.0


def test_vix_stage2_leverage_entry():
    # Stage 1 position held, VIX crosses 41.0 >= 40.0 -> BUY_STAGE2, 30% weight, 2.0x leverage
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=41.0, current_stage=1)
    assert sig.action == VixPanicAction.BUY_STAGE2
    assert sig.current_stage == 2
    assert sig.incremental_weight == 0.30
    assert sig.target_cumulative_weight == 0.60
    assert sig.recommended_leverage == 2  # 開啟受控 X2 槓桿
    assert sig.is_trailing_stop_loss is True
    assert sig.stop_loss_pct == 5.0


def test_vix_stage3_peak_entry():
    # Stage 2 position held, VIX crosses 46.5 >= 45.0 -> BUY_STAGE3, 40% weight, 2.0x leverage
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=46.5, current_stage=2)
    assert sig.action == VixPanicAction.BUY_STAGE3
    assert sig.current_stage == 3
    assert sig.incremental_weight == 0.40
    assert sig.target_cumulative_weight == 1.00
    assert sig.recommended_leverage == 2
    assert sig.is_trailing_stop_loss is True
    assert sig.stop_loss_pct == 5.5


def test_vix_stage3_peaking_signal_entry():
    # VIX was >= 40, now curves down below 5-day MA -> BUY_STAGE3
    # 5-day MA of [44, 43, 42, 41, 39] is 41.8. Current VIX is 39.5 < 41.8.
    vix_history = [35.0, 38.0, 42.0, 44.0, 43.0, 42.0, 41.0, 39.0]
    sig = VixPanicReboundStrategy.evaluate_signal(
        current_vix=39.5,
        current_stage=2,
        vix_history=vix_history,
    )
    assert sig.action == VixPanicAction.BUY_STAGE3
    assert sig.current_stage == 3
    assert sig.recommended_leverage == 2
    assert "crossed below 5MA" in sig.reason


def test_vix_partial_exit_and_deleverage():
    # Holding stage 3 position, VIX subsides to 24.2 <= 25.0 -> PARTIAL_EXIT_DELEVERAGE
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=24.2, current_stage=3)
    assert sig.action == VixPanicAction.PARTIAL_EXIT_DELEVERAGE
    assert sig.incremental_weight == 0.50
    assert sig.recommended_leverage == 1  # 降回現貨 X1，終止 8.5% 融資利息
    assert "Close 50% to lock in profit" in sig.reason


def test_vix_full_exit_when_market_normalizes():
    # Holding stage 1 position, VIX drops to 19.5 <= 20.0 -> FULL_EXIT
    sig = VixPanicReboundStrategy.evaluate_signal(current_vix=19.5, current_stage=1)
    assert sig.action == VixPanicAction.FULL_EXIT
    assert sig.current_stage == 0
    assert sig.target_cumulative_weight == 0.0
    assert "Market normalized" in sig.reason


def test_vix_profit_ratchet_exit():
    # Trade profit hits +26% >= +25% -> FULL_EXIT
    sig = VixPanicReboundStrategy.evaluate_signal(
        current_vix=28.0,
        current_stage=2,
        current_pnl_pct=0.26,
    )
    assert sig.action == VixPanicAction.FULL_EXIT
    assert sig.current_stage == 0
    assert "Target profit reached" in sig.reason


def test_vix_trailing_stop_loss_trigger():
    # High-water mark drawdown reaches -7.0% <= -6.0% -> STOP_LOSS
    sig = VixPanicReboundStrategy.evaluate_signal(
        current_vix=42.0,
        current_stage=2,
        drawdown_from_hwm=-0.07,
    )
    assert sig.action == VixPanicAction.STOP_LOSS
    assert sig.current_stage == 0
    assert "High-water mark trailing stop triggered" in sig.reason


def test_vix_hard_circuit_breaker():
    # Underlying loss reaches -16% <= -15% -> Hard STOP_LOSS
    sig = VixPanicReboundStrategy.evaluate_signal(
        current_vix=48.0,
        current_stage=3,
        current_pnl_pct=-0.16,
    )
    assert sig.action == VixPanicAction.STOP_LOSS
    assert sig.current_stage == 0
    assert "Hard stop-loss triggered" in sig.reason
