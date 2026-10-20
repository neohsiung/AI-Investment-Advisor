"""
L7: GEX and Kalman pairs guards must never emit plausible numbers from fabricated data.
L7：GEX 與 Kalman 配對護欄不得以捏造資料產生看似真實的數字。
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from src.services.kalman_pairs_cointegration_service import (
    KalmanPairsCointegrationService,
    KalmanPairsMetric,
)
from src.services.option_gamma_exposure_gex_service import (
    GEXExposureMetric,
    OptionGammaExposureGEXService,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _gex_service(market_data=None):
    # spec=[] -> no attributes at all, i.e. a provider without get_options_chain
    return OptionGammaExposureGEXService(
        user_id="u1",
        settings_service=MagicMock(),
        market_data_service=market_data if market_data is not None else MagicMock(spec=[]),
    )


@pytest.mark.asyncio
async def test_gex_no_chain_provider_is_marked_and_has_no_regime_or_numbers():
    svc = _gex_service()
    for price in (50.0, 100.0, 135.0, 230.0, 580.0):
        m = await svc.evaluate_ticker_gex("NVDA", spot_price=price)
        assert m.fallback_reason == "no_options_chain_provider"
        assert m.regime != OptionGammaExposureGEXService.REGIME_POSITIVE_GAMMA
        assert m.regime == OptionGammaExposureGEXService.REGIME_UNAVAILABLE
        assert m.net_gex == 0.0 and m.requires_protection is False
        assert "POSITIVE_GAMMA_STICKY" not in json.dumps(m.to_dict())


@pytest.mark.asyncio
async def test_gex_provider_failure_is_marked_not_swallowed():
    md = MagicMock()
    md.get_options_chain = MagicMock(side_effect=RuntimeError("boom"))

    async def _raise(_t):
        raise RuntimeError("boom")

    md.get_options_chain = _raise
    m = await _gex_service(md).evaluate_ticker_gex("NVDA", spot_price=100.0)
    assert m.fallback_reason == "no_options_chain_provider"


@pytest.mark.asyncio
async def test_gex_real_chain_is_measured_without_fallback():
    chain = []
    for stk in (90.0, 95.0, 100.0, 105.0, 110.0):
        chain.append({"type": "CALL", "strike": stk, "open_interest": 1000.0, "implied_volatility": 0.3, "days_to_expiry": 14})
        chain.append({"type": "PUT", "strike": stk, "open_interest": 1000.0, "implied_volatility": 0.3, "days_to_expiry": 14})
    md = MagicMock()

    async def _chain(_t):
        return chain

    md.get_options_chain = _chain
    m = await _gex_service(md).evaluate_ticker_gex("NVDA", spot_price=100.0)
    assert m.fallback_reason is None
    assert m.regime != OptionGammaExposureGEXService.REGIME_UNAVAILABLE


def test_gex_fallback_reason_round_trips_and_report_claims_no_regime():
    m = GEXExposureMetric.from_dict(
        {"ticker": "X", "regime": "UNAVAILABLE_NO_OPTIONS_CHAIN", "fallback_reason": "no_options_chain_provider"}
    )
    assert m.fallback_reason == "no_options_chain_provider"
    assert m.to_dict()["fallback_reason"] == "no_options_chain_provider"
    report = _gex_service().format_gex_report(m)
    assert "不適用" in report and "正伽馬" not in report


def test_gex_default_is_off_in_schema_and_service():
    schema = yaml.safe_load((REPO_ROOT / "config/settings_schema.yaml").read_text())
    entries = schema["settings"] if isinstance(schema, dict) and "settings" in schema else schema
    entry = next(e for e in entries if e.get("key") == "enable_option_gamma_exposure_gex")
    assert entry["default"] is False
    svc = OptionGammaExposureGEXService(user_id="u1", settings_service=None, market_data_service=MagicMock(spec=[]))
    assert asyncio.run(svc.is_enabled()) is False


_SERIES_SCRIPT = """
import asyncio, json
from unittest.mock import MagicMock
from src.services.kalman_pairs_cointegration_service import KalmanPairsCointegrationService
svc = KalmanPairsCointegrationService(user_id="u1", settings_service=MagicMock(), market_data_service=MagicMock(spec=[]))
async def _no_redis():
    return None
svc._get_redis = _no_redis
y, x, synth = asyncio.run(svc.get_price_series_pair("NVDA", "AMD"))
print(json.dumps([y, x, synth]))
"""


def _series_in_new_process(hashseed: str):
    out = subprocess.run(
        [sys.executable, "-c", _SERIES_SCRIPT],
        capture_output=True, text=True, cwd=REPO_ROOT, check=True,
        env={**__import__("os").environ, "PYTHONHASHSEED": hashseed},
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_kalman_series_is_identical_across_processes():
    a = _series_in_new_process("1")
    b = _series_in_new_process("2")
    assert a == b
    assert a[2] is True


@pytest.mark.asyncio
async def test_kalman_synthetic_series_is_marked_and_never_trips_breaker():
    svc = KalmanPairsCointegrationService(
        user_id="u1", settings_service=MagicMock(), market_data_service=MagicMock(spec=[])
    )

    async def _no_redis():
        return None

    svc._get_redis = _no_redis
    m = await svc.evaluate_pairs_cointegration("NVDA", "AMD")
    assert m.fallback_reason == "synthetic_series"
    assert m.requires_circuit_breaker is False
    assert KalmanPairsMetric.from_dict(m.to_dict()).fallback_reason == "synthetic_series"
    assert "不適用" in svc.format_pairs_report(m)


@pytest.mark.asyncio
async def test_kalman_real_history_is_not_marked():
    hist = [100.0 + i * 0.1 + (0.3 if i % 2 else -0.3) for i in range(40)]
    md = MagicMock()

    async def _h(_t, days=60):
        return list(hist)

    md.get_historical_prices = _h
    svc = KalmanPairsCointegrationService(user_id="u1", settings_service=MagicMock(), market_data_service=md)
    m = await svc.evaluate_pairs_cointegration("NVDA", "AMD")
    assert m.fallback_reason is None
