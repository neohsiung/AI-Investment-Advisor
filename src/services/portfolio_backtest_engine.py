"""
Event-driven, portfolio-aware backtest engine.

Reference implementation studied: QuantDinger's backtest simulator
(services/backtest.py, Apache-2.0 — reimplemented here, not ported: no
shared code, different data shapes) and freqtrade's backtest loop
(optimize/backtesting.py, GPL-3.0 — ideas only, formulas reimplemented
independently, no code copied).

This replaces the day-by-day LLM-calling loop in `backtest_service.py`
(which is really an agent-feedback generator, not a strategy backtester —
left untouched, still used for agent accuracy tracking) with a real
bar-by-bar simulator: cash, a single position, fees, slippage, stoploss,
fixed-fraction position sizing, and an equity curve. Strategy logic is a
pluggable, deterministic `signal_fn(bar_index, ohlcv) -> "BUY"|"SELL"|"HOLD"`
— NOT an LLM call per bar (too slow/costly for a real backtest); an LLM-
driven strategy can be backtested by pre-computing its signals once and
replaying them here.

事件驅動投組回測引擎：現金/單一部位/手續費/滑價/停損/固定比例部位大小/
權益曲線。策略邏輯為可插拔的決定性 signal_fn（非逐 bar 呼叫 LLM）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SignalFn = Callable[[int, Dict[str, List[Any]]], str]


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    quantity: float = 0.0
    exit_reason: Optional[str] = None  # "signal" | "stoploss"
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


@dataclass
class BacktestResult:
    ticker: str
    equity_curve: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    final_cash: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)


class PortfolioBacktestEngine:
    def __init__(
        self,
        initial_cash: float = 100_000.0,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        stoploss_pct: Optional[float] = 0.08,
        position_size_pct: float = 0.20,
    ):
        self.initial_cash = initial_cash
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.stoploss_pct = stoploss_pct
        self.position_size_pct = position_size_pct

    def run(self, ticker: str, ohlcv: Dict[str, List[Any]], signal_fn: SignalFn) -> BacktestResult:
        """
        Bar-by-bar simulation over `ohlcv` (the `MarketDataService.get_ohlcv()`
        shape: {"date","open","high","low","close","volume"}). `signal_fn` is
        called once per bar with (bar_index, ohlcv) and must return
        "BUY"/"SELL"/"HOLD" using only data up to and including that bar
        (callers are responsible for not leaking future data).
        """
        dates = ohlcv.get("date", [])
        closes = ohlcv.get("close", [])
        lows = ohlcv.get("low", closes)
        n = len(closes)
        if n < 2:
            return BacktestResult(ticker=ticker, final_cash=self.initial_cash)

        cash = self.initial_cash
        position_qty = 0.0
        entry_price = 0.0
        entry_date = None
        trades: List[Trade] = []
        equity_curve: List[float] = []

        for i in range(n):
            price = float(closes[i])
            low = float(lows[i]) if i < len(lows) else price
            date = str(dates[i]) if i < len(dates) else str(i)

            # Stoploss check (intra-bar, using the bar's low) — before signal.
            if position_qty > 0 and self.stoploss_pct:
                stop_price = entry_price * (1 - self.stoploss_pct)
                if low <= stop_price:
                    fill_price = stop_price * (1 - self.slippage_pct)
                    proceeds = position_qty * fill_price * (1 - self.fee_pct)
                    pnl = proceeds - (position_qty * entry_price)
                    trades.append(Trade(
                        entry_date=entry_date, entry_price=entry_price,
                        exit_date=date, exit_price=fill_price, quantity=position_qty,
                        exit_reason="stoploss", pnl=round(pnl, 4),
                        pnl_pct=round((fill_price / entry_price - 1) * 100, 4),
                    ))
                    cash += proceeds
                    position_qty = 0.0
                    entry_price = 0.0
                    entry_date = None

            try:
                signal = signal_fn(i, ohlcv)
            except Exception as exc:
                logger.warning("signal_fn failed at bar %d: %s", i, exc)
                signal = "HOLD"

            if signal == "BUY" and position_qty == 0 and cash > 0:
                alloc = cash * self.position_size_pct
                fill_price = price * (1 + self.slippage_pct)
                qty = (alloc * (1 - self.fee_pct)) / fill_price
                if qty > 0:
                    cash -= qty * fill_price * (1 + self.fee_pct)
                    position_qty = qty
                    entry_price = fill_price
                    entry_date = date

            elif signal == "SELL" and position_qty > 0:
                fill_price = price * (1 - self.slippage_pct)
                proceeds = position_qty * fill_price * (1 - self.fee_pct)
                pnl = proceeds - (position_qty * entry_price)
                trades.append(Trade(
                    entry_date=entry_date, entry_price=entry_price,
                    exit_date=date, exit_price=fill_price, quantity=position_qty,
                    exit_reason="signal", pnl=round(pnl, 4),
                    pnl_pct=round((fill_price / entry_price - 1) * 100, 4),
                ))
                cash += proceeds
                position_qty = 0.0
                entry_price = 0.0
                entry_date = None

            mark_to_market = cash + position_qty * price
            equity_curve.append(round(mark_to_market, 4))

        # Close any open position at the final bar's price for reporting.
        final_cash = cash
        if position_qty > 0:
            final_cash = cash + position_qty * float(closes[-1])

        from src.services.metrics_service import compute_all_metrics
        trade_dicts = [vars(t) for t in trades]
        metrics = compute_all_metrics(equity_curve, trade_dicts)

        return BacktestResult(
            ticker=ticker, equity_curve=equity_curve, dates=[str(d) for d in dates[:len(equity_curve)]],
            trades=trade_dicts, final_cash=round(final_cash, 4), metrics=metrics,
        )


def simple_ma_crossover_signal(fast: int = 10, slow: int = 30) -> SignalFn:
    """
    Reference deterministic strategy for smoke-testing the engine (and a
    real usable baseline): BUY when fast MA crosses above slow MA, SELL on
    the reverse cross. Returns a `signal_fn` closure.
    """
    def _signal(i: int, ohlcv: Dict[str, List[Any]]) -> str:
        closes = ohlcv.get("close", [])
        if i < slow:
            return "HOLD"
        window_fast_prev = closes[i - fast:i]
        window_slow_prev = closes[i - slow:i]
        window_fast_now = closes[i - fast + 1:i + 1]
        window_slow_now = closes[i - slow + 1:i + 1]
        if not window_fast_prev or not window_slow_prev:
            return "HOLD"
        fast_prev = sum(window_fast_prev) / len(window_fast_prev)
        slow_prev = sum(window_slow_prev) / len(window_slow_prev)
        fast_now = sum(window_fast_now) / len(window_fast_now)
        slow_now = sum(window_slow_now) / len(window_slow_now)
        if fast_prev <= slow_prev and fast_now > slow_now:
            return "BUY"
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL"
        return "HOLD"
    return _signal
