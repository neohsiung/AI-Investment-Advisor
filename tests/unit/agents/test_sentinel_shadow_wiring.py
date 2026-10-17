"""WP5: shadow proposal recording is wired before the executor and never changes the executor call.
WP5：shadow 提案紀錄接在執行器之前，且絕不改變執行器的呼叫內容。"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import yaml

from src.services.sentinel_service import SentinelService

ROOT = Path(__file__).resolve().parents[3]

SIGNALS = [
    {"ticker": "AAPL", "action": "BUY", "quantity": 2.5, "score": 8, "intent": "auto", "reason": "r1"},
    {"ticker": "MSFT", "action": "SELL", "quantity": 1.0, "score": 6, "intent": "trim", "reason": "r2"},
]
EXPECTED = [
    call(user_id="u1", ticker="AAPL", action="BUY", quantity=2.5, confidence_score=8, rationale="r1"),
    call(user_id="u1", ticker="MSFT", action="SELL", quantity=1.0, confidence_score=6, rationale="r2"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make(mode):
    settings = MagicMock()

    def get(key, default=None, user_id=None):
        if key == "trade_proposal_mode":
            if isinstance(mode, Exception):
                raise mode
            return mode if mode is not None else default
        return default

    settings.get_setting.side_effect = get
    with patch("src.services.sentinel_service.SettingsService", return_value=settings):
        svc = SentinelService(user_id="u1")
    svc.settings_service = settings
    return svc


async def _run(mode, shadow, signals=None):
    svc = _make(mode)
    auto = AsyncMock()
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.proposal_shadow_service.record_shadow_proposals", shadow), \
         patch("src.services.proposal_shadow_service.logger") as slog, \
         patch("src.services.sentinel_service.logger") as log:
        await svc._execute_trade_signals("u1", signals if signals is not None else [dict(s) for s in SIGNALS], "sentinel")
    return auto, slog, log


@pytest.mark.anyio
async def test_baseline_executor_args_and_shadow_called_before_executor():
    order = []
    shadow = AsyncMock(side_effect=lambda *a, **k: order.append("shadow"))
    auto = AsyncMock(side_effect=lambda **k: order.append("exec"))
    svc = _make("shadow")
    with patch("src.services.automated_trading_service.AutomatedTradingService", return_value=auto), \
         patch("src.services.proposal_shadow_service.record_shadow_proposals", shadow):
        auto.evaluate_and_execute_trade = AsyncMock(side_effect=lambda **k: order.append("exec"))
        await svc._execute_trade_signals("u1", [dict(s) for s in SIGNALS], "sentinel")
    assert order == ["shadow", "exec", "exec"]
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED
    assert shadow.await_args.args[:3] == ("u1", SIGNALS, "sentinel")


@pytest.mark.anyio
async def test_executor_args_identical_when_shadow_approves():
    auto, _, _ = await _run("shadow", AsyncMock(return_value=None))
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED


@pytest.mark.anyio
async def test_executor_args_identical_when_shadow_rejects_everything():
    async def rejecting(user_id, signals, source, **kw):
        return [{"status": "rejected", "reason": "gateway_blocked"} for _ in signals]

    auto, _, _ = await _run("shadow", rejecting)
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED


@pytest.mark.anyio
async def test_executor_args_identical_when_shadow_raises_and_warning_is_logged():
    auto, _, log = await _run("shadow", AsyncMock(side_effect=RuntimeError("shadow exploded")))
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED
    assert any("shadow exploded" in str(c) for c in log.warning.call_args_list)


@pytest.mark.anyio
async def test_executor_args_identical_when_shadow_times_out():
    async def hangs(*a, **k):
        await asyncio.sleep(30)

    with patch("src.services.sentinel_service.SHADOW_PROPOSAL_TIMEOUT_S", 0.05):
        auto, _, log = await _run("shadow", hangs)
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED
    assert log.warning.called


@pytest.mark.anyio
async def test_shadow_receives_copies_so_it_cannot_alter_executor_args():
    async def mutating(user_id, signals, source, **kw):
        for s in signals:
            s["quantity"] = 999
            s.pop("score", None)
        signals.clear()

    auto, _, _ = await _run("shadow", mutating)
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED


@pytest.mark.anyio
async def test_mode_off_does_not_call_shadow_but_executor_still_runs():
    shadow = AsyncMock()
    auto, _, _ = await _run("off", shadow)
    shadow.assert_not_called()
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["enforce", "bogus", "", None, RuntimeError("settings down")])
async def test_enforce_unknown_or_unreadable_behaves_as_shadow_with_warning(mode):
    shadow = AsyncMock()
    auto, slog, _ = await _run(mode, shadow)
    assert shadow.await_count == 1
    assert slog.warning.called
    assert auto.evaluate_and_execute_trade.call_args_list == EXPECTED


@pytest.mark.anyio
async def test_enforce_warning_names_enforce():
    _, slog, _ = await _run("enforce", AsyncMock())
    assert any("enforce" in str(c).lower() for c in slog.warning.call_args_list)


def test_setting_declared_in_schema_with_quoted_enum_and_safe_default():
    schema = yaml.safe_load((ROOT / "config" / "settings_schema.yaml").read_text(encoding="utf-8"))
    rows = schema["settings"] if isinstance(schema, dict) and "settings" in schema else schema
    (item,) = [s for s in rows if s.get("key") == "trade_proposal_mode"]
    assert item["enum"] == ["off", "shadow", "enforce"]
    assert all(isinstance(v, str) for v in item["enum"])
    assert item["default"] == "shadow" and item["danger"] is True
    for k in ("label_en", "label_zh", "help_en", "help_zh"):
        assert item.get(k)
