"""One protection alert per (rule, ticker) per window — not one email per evaluation.

Every time check() returned a reason it fired a notify_all email. Capital-rotation screening alone evaluates every
candidate every 30 minutes, so a single cooled-down ticker produced ~48 identical "個股冷卻" emails a day.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import trading_protections_service as tp
from src.services.trading_protections_service import TradingProtectionsService


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = (value, ex)
        return True


@pytest.fixture
def svc():
    s = TradingProtectionsService.__new__(TradingProtectionsService)
    s.user_id = "u1"
    s._cfg = dict(tp._SETTING_DEFAULTS)
    return s


async def _dispatch_n(svc, n, ticker="MSFT", reason="MSFT cooldown: last resolved BUY decision lost -2.0% alpha 1d ago"):
    hub = MagicMock()
    hub.dispatch_protection_breached_alert = AsyncMock(return_value={})
    with patch("src.services.actionable_alert_service.ActionableAlertHubService", return_value=hub):
        for _ in range(n):
            svc._dispatch_protection_alert_safely(reason, ticker)
        await asyncio.sleep(0)  # let the scheduled tasks run
        await asyncio.sleep(0)
    return hub.dispatch_protection_breached_alert.await_count


@pytest.mark.asyncio
async def test_repeated_hits_for_the_same_rule_and_ticker_send_one_alert(svc):
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=_FakeRedis()):
        assert await _dispatch_n(svc, 50) == 1


@pytest.mark.asyncio
async def test_the_changing_day_count_in_the_reason_does_not_defeat_the_dedupe(svc):
    hub = MagicMock()
    hub.dispatch_protection_breached_alert = AsyncMock(return_value={})
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=_FakeRedis()), \
         patch("src.services.actionable_alert_service.ActionableAlertHubService", return_value=hub):
        for d in range(5):
            svc._dispatch_protection_alert_safely(f"MSFT cooldown: lost -2.0% alpha {d}d ago (cooldown 3d)", "MSFT")
        await asyncio.sleep(0); await asyncio.sleep(0)
    assert hub.dispatch_protection_breached_alert.await_count == 1


@pytest.mark.asyncio
async def test_a_different_ticker_or_rule_still_alerts(svc):
    hub = MagicMock()
    hub.dispatch_protection_breached_alert = AsyncMock(return_value={})
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=_FakeRedis()), \
         patch("src.services.actionable_alert_service.ActionableAlertHubService", return_value=hub):
        svc._dispatch_protection_alert_safely("MSFT cooldown: x", "MSFT")
        svc._dispatch_protection_alert_safely("AAPL cooldown: x", "AAPL")
        svc._dispatch_protection_alert_safely("Consecutive-loss lockout: x", "MSFT")
        await asyncio.sleep(0); await asyncio.sleep(0)
    assert hub.dispatch_protection_breached_alert.await_count == 3


@pytest.mark.asyncio
async def test_window_comes_from_the_setting_and_is_used_as_the_ttl(svc):
    svc._cfg["protection_alert_dedupe_hours"] = 6.0
    r = _FakeRedis()
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=r):
        await _dispatch_n(svc, 1)
    assert [v[1] for v in r.store.values()] == [6 * 3600]


@pytest.mark.asyncio
async def test_redis_outage_falls_back_to_an_in_process_window_instead_of_spamming(svc):
    tp._LOCAL_ALERT_SEEN.clear()
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", side_effect=RuntimeError("redis down")):
        assert await _dispatch_n(svc, 10, ticker="NVDA") == 1


def test_screening_calls_can_opt_out_of_alerts(svc):
    """check(..., notify=False) is a pure query: no alert even when a rule fires."""
    with patch.object(TradingProtectionsService, "_check_flip_flop_lockout", return_value=None), \
         patch.object(TradingProtectionsService, "_check_max_drawdown", return_value=None), \
         patch.object(TradingProtectionsService, "_check_ticker_cooldown", return_value="MSFT cooldown: x"), \
         patch.object(TradingProtectionsService, "_dispatch_protection_alert_safely") as disp:
        assert svc.check("MSFT", "BUY", notify=False) == "MSFT cooldown: x"
        disp.assert_not_called()
        assert svc.check("MSFT", "BUY") == "MSFT cooldown: x"          # default still alerts
        disp.assert_called_once()


def test_capital_rotation_candidate_screening_does_not_notify():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3].joinpath("src/services/sentinel_service.py").read_text(encoding="utf-8")
    m = re.search(r'protections_svc\.check\(ticker=cand_ticker[^)]*\)', src)
    assert m and "notify=False" in m.group(0), "rotation candidate screening must not email per candidate per tick"


def test_no_running_loop_does_not_consume_the_dedupe_window(svc):
    """Sync context: nothing is sent, so the window must stay open for the next (async) evaluation."""
    r = _FakeRedis()
    with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=r):
        svc._dispatch_protection_alert_safely("MSFT cooldown: x", "MSFT")   # no loop running here
    assert r.store == {}
