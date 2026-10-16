"""
Evaluate a strategy against its benchmark: net of costs, with the multiple-testing correction and a
"how long until live data could prove it" estimate. Pure functions; data loading lives in the caller.
以扣成本、多重檢定校正與『實盤需多久才可能證明』評估策略；純函式，資料載入由呼叫端負責。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

import pandas as pd

from src.config.mission import load_mission
from src.evaluation.performance import (
    backtest_weights, compute_performance, deflated_sharpe_ratio, purged_walk_forward_splits, years_to_significance,
)


def evaluate_strategy(
    prices: pd.DataFrame,
    strategy: Callable[[pd.DataFrame], pd.DataFrame],
    benchmark: str = "SPY",
    cost_bps: float = 5.0,
    n_trials: int = 1,
    n_splits: int = 4,
) -> Dict[str, Any]:
    """Returns full-sample and walk-forward (out-of-sample windows) statistics plus the promotion verdict
    from config/mission.yaml. `n_trials` MUST count every variant ever tried (multiple testing).
    回傳全樣本與 walk-forward（樣本外視窗）統計，以及依 mission.yaml 的晉升判定；n_trials 必須計入所有試過的變體。"""
    m = load_mission()
    weights = strategy(prices)
    net = backtest_weights(prices, weights, cost_bps=cost_bps, lag=1)
    bench = prices[benchmark].pct_change().fillna(0.0)
    # skip the warm-up before the strategy could hold anything
    first = weights.dropna(how="all").index.min()
    start = net.index.get_loc(first) + 2          # signal -> trade (t+1) -> first return (t+2), see backtest_weights
    net, bench = net.iloc[start:], bench.iloc[start:]
    full = compute_performance(net, bench)
    oos = []
    try:
        for sp in purged_walk_forward_splits(len(net), n_splits, embargo=5, min_train=min(252, len(net) // 2)):
            idx = net.index[list(sp["test"])]
            oos.append(compute_performance(net.loc[idx], bench.loc[idx]).to_dict())
    except ValueError:
        pass
    ex = net - bench
    sr_period = float(ex.mean() / ex.std(ddof=1)) if ex.std(ddof=1) > 0 else 0.0
    dsr = deflated_sharpe_ratio(sr_period, full.n_obs, full.skew, full.kurtosis, n_trials=n_trials)
    promo = m.promotion
    verdict = {
        "dsr": round(dsr, 4), "dsr_required": promo.min_deflated_sharpe,
        "t_stat": round(full.t_stat_excess, 3), "t_required": promo.min_t_stat,
        "promotable": bool(dsr > promo.min_deflated_sharpe and full.t_stat_excess >= promo.min_t_stat),
        "years_for_live_t3": round(years_to_significance(full.information_ratio, promo.min_t_stat), 1),
        "n_trials": n_trials,
    }
    return {"full_sample": full.to_dict(), "out_of_sample_windows": oos, "verdict": verdict,
            "cost_bps": cost_bps, "start": str(net.index[0].date()), "end": str(net.index[-1].date())}
