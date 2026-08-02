"""
Regression tests for fail-closed trading guards.
測試風控例外時改為 fail-closed。

Context (2026-08-02): four guard sites swallowed every exception and let the
trade proceed — the drawdown/cooldown/lockout check (inner and outer), the BUY
position-sizing guard, and the SELL quantity clamp. Because repositories share
a scoped_session across concurrent coroutines, transient DB errors are a real
and recurring mechanism here, not a theoretical one. An unsized BUY or an
unclamped SELL reaching a live broker is the worst outcome in this file, so
these now fail closed. SELL remains permitted when only the *protections*
subsystem is unavailable, so a user is never trapped in a position.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.automated_trading_service import AutomatedTradingService
from src.services.trading_protections_service import TradingProtectionsService


@pytest.fixture
def settings_repo():
    repo = MagicMock()
    repo.get.side_effect = lambda uid, key: {
        "ai_trading_enabled": "true",
        "auto_trade_threshold": "9",
        "auto_trade_min_threshold": "3",
    }.get(key)
    return repo


@pytest.fixture
def service(settings_repo):
    with patch('src.services.automated_trading_service.InteractionService'):
        return AutomatedTradingService(
            settings_repo=settings_repo,
            notification_service=AsyncMock(),
        )


class TestProtectionsServiceFailsClosed:

    def test_check_blocks_buy_when_internals_raise(self):
        svc = TradingProtectionsService(user_id="u1")
        svc._check_max_drawdown = MagicMock(side_effect=RuntimeError("db gone"))

        reason = svc.check("AAPL", "BUY")

        assert reason is not None
        assert "blocked" in reason.lower()

    def test_check_still_allows_sell_when_internals_raise(self):
        """Non-BUY returns before the guarded block — never trap a position."""
        svc = TradingProtectionsService(user_id="u1")
        svc._check_max_drawdown = MagicMock(side_effect=RuntimeError("db gone"))

        assert svc.check("AAPL", "SELL") is None


class TestEvaluateFailsClosed:

    @pytest.mark.asyncio
    async def test_buy_blocked_when_protection_subsystem_unavailable(self, service):
        with patch('src.services.trading_protections_service.TradingProtectionsService',
                   side_effect=ImportError("boom")):
            result = await service.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="BUY",
                quantity=100.0, confidence_score=10, rationale="test",
            )

        assert result["status"] == "blocked"
        assert "protection" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_sell_allowed_when_protection_subsystem_unavailable(self, service):
        """A protections outage must not block an exit; it should proceed past
        the guard (and fail later for unrelated reasons, not 'blocked')."""
        with patch('src.services.trading_protections_service.TradingProtectionsService',
                   side_effect=ImportError("boom")):
            result = await service.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="SELL",
                quantity=1.0, confidence_score=10, rationale="test",
            )

        reason = str(result.get("reason", "")).lower()
        assert "protection subsystem unavailable" not in reason


class TestRationaleNoneHandling:

    @pytest.mark.asyncio
    async def test_rationale_none_does_not_raise_typeerror(self, service):
        """
        rationale defaults to None but feeds `in` substring tests for
        excess-cash detection — previously TypeError for any caller omitting it.
        """
        with patch('src.services.trading_protections_service.TradingProtectionsService') as MockProt:
            MockProt.return_value.check.return_value = None
            try:
                await service.evaluate_and_execute_trade(
                    user_id="u1", ticker="AAPL", action="BUY",
                    quantity=100.0, confidence_score=1, rationale=None,
                )
            except TypeError as exc:  # pragma: no cover - regression guard
                pytest.fail(f"rationale=None raised TypeError: {exc}")

    @pytest.mark.asyncio
    async def test_low_confidence_still_skips_with_none_rationale(self, service):
        with patch('src.services.trading_protections_service.TradingProtectionsService') as MockProt:
            MockProt.return_value.check.return_value = None
            result = await service.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="BUY",
                quantity=100.0, confidence_score=1, rationale=None,
            )

        assert result["status"] == "skipped"
