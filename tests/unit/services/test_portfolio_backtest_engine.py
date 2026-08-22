"""
Unit tests for PortfolioBacktestEngine.
投組回測引擎單元測試。

This engine's output is not just a report: migration 018 gates candidate agent
rules on backtest results, and /backtest persists every run. An engine that
quietly overstates returns would promote bad rules to active. So the tests
assert the arithmetic — fees, slippage, stoploss fill price — rather than only
that a result comes back.

Pure computation, no I/O, no mocking needed.

這個引擎的輸出不只是報表：018 用回測結果當 candidate 規則的升級閘門，/backtest
也會把每次結果寫進資料庫。引擎若默默高估報酬，就會把壞規則升成 active。
所以這裡斷言的是手續費、滑價、停損成交價這些算術，而不只是「有回傳結果」。
"""
import pytest

from src.services.portfolio_backtest_engine import (
    BacktestResult,
    PortfolioBacktestEngine,
    Trade,
    simple_ma_crossover_signal,
)


def _ohlcv(closes, lows=None, dates=None):
    return {
        "date": dates if dates is not None else [f"2026-01-{i + 1:02d}" for i in range(len(closes))],
        "close": closes,
        "low": lows if lows is not None else closes,
    }


def _always(signal):
    return lambda i, ohlcv: signal


def _on_bars(mapping, default="HOLD"):
    return lambda i, ohlcv: mapping.get(i, default)


class TestGuardRails:
    @pytest.mark.parametrize("closes", [[], [100.0]])
    def test_too_few_bars_returns_untouched_cash(self, closes):
        engine = PortfolioBacktestEngine(initial_cash=50_000.0)
        result = engine.run("AAPL", _ohlcv(closes), _always("BUY"))
        assert isinstance(result, BacktestResult)
        assert result.final_cash == 50_000.0
        assert result.equity_curve == []
        assert result.trades == []

    def test_signal_function_errors_are_treated_as_hold(self):
        """A broken strategy must not abort the run or open a position."""
        def _boom(i, ohlcv):
            raise ValueError("strategy exploded")

        engine = PortfolioBacktestEngine()
        result = engine.run("AAPL", _ohlcv([100.0, 101.0, 102.0]), _boom)
        assert result.trades == []
        assert result.final_cash == pytest.approx(100_000.0)

    def test_missing_lows_fall_back_to_closes(self):
        engine = PortfolioBacktestEngine(stoploss_pct=0.08)
        ohlcv = {"date": ["d0", "d1"], "close": [100.0, 100.0]}
        result = engine.run("AAPL", ohlcv, _always("HOLD"))
        assert len(result.equity_curve) == 2

    def test_dates_default_to_bar_index_when_absent(self):
        # Stoploss off so the exit is driven purely by the signal — otherwise
        # the default 8% stop fires at bar 1 and this would be testing two
        # things at once. / 關掉停損以隔離變因，否則預設 8% 會在 bar 1 先觸發。
        engine = PortfolioBacktestEngine(stoploss_pct=None)
        result = engine.run("AAPL", {"close": [100.0, 90.0, 80.0]}, _on_bars({0: "BUY", 2: "SELL"}))
        assert result.trades[0]["entry_date"] == "0"
        assert result.trades[0]["exit_date"] == "2"


class TestEntryAccounting:
    def test_buy_applies_slippage_and_fee_and_sizes_the_position(self):
        engine = PortfolioBacktestEngine(
            initial_cash=100_000.0, fee_pct=0.001, slippage_pct=0.0005,
            stoploss_pct=None, position_size_pct=0.20,
        )
        result = engine.run("AAPL", _ohlcv([100.0, 100.0]), _on_bars({0: "BUY"}))

        alloc = 100_000.0 * 0.20
        fill = 100.0 * 1.0005
        qty = (alloc * 0.999) / fill
        expected_cash = 100_000.0 - qty * fill * 1.001

        # Position is still open at the end, so final_cash marks it to market.
        assert result.final_cash == pytest.approx(expected_cash + qty * 100.0, rel=1e-9)
        assert result.trades == []

    def test_second_buy_while_holding_is_ignored(self):
        engine = PortfolioBacktestEngine(stoploss_pct=None)
        result = engine.run("AAPL", _ohlcv([100.0, 100.0, 100.0]), _always("BUY"))
        # One entry only; no trade closes, so the log stays empty.
        assert result.trades == []
        assert len(result.equity_curve) == 3

    def test_sell_without_a_position_is_a_noop(self):
        engine = PortfolioBacktestEngine()
        result = engine.run("AAPL", _ohlcv([100.0, 101.0]), _always("SELL"))
        assert result.trades == []
        assert result.final_cash == pytest.approx(100_000.0)


class TestExitAccounting:
    def test_signal_exit_records_pnl_and_reason(self):
        engine = PortfolioBacktestEngine(
            initial_cash=100_000.0, fee_pct=0.0, slippage_pct=0.0,
            stoploss_pct=None, position_size_pct=1.0,
        )
        result = engine.run("AAPL", _ohlcv([100.0, 120.0]), _on_bars({0: "BUY", 1: "SELL"}))

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade["exit_reason"] == "signal"
        assert trade["entry_price"] == pytest.approx(100.0)
        assert trade["exit_price"] == pytest.approx(120.0)
        assert trade["pnl_pct"] == pytest.approx(20.0)
        assert trade["pnl"] == pytest.approx(1000.0 * 20.0)
        assert result.final_cash == pytest.approx(120_000.0)

    def test_losing_trade_reports_negative_pnl(self):
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.0, stoploss_pct=None, position_size_pct=1.0)
        result = engine.run("AAPL", _ohlcv([100.0, 90.0]), _on_bars({0: "BUY", 1: "SELL"}))
        assert result.trades[0]["pnl_pct"] == pytest.approx(-10.0)
        assert result.trades[0]["pnl"] < 0

    def test_stoploss_fires_on_the_bar_low_not_the_close(self):
        """
        The whole point of tracking lows is that an intra-bar spike down should
        stop you out even if the close recovers. If this regressed to using the
        close, every backtest would understate drawdown.
        用 low 而非 close 判斷停損：盤中insert急殺應該要被掃出場，即使收盤已收復。
        """
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.0, stoploss_pct=0.10, position_size_pct=1.0)
        # Bar 1 closes flat at 100 but dipped to 85 — below the 90 stop.
        result = engine.run("AAPL", _ohlcv([100.0, 100.0], lows=[100.0, 85.0]),
                            _on_bars({0: "BUY"}))

        assert len(result.trades) == 1
        assert result.trades[0]["exit_reason"] == "stoploss"
        # Filled at the stop price, not the 85 low and not the 100 close.
        assert result.trades[0]["exit_price"] == pytest.approx(90.0)
        assert result.trades[0]["pnl_pct"] == pytest.approx(-10.0)

    def test_stoploss_can_be_disabled(self):
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.0, stoploss_pct=None, position_size_pct=1.0)
        result = engine.run("AAPL", _ohlcv([100.0, 100.0], lows=[100.0, 1.0]),
                            _on_bars({0: "BUY"}))
        assert result.trades == []

    def test_stoploss_applies_slippage_to_the_fill(self):
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.01, stoploss_pct=0.10, position_size_pct=1.0)
        result = engine.run("AAPL", _ohlcv([100.0, 100.0], lows=[100.0, 50.0]),
                            _on_bars({0: "BUY"}))
        entry = result.trades[0]["entry_price"]
        assert result.trades[0]["exit_price"] == pytest.approx(entry * 0.90 * 0.99)

    def test_position_can_be_reopened_after_a_stoploss(self):
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.0, stoploss_pct=0.10, position_size_pct=0.5)
        result = engine.run(
            "AAPL",
            _ohlcv([100.0, 100.0, 100.0, 110.0], lows=[100.0, 85.0, 100.0, 110.0]),
            _on_bars({0: "BUY", 2: "BUY", 3: "SELL"}),
        )
        reasons = [t["exit_reason"] for t in result.trades]
        assert reasons == ["stoploss", "signal"]


class TestResultShape:
    def test_equity_curve_and_dates_line_up(self):
        engine = PortfolioBacktestEngine()
        closes = [100.0, 101.0, 102.0, 103.0]
        result = engine.run("AAPL", _ohlcv(closes), _always("HOLD"))
        assert len(result.equity_curve) == len(closes)
        assert len(result.dates) == len(result.equity_curve)

    def test_flat_hold_leaves_equity_at_initial_cash(self):
        engine = PortfolioBacktestEngine(initial_cash=1_000.0)
        result = engine.run("AAPL", _ohlcv([10.0, 20.0, 5.0]), _always("HOLD"))
        assert result.equity_curve == [1_000.0, 1_000.0, 1_000.0]

    def test_metrics_are_computed(self):
        engine = PortfolioBacktestEngine(
            fee_pct=0.0, slippage_pct=0.0, stoploss_pct=None, position_size_pct=1.0)
        result = engine.run("AAPL", _ohlcv([100.0, 110.0, 120.0]),
                            _on_bars({0: "BUY", 2: "SELL"}))
        assert isinstance(result.metrics, dict)
        assert result.metrics  # compute_all_metrics returned something

    def test_ticker_is_echoed_back(self):
        result = PortfolioBacktestEngine().run("MSFT", _ohlcv([1.0, 2.0]), _always("HOLD"))
        assert result.ticker == "MSFT"


class TestTradeDataclass:
    def test_defaults(self):
        t = Trade(entry_date="d", entry_price=1.0)
        assert t.exit_date is None and t.exit_price is None
        assert t.quantity == 0.0 and t.pnl is None


class TestSimpleMaCrossoverSignal:
    def test_holds_until_the_slow_window_is_available(self):
        signal = simple_ma_crossover_signal(fast=2, slow=5)
        closes = [1.0] * 10
        for i in range(5):
            assert signal(i, {"close": closes}) == "HOLD"

    def test_golden_cross_emits_buy(self):
        signal = simple_ma_crossover_signal(fast=2, slow=4)
        # Flat, then a sharp jump so the fast MA crosses above the slow MA.
        closes = [10.0, 10.0, 10.0, 10.0, 30.0]
        assert signal(4, {"close": closes}) == "BUY"

    def test_death_cross_emits_sell(self):
        signal = simple_ma_crossover_signal(fast=2, slow=4)
        closes = [30.0, 30.0, 30.0, 30.0, 5.0]
        assert signal(4, {"close": closes}) == "SELL"

    def test_no_cross_holds(self):
        signal = simple_ma_crossover_signal(fast=2, slow=4)
        closes = [10.0] * 6
        assert signal(5, {"close": closes}) == "HOLD"

    def test_runs_end_to_end_through_the_engine(self):
        """Smoke test: the reference strategy must drive the engine without error."""
        closes = [100.0 + (i % 20) * 2 for i in range(120)]
        result = PortfolioBacktestEngine().run(
            "AAPL", _ohlcv(closes), simple_ma_crossover_signal(5, 20))
        assert len(result.equity_curve) == 120
        assert result.final_cash > 0
