"""
Unit Tests for SmartMoneySupportService and Institutional Trailing Stop Engine
==============================================================================
"""
import pytest
from unittest.mock import MagicMock
from src.services.smart_money_support_service import (
    SmartMoneySupportService,
    SmartMoneySupportResult,
)
from src.services.exit_compositor_service import (
    compute_dynamic_atr_exit,
    DynamicAtrExitResult,
)


def _generate_synthetic_ohlcv(base_price=100.0, trend="up", days=30):
    dates = [f"2026-08-{i+1:02d}" for i in range(days)]
    highs = []
    lows = []
    closes = []
    volumes = []

    price = base_price
    for i in range(days):
        if trend == "up":
            # Dip at day 5, then rally with high volume at day 15
            if i == 5:
                low = base_price - 15.0  # Definitive swing low of the period
                high = price + 1.0
                close = price - 2.0
                vol = 500_000.0
            elif i == 15:
                low = price - 1.0
                high = price + 8.0
                close = price + 6.0
                vol = 2_000_000.0  # Massive volume day (Institutional accumulation)
            else:
                low = price - 1.0
                high = price + 2.0
                close = price + 1.0
                vol = 800_000.0
        else:
            low = price - 2.0
            high = price + 1.0
            close = price - 1.0
            vol = 600_000.0

        price = close
        highs.append(round(high, 2))
        lows.append(round(low, 2))
        closes.append(round(close, 2))
        volumes.append(vol)

    return {
        "date": dates,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }


class TestSmartMoneySupportService:

    def test_calculate_anchored_vwap_auto_anchor_at_swing_low(self):
        svc = SmartMoneySupportService()
        ohlcv = _generate_synthetic_ohlcv(base_price=100.0, trend="up", days=20)
        
        avwap, anchor_idx, anchor_date = svc.calculate_anchored_vwap(
            dates=ohlcv["date"],
            highs=ohlcv["high"],
            lows=ohlcv["low"],
            closes=ohlcv["close"],
            volumes=ohlcv["volume"],
        )

        # Day 5 had the lowest low in our synthetic series (base_price - 15.0)
        assert anchor_idx == 5
        assert anchor_date == ohlcv["date"][5]
        assert avwap > ohlcv["low"][5]
        assert avwap < ohlcv["high"][-1]

    def test_calculate_volume_profile_poc_identification(self):
        svc = SmartMoneySupportService()
        ohlcv = _generate_synthetic_ohlcv(base_price=100.0, trend="up", days=25)

        vp = svc.calculate_volume_profile(
            highs=ohlcv["high"],
            lows=ohlcv["low"],
            closes=ohlcv["close"],
            volumes=ohlcv["volume"],
            bins=30,
        )

        poc = vp["poc"]
        val = vp["val"]
        vah = vp["vah"]

        assert poc > 0
        assert val <= poc <= vah
        assert "hvns" in vp
        assert len(vp["hvns"]) >= 1

    def test_calculate_institutional_support_bullish(self):
        svc = SmartMoneySupportService()
        ohlcv = _generate_synthetic_ohlcv(base_price=100.0, trend="up", days=10)
        curr_price = ohlcv["close"][-1]

        res = svc.calculate_institutional_support(
            ticker="NVDA",
            current_price=curr_price,
            days=10,
            ohlcv_data=ohlcv,
        )

        assert isinstance(res, SmartMoneySupportResult)
        assert res.ticker == "NVDA"
        assert res.current_price == curr_price
        assert res.key_support_price > 0
        assert res.recommended_stop_loss < curr_price
        # Check min pip constraint (at least 1.5% below current price)
        assert res.stop_loss_distance_pct >= 1.5
        # Check max risk cap (not more than 10%)
        assert res.stop_loss_distance_pct <= 10.0

    def test_calculate_institutional_support_insufficient_history_fallback(self):
        svc = SmartMoneySupportService()
        short_ohlcv = {
            "date": ["2026-08-01", "2026-08-02"],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 2000],
        }

        res = svc.calculate_institutional_support(
            ticker="TSLA",
            current_price=102.0,
            ohlcv_data=short_ohlcv,
        )

        assert res.support_type == "FALLBACK_PERCENTAGE"
        assert res.stop_loss_distance_pct == 6.0
        assert round(res.recommended_stop_loss, 2) == round(102.0 * 0.94, 2)


class TestExitCompositorInstitutionalRatchet:

    def test_dynamic_atr_exit_anchored_by_institutional_support(self):
        # Entry at 100, current price at 110 (+10%), ATR = 2.0
        # Normal ATR initial stop would be 100 - 2.0*2.0 = 96.0
        # Breakeven stop at +10% peak is 100 * 1.005 = 100.5
        # If institutional support is at 106.0:
        # Support stop = 106.0 * 0.992 = 105.152 > 100.5 (ratchets up to lock in profit!)
        res = compute_dynamic_atr_exit(
            entry_price=100.0,
            current_price=110.0,
            highest_price=110.0,
            atr=2.0,
            institutional_support_price=106.0,
        )

        assert res.should_exit is False
        assert res.exit_type == "HOLD"
        assert res.stop_price > 100.5  # Higher than breakeven
        assert res.stop_price == round(106.0 * 0.992, 4)
        assert res.ratchet_stage in ("SUPPORT_LOCKED", "BREAKEVEN")

    def test_dynamic_atr_exit_triggers_when_falling_below_support(self):
        # Current price drops to 104 <= support stop 105.152
        res = compute_dynamic_atr_exit(
            entry_price=100.0,
            current_price=104.0,
            highest_price=110.0,
            atr=2.0,
            institutional_support_price=106.0,
        )

        assert res.should_exit is True
        assert res.exit_type in ("TRAILING_PROFIT", "STOP_LOSS")
        assert res.stop_price >= 105.0
