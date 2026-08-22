"""
Tests for the SELL churn guard and signal-scoped BUY rules.
測試 SELL churn 防護與買方 signal 分側。

Context (2026-08-02): SELL bypassed TradingProtectionsService entirely. The fix
deliberately does NOT extend the three existing rules to SELL — they all key
off "recent decision alpha is negative", which is exactly when a user most
needs to exit, so blocking a SELL then would lock them into a falling position.
Instead SELL gets its own over-trading guard, and the three BUY rules stop
pooling BUY and SELL outcomes into one alpha average.

The churn rule counts COMPLETED ROUND TRIPS (SELL later followed by a BUY of
the same ticker), not raw SELL count — scaling out in tranches is legitimate.
That also makes it structurally unable to block a first exit.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

from src.services.trading_protections_service import (
    TradingProtectionsService,
    BUY_SIDE_SIGNALS,
    SELL_SIDE_SIGNALS,
)

USER = "u1"


def _engine_with(trades=(), outcomes=()):
    """In-memory DB seeded with transactions and/or decision_outcomes."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY, user_id TEXT, ticker TEXT,
                trade_date DATE, action TEXT, entry_category TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE decision_outcomes (
                id INTEGER PRIMARY KEY, user_id TEXT, ticker TEXT,
                signal TEXT, alpha_pct REAL, resolved_at TIMESTAMP
            )
        """))
        for d, action, category in trades:
            conn.execute(
                text("INSERT INTO transactions (user_id,ticker,trade_date,action,entry_category) "
                     "VALUES (:u,'AAPL',:d,:a,:c)"),
                {"u": USER, "d": d, "a": action, "c": category},
            )
        for i, (signal, alpha) in enumerate(outcomes):
            conn.execute(
                text("INSERT INTO decision_outcomes (user_id,ticker,signal,alpha_pct,resolved_at) "
                     "VALUES (:u,'AAPL',:s,:a,:t)"),
                {"u": USER, "s": signal, "a": alpha, "t": f"2026-07-{i + 1:02d} 00:00:00"},
            )
    return engine


def _svc(engine, **cfg_overrides):
    with patch('src.services.trading_protections_service.get_db_engine', return_value=engine):
        s = TradingProtectionsService(user_id=USER)
    from src.services.trading_protections_service import _SETTING_DEFAULTS
    s._cfg = {**_SETTING_DEFAULTS, **cfg_overrides}
    return s


def _d(days_ago):
    return (date.today() - timedelta(days=days_ago)).isoformat()


class TestSellChurnGuard:

    def test_first_exit_is_never_blocked(self):
        """Structural property: zero round trips → rule cannot fire."""
        svc = _svc(_engine_with())

        assert svc.check("AAPL", "SELL") is None

    def test_scaling_out_in_tranches_is_allowed(self):
        """Three SELLs with no intervening BUY is risk management, not churn."""
        svc = _svc(_engine_with(trades=[
            (_d(2), "SELL", "trade"),
            (_d(1), "SELL", "trade"),
            (_d(0), "SELL", "trade"),
        ]))

        assert svc.check("AAPL", "SELL") is None

    def test_repeated_round_trips_are_blocked(self):
        svc = _svc(_engine_with(trades=[
            (_d(3), "SELL", "trade"),
            (_d(3), "BUY", "trade"),
            (_d(2), "SELL", "trade"),
            (_d(1), "BUY", "trade"),
        ]))

        reason = svc.check("AAPL", "SELL")

        assert reason is not None
        assert "churn" in reason.lower()

    def test_round_trips_outside_the_window_are_ignored(self):
        svc = _svc(_engine_with(trades=[
            (_d(30), "SELL", "trade"), (_d(30), "BUY", "trade"),
            (_d(29), "SELL", "trade"), (_d(28), "BUY", "trade"),
        ]))

        assert svc.check("AAPL", "SELL") is None

    def test_non_trade_rows_are_excluded(self):
        """capital_flow / sync_adjustment rows must not count as churn."""
        svc = _svc(_engine_with(trades=[
            (_d(2), "SELL", "capital_flow"), (_d(2), "BUY", "capital_flow"),
            (_d(1), "SELL", "sync_adjustment"), (_d(1), "BUY", "sync_adjustment"),
        ]))

        assert svc.check("AAPL", "SELL") is None

    def test_kill_switch_disables_the_rule(self):
        svc = _svc(
            _engine_with(trades=[
                (_d(3), "SELL", "trade"), (_d(3), "BUY", "trade"),
                (_d(2), "SELL", "trade"), (_d(1), "BUY", "trade"),
            ]),
            protection_sell_churn_enabled=False,
        )

        assert svc.check("AAPL", "SELL") is None

    def test_fails_open_on_internal_error(self):
        """A churn-guard fault must never stop someone exiting."""
        svc = _svc(_engine_with())
        svc._check_sell_churn = MagicMock(side_effect=RuntimeError("db gone"))

        assert svc.check("AAPL", "SELL") is None

    def test_strong_sell_routes_to_the_churn_rule(self):
        svc = _svc(_engine_with())
        svc._check_sell_churn = MagicMock(return_value="churned")

        assert svc.check("AAPL", "STRONG_SELL") == "churned"

    def test_buy_does_not_run_the_churn_rule(self):
        svc = _svc(_engine_with())
        svc._check_sell_churn = MagicMock(side_effect=AssertionError("churn ran for BUY"))
        svc._check_max_drawdown = MagicMock(return_value=None)
        svc._check_ticker_cooldown = MagicMock(return_value=None)
        svc._check_consecutive_loss_lockout = MagicMock(return_value=None)

        assert svc.check("AAPL", "BUY") is None


class TestSignalScoping:

    def test_sell_losses_do_not_halt_buying(self):
        """
        The pooling bug: heavily negative SELL alpha must not trip the BUY-side
        drawdown halt.
        """
        svc = _svc(_engine_with(outcomes=[
            ("SELL", -50.0), ("SELL", -60.0), ("STRONG_SELL", -70.0),
            ("BUY", 5.0), ("BUY", 6.0), ("STRONG_BUY", 7.0),
        ]))

        assert svc._check_max_drawdown() is None

    def test_strong_buy_is_counted(self):
        """STRONG_BUY must not be dropped by the signal filter."""
        svc = _svc(_engine_with(outcomes=[
            ("STRONG_BUY", -10.0), ("STRONG_BUY", -20.0), ("STRONG_BUY", -30.0),
        ]))

        reason = svc._check_max_drawdown()

        assert reason is not None
        assert "drawdown halt" in reason.lower()

    def test_cooldown_ignores_sell_outcomes(self):
        svc = _svc(_engine_with(outcomes=[("SELL", -99.0)]))

        assert svc._check_ticker_cooldown("AAPL") is None

    def test_consecutive_loss_ignores_sell_outcomes(self):
        svc = _svc(_engine_with(outcomes=[
            ("SELL", -1.0), ("SELL", -2.0), ("SELL", -3.0),
        ]))

        assert svc._check_consecutive_loss_lockout() is None

    def test_signal_lists_are_disjoint_and_cover_the_rating_scale(self):
        from src.agents.structured import Rating

        assert not set(BUY_SIDE_SIGNALS) & set(SELL_SIDE_SIGNALS)
        scale = {r.value.upper() for r in Rating}
        covered = set(BUY_SIDE_SIGNALS) | set(SELL_SIDE_SIGNALS) | {"HOLD"}
        assert scale <= covered, f"Rating values not classified: {scale - covered}"


class TestConfigOverrides:

    def test_settings_override_defaults(self):
        svc = _svc(
            _engine_with(trades=[(_d(1), "SELL", "trade"), (_d(1), "BUY", "trade")]),
            protection_sell_churn_max_round_trips=1,
        )

        assert svc.check("AAPL", "SELL") is not None

    def test_settings_failure_falls_back_to_defaults(self):
        """A settings hiccup must not block every BUY."""
        with patch('src.services.trading_protections_service.get_db_engine',
                   return_value=_engine_with()):
            svc = TradingProtectionsService(user_id=USER)

        with patch('src.services.settings_service.SettingsService',
                   side_effect=RuntimeError("settings table down")):
            cfg = svc._load_config()

        from src.services.trading_protections_service import _SETTING_DEFAULTS
        assert cfg == _SETTING_DEFAULTS
