"""
Safety regression tests for action normalization and NULL alpha handling.
測試 action 正規化與 alpha_pct NULL 的安全性回歸。

Context (2026-08-02), two defects found while preparing to enable live trading:

1. `AutomatedTradingService` resolves direction as
   `OrderAction.BUY if action.upper() == "BUY" else OrderAction.SELL`, while
   `TradingProtectionsService.check()` returned None for any non-BUY. The
   WebSocket manual-order path forwards a client-supplied action verbatim at
   confidence_score=10 (always auto-executes, no approval card). So
   `action="BUUY"` was an unguarded live SELL.

2. `decision_outcomes.alpha_pct` is nullable and the three rules only filtered
   `resolved_at IS NOT NULL`. `float(None)` raised TypeError, which — after the
   guards were made fail-closed — blocked every BUY on a single NULL row.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.trading_protections_service import (
    TradingProtectionsService,
    _normalize_side,
)


@pytest.fixture
def svc():
    with patch('src.services.trading_protections_service.get_db_engine'):
        return TradingProtectionsService(user_id="u1")


class TestNormalizeSide:

    @pytest.mark.parametrize("raw", ["BUY", "buy", " Buy ", "STRONG_BUY", "strong-buy",
                                     "ACCUMULATE", "ADD", "INCREASE"])
    def test_buy_vocabulary(self, raw):
        assert _normalize_side(raw) == "BUY"

    @pytest.mark.parametrize("raw", ["SELL", "sell", "STRONG_SELL", "strong sell",
                                     "TRIM", "REDUCE", "LIQUIDATE", "EXIT", "CLOSE"])
    def test_sell_vocabulary(self, raw):
        assert _normalize_side(raw) == "SELL"

    @pytest.mark.parametrize("raw", ["HOLD", "hold", "NEUTRAL"])
    def test_hold_vocabulary(self, raw):
        assert _normalize_side(raw) == "HOLD"

    @pytest.mark.parametrize("raw", ["BUUY", "", "   ", None, "SELLL", "purchase", 42])
    def test_unrecognized_returns_none(self, raw):
        assert _normalize_side(raw) is None


class TestCheckRefusesUnknownActions:
    """The headline safety property: unknown action must never be waved through."""

    @pytest.mark.parametrize("bad", ["BUUY", "", "   ", None, "purchase"])
    def test_unrecognized_action_is_blocked(self, svc, bad):
        reason = svc.check("AAPL", bad)

        assert reason is not None, f"{bad!r} was allowed — downstream turns it into a live SELL"
        assert "unrecognized" in reason.lower()

    def test_hold_is_not_gated(self, svc):
        assert svc.check("AAPL", "HOLD") is None

    def test_recognized_sell_is_not_gated_by_buy_rules(self, svc):
        # BUY-side rules must not run for a legitimate exit.
        svc._check_max_drawdown = MagicMock(side_effect=AssertionError("BUY rule ran for SELL"))
        assert svc.check("AAPL", "SELL") is None

    def test_strong_buy_is_gated_like_buy(self, svc):
        """STRONG_BUY is the highest-conviction signal — it must not slip past."""
        svc._check_max_drawdown = MagicMock(return_value="halted")
        svc._check_ticker_cooldown = MagicMock(return_value=None)
        svc._check_consecutive_loss_lockout = MagicMock(return_value=None)

        assert svc.check("AAPL", "STRONG_BUY") == "halted"

    def test_health_probe_still_works(self, svc):
        """webhook_service.py calls check("HEALTHCHECK","BUY") as a read-only probe."""
        svc._check_max_drawdown = MagicMock(return_value=None)
        svc._check_ticker_cooldown = MagicMock(return_value=None)
        svc._check_consecutive_loss_lockout = MagicMock(return_value=None)

        assert svc.check("HEALTHCHECK", "BUY") is None


class TestNullAlphaDoesNotBlockBuy:
    """
    A resolved row with NULL alpha_pct must be excluded by the query, not
    crash the rule. Verified against real SQL on in-memory sqlite.
    """

    @staticmethod
    def _seed(alphas):
        """Build an in-memory DB with decision_outcomes rows; alphas may contain None."""
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE decision_outcomes (
                    id INTEGER PRIMARY KEY, user_id TEXT, ticker TEXT,
                    signal TEXT, alpha_pct REAL, resolved_at TIMESTAMP
                )
            """))
            for i, a in enumerate(alphas):
                conn.execute(
                    text("INSERT INTO decision_outcomes "
                         "(user_id,ticker,signal,alpha_pct,resolved_at) "
                         "VALUES ('u1','AAPL','BUY',:a,:t)"),
                    {"a": a, "t": f"2026-08-0{i + 1} 00:00:00"},
                )
        return engine

    def _svc_with(self, engine):
        with patch('src.services.trading_protections_service.get_db_engine', return_value=engine):
            return TradingProtectionsService(user_id="u1")

    def test_null_alpha_row_does_not_raise(self):
        svc = self._svc_with(self._seed([1.0, None, 2.0, 3.0]))

        # Must not raise TypeError, and must not fail closed into a block.
        assert svc._check_max_drawdown() is None

    def test_all_null_alpha_is_treated_as_no_history(self):
        svc = self._svc_with(self._seed([None, None, None, None]))

        assert svc._check_max_drawdown() is None
        assert svc._check_consecutive_loss_lockout() is None

    def test_null_rows_excluded_from_consecutive_loss(self):
        """NULLs must not be counted as losses, nor break the streak check."""
        svc = self._svc_with(self._seed([-1.0, None, -2.0, -3.0]))

        # Three real losses remain → lockout should fire on the non-NULL rows.
        assert svc._check_consecutive_loss_lockout() is not None

    def test_buy_not_blocked_by_null_alpha_via_public_check(self):
        """End-to-end: a NULL row must not turn into 'BUY blocked for safety'."""
        svc = self._svc_with(self._seed([1.0, None, 2.0]))

        assert svc.check("AAPL", "BUY") is None
