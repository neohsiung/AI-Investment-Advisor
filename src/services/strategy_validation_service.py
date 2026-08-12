"""
StrategyValidationService — the gate between a strategy and real money.
策略驗證關卡：策略與真實資金之間的閘門。

Why this exists / 為何需要
────────────────────────
As of 2026-08-10 this system was configured to trade a live eToro account
(`etoro_mode="real"`, `ai_trading_enabled=true`, no `TRADING_MODE` override)
with `auto_trade_threshold=75`, meaning any signal scoring >= 7.5/10
executed with no human in the loop. Meanwhile:

  - `backtest_runs` held **0 rows**. No strategy had ever been backtested.
  - `transactions` held **0 rows** with `entry_category='trade'`. The order
    path had never produced a fill.
  - The thing driving automated sells was not an alpha model at all. It was
    `_check_allocation_drift`: "if any position exceeds 25% of the
    portfolio, sell it down to 22.5%." That is a concentration-risk
    heuristic. Its expected return is unknown and was never measured.

So the system was one Redis restart away from trading real money on an
unvalidated rule. This module makes that impossible by construction: live
automated execution requires a stored backtest that cleared explicit
thresholds. Paper/demo mode is deliberately unaffected — that is where a
strategy earns its way to a live allocation.

**This does not predict profit.** No backtest can. It enforces that a
strategy was measured against history and cleared a stated bar before it is
allowed to risk capital. A strategy that fails the bar should not trade, and
"do not trade" is a valid, useful outcome.

2026-08-10 現況：系統設定為對實盤 eToro 帳戶交易，且分數 ≥ 7.5 即無人工核准
自動成交；但 backtest_runs 為 0 筆、從未有任何成交紀錄，而驅動自動賣出的只是
「單一部位超過 25% 就砍到 22.5%」的集中度風控啟發式，其期望報酬從未被量測。
本模組要求：實盤自動執行前，必須存在一筆通過明確門檻的回測紀錄。

**本模組不預測獲利**，任何回測都做不到。它只確保策略在動用資金前，曾以歷史
資料量測並通過既定標準。未達標的策略就不該交易——「不要交易」也是有效結論。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("StrategyValidation")

# The concentration-rebalance rule implemented by
# SentinelService._check_allocation_drift. Named so a backtest can be
# attributed to it and the live path can ask whether it passed.
# 對應 SentinelService._check_allocation_drift 的集中度再平衡規則。
STRATEGY_CONCENTRATION_REBALANCE = "concentration_rebalance"


class ValidationThresholds:
    """
    The bar a strategy must clear before it may trade live.
    策略可進行實盤交易前必須通過的標準。

    Deliberately conservative and deliberately explicit — these are policy,
    not discovered constants, and they should be argued with rather than
    tuned until something passes. Tuning them to admit a failing strategy
    defeats the point of the gate.
    這些是「政策」而非實測常數，應該被辯論而不是調到某個策略剛好通過為止。
    """

    # Risk-adjusted return. Below ~0.8 the edge is not distinguishable from
    # noise at the sample sizes a few years of daily bars provide.
    MIN_SHARPE = 0.8

    # Peak-to-trough loss. Past this, most people stop following the system
    # precisely when they most need to, which makes the backtest fiction.
    MAX_DRAWDOWN_PCT = 20.0

    # Must actually make money after fees and slippage. The engine already
    # charges both (portfolio_backtest_engine.PortfolioBacktestEngine).
    MIN_NET_RETURN_PCT = 0.0

    # Must beat holding the same asset. A strategy that trades all year to
    # underperform buy-and-hold is a cost generator, not an edge.
    MUST_BEAT_BUY_AND_HOLD = True

    # Below this, metrics are curve-fitted noise regardless of how good the
    # Sharpe looks.
    MIN_TRADES = 10


def evaluate_backtest(
    metrics: Dict[str, Any],
    initial_cash: float,
    final_cash: float,
    buy_and_hold_return_pct: Optional[float] = None,
    thresholds: type = ValidationThresholds,
) -> Tuple[bool, List[str]]:
    """
    Score one backtest against the thresholds.
    以門檻評估單次回測結果。

    Returns (passed, reasons). `reasons` lists every failure, not just the
    first, so a single run tells you everything that needs to improve.
    回傳 (是否通過, 原因清單)；列出所有未達標項目而非只有第一項。
    """
    failures: List[str] = []

    sharpe = _as_float(metrics.get("sharpe"))
    if sharpe is None or sharpe < thresholds.MIN_SHARPE:
        failures.append(
            f"Sharpe {_fmt(sharpe)} < required {thresholds.MIN_SHARPE}"
        )

    # max_drawdown_pct is reported as a magnitude by metrics_service; take
    # abs() so a sign convention change cannot silently pass a bad run.
    # metrics_service 以絕對值回報回撤；此處再取 abs()，避免正負號慣例變更時誤放行。
    drawdown = _as_float(metrics.get("max_drawdown_pct"))
    if drawdown is None or abs(drawdown) > thresholds.MAX_DRAWDOWN_PCT:
        failures.append(
            f"Max drawdown {_fmt(drawdown)}% > allowed {thresholds.MAX_DRAWDOWN_PCT}%"
        )

    if initial_cash <= 0:
        failures.append(f"initial_cash {initial_cash} is not positive; return is undefined")
        net_return_pct = None
    else:
        net_return_pct = (final_cash / initial_cash - 1) * 100
        if net_return_pct <= thresholds.MIN_NET_RETURN_PCT:
            failures.append(
                f"Net return {net_return_pct:.2f}% <= required "
                f"{thresholds.MIN_NET_RETURN_PCT}% (after fees and slippage)"
            )

    total_trades = _as_float(metrics.get("total_trades"))
    if total_trades is None or total_trades < thresholds.MIN_TRADES:
        failures.append(
            f"Only {_fmt(total_trades)} trades < required {thresholds.MIN_TRADES}; "
            f"metrics are not statistically meaningful"
        )

    if thresholds.MUST_BEAT_BUY_AND_HOLD:
        if buy_and_hold_return_pct is None:
            failures.append(
                "No buy-and-hold benchmark supplied; cannot show the strategy adds value"
            )
        elif net_return_pct is not None and net_return_pct <= buy_and_hold_return_pct:
            failures.append(
                f"Net return {net_return_pct:.2f}% <= buy-and-hold "
                f"{buy_and_hold_return_pct:.2f}%; the trading adds cost, not edge"
            )

    return (not failures), failures


def buy_and_hold_return_pct(ohlcv: Dict[str, List[Any]]) -> Optional[float]:
    """
    Benchmark return for holding the asset across the same bars.
    同期間單純持有該資產的基準報酬率。
    """
    closes = ohlcv.get("close") or []
    if len(closes) < 2:
        return None
    first, last = float(closes[0]), float(closes[-1])
    if first <= 0:
        return None
    return (last / first - 1) * 100


class StrategyValidationService:
    """
    Answers: may this strategy trade real money right now?
    回答：此策略現在是否可以動用真實資金？
    """

    def __init__(self, repository: Any = None):
        self._repository = repository

    @property
    def repository(self):
        if self._repository is None:
            from src.repositories.backtest_repository import AlchemyBacktestRepository
            self._repository = AlchemyBacktestRepository()
        return self._repository

    def is_validated(self, user_id: str, strategy_name: str) -> Tuple[bool, str]:
        """
        True when a stored run for this strategy cleared the thresholds.
        當此策略存有通過門檻的回測紀錄時回傳 True。

        Re-evaluates the stored metrics rather than trusting a flag written at
        save time, so tightening ValidationThresholds immediately revokes
        approval for runs that no longer qualify — no re-run required.
        重新評估既有指標而非信任存檔時寫下的旗標；因此門檻一調嚴，不再合格的
        紀錄會立即失效，無需重跑。
        """
        try:
            runs = self.repository.list_runs(user_id=user_id, limit=100)
        except Exception as e:
            # Fail closed: an unreadable backtest history is not evidence of a
            # validated strategy.
            # Fail-closed：讀不到回測歷史，不能當作策略已驗證。
            logger.error(f"Strategy validation lookup failed for {strategy_name}: {e}")
            return False, f"backtest history unavailable ({type(e).__name__})"

        matching = [r for r in runs if r.get("strategy_name") == strategy_name]
        if not matching:
            return False, (
                f"no backtest on record for strategy '{strategy_name}' — "
                f"run one and clear the thresholds before trading it live"
            )

        for run in matching:
            metrics = run.get("metrics") or {}
            params = run.get("params") or {}
            if isinstance(metrics, str) or isinstance(params, str):
                import json
                if isinstance(metrics, str):
                    metrics = json.loads(metrics)
                if isinstance(params, str):
                    params = json.loads(params)
            passed, _ = evaluate_backtest(
                metrics=metrics,
                initial_cash=float(run.get("initial_cash") or 0),
                final_cash=float(run.get("final_cash") or 0),
                buy_and_hold_return_pct=_as_float(params.get("buy_and_hold_return_pct")),
            )
            if passed:
                return True, f"validated by backtest run {run.get('id')}"

        return False, (
            f"{len(matching)} backtest run(s) on record for '{strategy_name}', "
            f"none cleared the thresholds"
        )


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.2f}"
