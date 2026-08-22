"""
The concentration-rebalance rule, expressed as a backtestable signal.
把集中度再平衡規則表達成可回測的訊號。

`SentinelService._check_allocation_drift` is what actually drives automated
sells in production: when a position's weight reaches
`max_single_position_weight` (25% in prod) it is trimmed back to 90% of that
(22.5%). As of 2026-08-10 that rule had never been measured — `backtest_runs`
held zero rows — yet it was wired to a live eToro account with auto-execution.

This module makes the rule measurable. `PortfolioBacktestEngine` simulates a
single position sized at `position_size_pct` of cash, so "weight" maps onto
"how far the position has run since entry": the engine's position grows
relative to the account exactly as a real holding does. Trimming at a weight
ceiling therefore backtests as *taking profit once an entry has appreciated
past a threshold* — which is precisely the economic content of the rule, and
precisely what needs testing.

Honest limits of this mapping / 此對應的誠實限制
  - The engine holds one position; production holds several. Cross-position
    interactions (which name gets trimmed first) are not modelled.
  - The engine is all-in/all-out per signal: it cannot sell a partial
    position, so a trim backtests as a full exit. That makes the simulated
    rule strictly more aggressive than production's partial trim, so a pass
    here is a *conservative* result and a fail is not automatically damning.
  - Entry timing is not part of the production rule at all — Sentinel never
    decides what to buy on this path. A buy rule is supplied here only so
    there is something to trim; it is a benchmark scaffold, not the strategy.

因此：本回測衡量的是「漲多就獲利了結」這個經濟本質。引擎僅持有單一部位且無法
部分減碼（減碼在此模擬為全數出場，比 production 的部分減碼更激進），故通過屬
保守結果；而買進規則僅為提供可減碼的部位，屬基準腳手架而非策略本身。
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.services.portfolio_backtest_engine import SignalFn


def concentration_trim_signal(
    max_single_position_weight: float = 25.0,
    position_size_pct: float = 20.0,
    entry_lookback: int = 20,
) -> SignalFn:
    """
    Build a signal_fn replaying the production concentration rule.
    產生重現 production 集中度規則的 signal_fn。

    Args mirror the production settings so a backtest can be run with the
    exact values in the `settings` table:
      max_single_position_weight — the trim ceiling (prod: 25.0)
      position_size_pct          — entry size as % of cash (engine default 20)
      entry_lookback             — bars of breakout used to open a position

    A position entered at `position_size_pct` of the account must appreciate
    by `max/position_size_pct` to reach the ceiling; at prod's 25/20 that is
    a 25% gain before the trim fires.
    以 25/20 為例，部位需上漲 25% 才會觸及上限並觸發減碼。

    IMPORTANT — run this with `stoploss_pct=None`.
    重要：必須以 stoploss_pct=None 執行。

    The closure tracks its own entry price, and a signal_fn cannot observe an
    engine-side stoploss exit. With a stoploss enabled the two would desync:
    the engine would be flat while this closure still believed it held, and it
    would emit HOLD forever, never re-entering. `run_concentration_backtest()`
    below sets this correctly. Production has no stoploss on the concentration
    path either, so this also keeps the simulation faithful.
    此閉包自行追蹤進場價，而 signal_fn 無法得知引擎端的停損出場；若啟用停損，
    兩邊狀態會脫節（引擎已空手，閉包仍認為持有），此後永遠回傳 HOLD 而不再進場。
    production 的集中度路徑同樣沒有停損，故此設定也更貼近真實。
    """
    if position_size_pct <= 0:
        raise ValueError("position_size_pct must be positive")

    # Gain multiple at which the position's weight reaches the ceiling.
    # 部位權重觸及上限時所對應的漲幅倍數。
    trim_multiple = max_single_position_weight / position_size_pct

    state: Dict[str, Any] = {"entry_price": None}

    def _signal(i: int, ohlcv: Dict[str, List[Any]]) -> str:
        closes = ohlcv.get("close", [])
        if i < entry_lookback or i >= len(closes):
            return "HOLD"

        price = float(closes[i])
        entry = state["entry_price"]

        if entry is not None:
            if price >= entry * trim_multiple:
                state["entry_price"] = None
                return "SELL"
            return "HOLD"

        # Entry scaffold: break above the prior `entry_lookback` bars. Uses
        # only closed bars up to i-1, so no future data leaks into the signal.
        # 進場腳手架：突破前 N 根收盤高點；僅使用 i-1 以前的資料，不洩漏未來。
        window = closes[i - entry_lookback:i]
        if not window:
            return "HOLD"
        if price > max(float(c) for c in window):
            state["entry_price"] = price
            return "BUY"
        return "HOLD"

    return _signal


def run_concentration_backtest(
    user_id: str,
    ticker: str,
    ohlcv: Dict[str, List[Any]],
    max_single_position_weight: float = 25.0,
    initial_cash: float = 100_000.0,
    position_size_pct: float = 0.20,
    persist: bool = True,
    repository: Any = None,
) -> Dict[str, Any]:
    """
    Backtest the concentration rule and record the verdict.
    回測集中度規則並記錄結論。

    Persists a `backtest_runs` row (with the buy-and-hold benchmark stored in
    `params`, which is where StrategyValidationService looks for it) and
    returns the metrics plus a pass/fail against ValidationThresholds.

    Returning a failure here is a legitimate outcome, not an error: it means
    the rule should not trade live, and the gate in AutomatedTradingService
    will keep it from doing so.
    回傳「未通過」是正當結果而非錯誤：代表該規則不應進行實盤交易，
    AutomatedTradingService 的關卡會據此阻擋。
    """
    from src.services.portfolio_backtest_engine import PortfolioBacktestEngine
    from src.services.strategy_validation_service import (
        STRATEGY_CONCENTRATION_REBALANCE,
        buy_and_hold_return_pct,
        evaluate_backtest,
    )

    signal_fn = concentration_trim_signal(
        max_single_position_weight=max_single_position_weight,
        position_size_pct=position_size_pct * 100,
    )

    engine = PortfolioBacktestEngine(
        initial_cash=initial_cash,
        position_size_pct=position_size_pct,
        # See concentration_trim_signal's docstring: a stoploss would desync
        # the closure's entry tracking from the engine's actual position.
        # 見上方 docstring：啟用停損會讓閉包的進場追蹤與引擎實際部位脫節。
        stoploss_pct=None,
    )
    result = engine.run(ticker, ohlcv, signal_fn)

    benchmark = buy_and_hold_return_pct(ohlcv)
    passed, failures = evaluate_backtest(
        metrics=result.metrics,
        initial_cash=initial_cash,
        final_cash=result.final_cash,
        buy_and_hold_return_pct=benchmark,
    )

    params = {
        "max_single_position_weight": max_single_position_weight,
        "position_size_pct": position_size_pct,
        "buy_and_hold_return_pct": benchmark,
        "bars": len(ohlcv.get("close", [])),
    }

    run_id = None
    if persist:
        repo = repository
        if repo is None:
            from src.repositories.backtest_repository import AlchemyBacktestRepository
            repo = AlchemyBacktestRepository()
        run_id = repo.save_run(
            user_id=user_id,
            ticker=ticker,
            strategy_name=STRATEGY_CONCENTRATION_REBALANCE,
            initial_cash=initial_cash,
            final_cash=result.final_cash,
            metrics=result.metrics,
            trades=result.trades,
            equity_curve=result.equity_curve,
            dates=result.dates,
            params=params,
        )

    return {
        "run_id": run_id,
        "ticker": ticker,
        "passed": passed,
        "failures": failures,
        "metrics": result.metrics,
        "initial_cash": initial_cash,
        "final_cash": result.final_cash,
        "buy_and_hold_return_pct": benchmark,
    }
