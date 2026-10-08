"""
Unit Tests for BreakoutFilterService
====================================
測試盤中量價異動偵測、假突破過濾、VWAP 乖離率與上影線抑制機制。
"""

import pytest
from unittest.mock import MagicMock
from src.services.breakout_filter_service import BreakoutFilterService, BreakoutFilterResult


@pytest.fixture
def sample_ohlcv():
    """模擬 25 天標準 OHLCV 數據，日均量約 10,000 股。"""
    days = 25
    return {
        "date": [f"2026-09-{i+1:02d}" for i in range(days)],
        "open": [100.0 + i * 0.5 for i in range(days)],
        "high": [102.0 + i * 0.5 for i in range(days)],
        "low": [99.0 + i * 0.5 for i in range(days)],
        "close": [101.5 + i * 0.5 for i in range(days)],
        "volume": [10000.0] * days,
    }


def test_breakout_filter_disabled(sample_ohlcv):
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: False if k == "enable_breakout_volume_filter" else d

    svc = BreakoutFilterService(settings_service=mock_settings)
    res = svc.evaluate_breakout_quality("NVDA", current_price=115.0, ohlcv_data=sample_ohlcv)

    assert res.is_valid_breakout is True
    assert res.metrics.get("filter_disabled") is True


def test_breakout_filter_passes_valid_breakout(sample_ohlcv):
    # 放量 1.5x (15,000 > 10,000)，價格高於 VWAP 且未大幅乖離，上影線短
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: d

    sample_ohlcv["volume"][-1] = 16000.0  # 1.6x ADV20
    sample_ohlcv["high"][-1] = 114.0
    sample_ohlcv["close"][-1] = 113.8  # 近乎最高點收盤，幾乎無上影線
    sample_ohlcv["low"][-1] = 111.0
    sample_ohlcv["open"][-1] = 111.5

    svc = BreakoutFilterService(settings_service=mock_settings)
    res = svc.evaluate_breakout_quality("NVDA", current_price=113.8, ohlcv_data=sample_ohlcv)

    assert res.is_valid_breakout is True
    assert res.rejection_reason is None
    assert res.volume_ratio >= 1.5
    assert res.confidence_penalty == 0.0


def test_breakout_filter_rejects_low_volume_divergence(sample_ohlcv):
    # 量價背離：突破創高但成交量萎縮至 5,000 股 (0.5x ADV20 < 0.7x)
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: d

    sample_ohlcv["volume"][-1] = 4500.0
    sample_ohlcv["high"][-1] = 116.0
    sample_ohlcv["close"][-1] = 115.5

    svc = BreakoutFilterService(settings_service=mock_settings)
    res = svc.evaluate_breakout_quality("NVDA", current_price=115.5, ohlcv_data=sample_ohlcv)

    assert res.is_valid_breakout is False
    assert "成交量萎縮" in res.rejection_reason
    assert res.volume_ratio < 0.70
    assert res.confidence_penalty > 0.0


def test_breakout_filter_rejects_vwap_breakdown(sample_ohlcv):
    # 價格大幅跌破 VWAP
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: d

    svc = BreakoutFilterService(settings_service=mock_settings)
    # 顯式傳入遠低於 VWAP 的現價與 realtime_vwap
    res = svc.evaluate_breakout_quality(
        "NVDA",
        current_price=95.0,
        ohlcv_data=sample_ohlcv,
        realtime_vwap=105.0,  # 現價 95.0 遠低於 VWAP 105.0 (-9.5%)
    )

    assert res.is_valid_breakout is False
    assert "低於短線基準 VWAP" in res.rejection_reason


def test_breakout_filter_rejects_overextended_vwap(sample_ohlcv):
    # 現價過度偏離 VWAP 超過 +6.0% (超買衰竭)
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: d

    svc = BreakoutFilterService(settings_service=mock_settings)
    res = svc.evaluate_breakout_quality(
        "NVDA",
        current_price=120.0,
        ohlcv_data=sample_ohlcv,
        realtime_vwap=108.0,  # 偏離 ((120-108)/108)*100 = +11.1% > +6.0%
    )

    assert res.is_valid_breakout is False
    assert "正乖離率" in res.rejection_reason


def test_breakout_filter_rejects_pin_bar_upper_shadow(sample_ohlcv):
    # 墓碑線 / 長上影線假突破：高點 120.0，開盤 110.0，收盤 111.0，低點 109.5
    # 振幅 120.0 - 109.5 = 10.5；上影線 120.0 - 111.0 = 9.0 (85.7% > 40%)
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d, u=None: d

    sample_ohlcv["open"][-1] = 110.0
    sample_ohlcv["high"][-1] = 120.0
    sample_ohlcv["low"][-1] = 109.5
    sample_ohlcv["close"][-1] = 111.0
    sample_ohlcv["volume"][-1] = 15000.0

    svc = BreakoutFilterService(settings_service=mock_settings)
    res = svc.evaluate_breakout_quality("NVDA", current_price=111.0, ohlcv_data=sample_ohlcv)

    assert res.is_valid_breakout is False
    assert "上影線" in res.rejection_reason
    assert res.upper_shadow_ratio > 0.40


def test_evaluate_tick_anomaly():
    svc = BreakoutFilterService()
    # 測試小單無異動
    res1 = svc.evaluate_tick_anomaly("AAPL", price=150.0, size=10, last_price=150.0, adv20=100000)
    assert res1["is_large_block"] is False
    assert res1["anomaly_detected"] is False

    # 測試大單 (Block trade: 1000 shares >= 100000 * 0.005 = 500)
    res2 = svc.evaluate_tick_anomaly("AAPL", price=150.5, size=800, last_price=150.0, adv20=100000)
    assert res2["is_large_block"] is True
    assert res2["anomaly_detected"] is True

    # 測試單筆劇烈價格跳動 (2.0% > 1.5%)
    res3 = svc.evaluate_tick_anomaly("AAPL", price=153.0, size=50, last_price=150.0, adv20=100000)
    assert res3["move_pct"] == 2.0
    assert res3["anomaly_detected"] is True
