"""WP5b: Sentinel emergency protocol is notify-only by default.
WP5b：Sentinel 緊急協議預設只通知、不下單。"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.services.sentinel_service import SentinelService

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make(mode):
    settings = MagicMock()

    def get(key, default=None, user_id=None):
        if key == "sentinel_emergency_protocol_mode":
            if isinstance(mode, Exception):
                raise mode
            return mode if mode is not None else default
        if key == "emergency_liquidation_score":
            return 10
        if key == "auto_hedge_score":
            return 5
        return default

    settings.get_setting.side_effect = get
    with patch("src.services.sentinel_service.SettingsService", return_value=settings):
        svc = SentinelService(user_id="test_user")
    svc.settings_service = settings
    return svc


async def _run(svc, notify_side_effect=None):
    auto = AsyncMock()
    tx = MagicMock()
    tx.get_user_tickers.return_value = ["AAPL", "MSFT"]
    tx.get_holdings_map.return_value = {"AAPL": {"quantity": 10}, "MSFT": {"quantity": 3}}
    notify = AsyncMock(side_effect=notify_side_effect)
    svc._dispatch_notifications_direct = notify
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.transaction_service.TransactionService", return_value=tx), \
         patch("src.services.sentinel_service.logger") as log:
        await svc._trigger_emergency_protocol("user123", "VIX spike panic")
    return auto, notify, log


@pytest.mark.anyio
async def test_notify_mode_places_no_orders_and_notifies_once():
    auto, notify, log = await _run(_make("notify"))
    auto.evaluate_and_execute_trade.assert_not_called()
    assert notify.await_count == 1
    text = " ".join(str(a) for a in notify.await_args.args) + str(notify.await_args.kwargs)
    assert "VIX spike panic" in text
    assert log.warning.called


@pytest.mark.anyio
async def test_notify_mode_notification_failure_still_no_orders():
    auto, notify, log = await _run(_make("notify"), notify_side_effect=RuntimeError("boom"))
    auto.evaluate_and_execute_trade.assert_not_called()
    emitted = [c for c in log.warning.call_args_list + log.error.call_args_list
               if "notif" in str(c).lower()]
    assert emitted


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["bogus", None, "", RuntimeError("db down")])
async def test_unknown_or_unreadable_mode_behaves_as_notify(mode):
    auto, notify, log = await _run(_make(mode))
    auto.evaluate_and_execute_trade.assert_not_called()
    assert notify.await_count == 1


@pytest.mark.anyio
async def test_legacy_mode_keeps_sell_and_hedge():
    auto, notify, log = await _run(_make("legacy"))
    calls = auto.evaluate_and_execute_trade.call_args_list
    sells = [c for c in calls if c.kwargs["action"] == "SELL"]
    assert {c.kwargs["ticker"] for c in sells} == {"AAPL", "MSFT"}
    assert {c.kwargs["quantity"] for c in sells} == {10, 3}
    buy = [c for c in calls if c.kwargs["ticker"] == "SQQQ"]
    assert len(buy) == 1 and buy[0].kwargs["action"] == "BUY" and buy[0].kwargs["quantity"] == 50.0
    assert "strategy_name" not in buy[0].kwargs
    notify.assert_not_called()


def test_schema_default_is_notify():
    schema = yaml.safe_load((ROOT / "config/settings_schema.yaml").read_text())
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("key") == "sentinel_emergency_protocol_mode":
                found.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(schema)
    assert len(found) == 1
    e = found[0]
    assert e["type"] == "enum" and e["enum"] == ["notify", "legacy"] and e["default"] == "notify"
    assert e["label_en"] and e["label_zh"]


@pytest.mark.anyio
async def test_notify_mode_never_logs_the_free_text_rationale():
    """CodeQL py/clear-text-logging-sensitive-data (#165): the rationale is free text and may carry a token."""
    svc = _make("notify")
    auto = AsyncMock()
    svc._dispatch_notifications_direct = AsyncMock()
    secret = "Bearer abcdefghijklmnop1234567890"
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.sentinel_service.logger") as log:
        await svc._trigger_emergency_protocol("user123", f"VIX spike; Authorization: {secret}")
    logged = " ".join(str(c) for c in log.warning.call_args_list)
    assert "abcdefghijklmnop1234567890" not in logged
    assert "VIX spike" not in logged        # free text is not logged at all (CodeQL does not treat redact_secrets as a sanitizer)
    assert "NO orders placed" in logged     # the fact of the emergency and the no-order outcome still are
