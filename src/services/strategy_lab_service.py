"""
Strategy lab: the closed evaluation loop with honest multiple-testing accounting (0-LLM).
策略實驗室：具誠實多重檢定記帳的封閉評估迴圈（0-LLM）。

Every distinct (family, params) variant is a TRIAL, recorded once in `strategy_trials`; the cumulative trial count N
feeds the Deflated Sharpe Ratio of every later evaluation, so searching more makes promotion HARDER, not easier.
A variant becomes `shadow_candidate` only when it clears mission.promotion (DSR and t-stat) on real data, net of
costs, relative to the benchmark. It never gets capital from here: capital requires forward shadow evidence.
每個不同的 (family, params) 變體是一次試驗，只記一次；累計試驗數 N 會進入之後所有評估的 DSR，因此搜尋越多、晉升越難。
通過 mission.promotion（DSR 與 t 值）者才標為 shadow_candidate；本服務絕不配置資金（資金需要前向 shadow 證據）。
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text

from src.evaluation.runner import evaluate_strategy
from src.evaluation.strategies import momentum_tilt

logger = logging.getLogger("StrategyLab")

# Pre-registered families and grids. Adding a variant here increases N for everyone (by design).
# 預先登記的策略族群與參數網格；新增變體會提高所有人的 N（刻意設計）。
FAMILIES: Dict[str, Dict[str, Any]] = {
    "momentum_tilt": {
        "fn": momentum_tilt,
        "grid": {"top_k": [2, 3, 5], "lookback": [63, 126, 252], "benchmark_weight": [0.7]},
    },
}


def quarter_bounds(now: Optional[datetime] = None) -> tuple:
    """[start, end) of the calendar quarter containing `now` (UTC). / 包含 now 的日曆季（UTC）半開區間。"""
    now = now or datetime.now(timezone.utc)
    q0 = ((now.month - 1) // 3) * 3 + 1
    start = datetime(now.year, q0, 1, tzinfo=timezone.utc)
    end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc) if q0 == 10 else datetime(now.year, q0 + 3, 1, tzinfo=timezone.utc)
    return start, end


def params_hash(family: str, params: Dict[str, Any]) -> str:
    return hashlib.sha256(f"{family}|{json.dumps(params, sort_keys=True)}".encode()).hexdigest()[:32]


def expand_grid(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = sorted(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]


class StrategyLabService:
    def __init__(self, engine: Any = None, families: Optional[Dict[str, Dict[str, Any]]] = None,
                 max_new_trials_per_quarter: Optional[int] = None):
        if engine is None:
            from src.data.database import get_db_engine
            engine = get_db_engine()
        self.engine = engine
        self.families = families or FAMILIES
        if max_new_trials_per_quarter is None:
            # Single source of truth: mission.yaml budgets (never copied here). / 單一真相：mission.yaml。
            from src.config.mission import load_mission
            max_new_trials_per_quarter = load_mission().budgets.max_hypothesis_trials_per_quarter
        self.max_new_trials_per_quarter = int(max_new_trials_per_quarter)

    # ── ledger ────────────────────────────────────────────────────────────────
    def trial_count(self) -> int:
        with self.engine.connect() as c:
            return int(c.execute(text("SELECT COUNT(*) FROM strategy_trials")).scalar() or 0)

    def quarter_trial_count(self, now: Optional[datetime] = None) -> int:
        """Trials FIRST seen in the current calendar quarter (re-evaluations do not count). / 本季首次出現的試驗數。"""
        start, end = quarter_bounds(now)
        with self.engine.connect() as c:
            return int(c.execute(text("SELECT COUNT(*) FROM strategy_trials WHERE first_eval_at >= :s AND first_eval_at < :e"),
                                 {"s": start.replace(tzinfo=None), "e": end.replace(tzinfo=None)}).scalar() or 0)

    def _is_registered(self, h: str) -> bool:
        with self.engine.connect() as c:
            return c.execute(text("SELECT 1 FROM strategy_trials WHERE params_hash = :h"), {"h": h}).fetchone() is not None

    def _register(self, h: str, family: str, params: Dict[str, Any]) -> bool:
        """Insert the trial if new. Returns True when it is a NEW trial (N grows). / 新試驗回傳 True（N 增加）。"""
        with self.engine.begin() as c:
            exists = c.execute(text("SELECT 1 FROM strategy_trials WHERE params_hash = :h"), {"h": h}).fetchone()
            if exists:
                return False
            c.execute(text("INSERT INTO strategy_trials (params_hash, family, params_json, n_evals) VALUES (:h, :f, :p, 0)"),
                      {"h": h, "f": family, "p": json.dumps(params, sort_keys=True)})
            return True

    def _save(self, h: str, metrics: Dict[str, Any], verdict: Dict[str, Any], status: str) -> None:
        with self.engine.begin() as c:
            c.execute(text("UPDATE strategy_trials SET last_eval_at = :t, n_evals = n_evals + 1, last_metrics = :m, "
                           "last_verdict = :v, status = :s WHERE params_hash = :h"),
                      {"t": datetime.now(timezone.utc), "m": json.dumps(metrics), "v": json.dumps(verdict), "s": status, "h": h})

    # ── loop ──────────────────────────────────────────────────────────────────
    def run(self, prices: Any, benchmark: str = "SPY", cost_bps: float = 10.0) -> Dict[str, Any]:
        """Evaluate every pre-registered variant on `prices`. / 以給定價格評估所有預先登記的變體。"""
        # Register ALL variants first so N reflects the whole search space before any verdict is computed.
        # 先登記全部變體，讓 N 在任何判定之前就涵蓋整個搜尋空間。
        plan = []
        deferred = 0
        budget_left = max(0, self.max_new_trials_per_quarter - self.quarter_trial_count())
        for fam, spec in self.families.items():
            for params in expand_grid(spec["grid"]):
                h = params_hash(fam, params)
                if not self._is_registered(h):
                    # A NEW trial: it spends this quarter's budget. Over budget => not registered, not evaluated
                    # (so N is not inflated by trials we never look at) and reported loudly.
                    # 新試驗會消耗本季預算；超額者不登記也不評估（N 不被灌水），並明確回報。
                    if budget_left <= 0:
                        deferred += 1
                        continue
                    budget_left -= 1
                self._register(h, fam, params)
                plan.append((fam, spec["fn"], params, h))
        if deferred:
            logger.warning("StrategyLab: quarterly trial cap (%d) reached; %d new variants deferred to next quarter",
                           self.max_new_trials_per_quarter, deferred)
        n_trials = self.trial_count()

        results, promotable = [], []
        for fam, fn, params, h in plan:
            try:
                strat: Callable = (lambda p, _fn=fn, _kw=params: _fn(p, benchmark=benchmark, **_kw))
                res = evaluate_strategy(prices, strat, benchmark=benchmark, cost_bps=cost_bps, n_trials=n_trials)
            except Exception as e:
                logger.warning("evaluation failed for %s %s: %s", fam, params, e)
                self._save(h, {}, {"error": str(e)[:200]}, "error")
                results.append({"family": fam, "params": params, "status": "error", "error": str(e)[:200]})
                continue
            status = "shadow_candidate" if res["verdict"]["promotable"] else "rejected"
            self._save(h, res["full_sample"], res["verdict"], status)
            row = {"family": fam, "params": params, "status": status,
                   "ann_excess_return": round(res["full_sample"]["ann_excess_return"], 4),
                   "t_stat": res["verdict"]["t_stat"], "dsr": res["verdict"]["dsr"]}
            results.append(row)
            if status == "shadow_candidate":
                promotable.append(row)
        logger.info("StrategyLab: %d variants, N=%d, %d shadow candidates", len(plan), n_trials, len(promotable))
        return {"n_trials_total": n_trials, "variants_evaluated": len(plan), "shadow_candidates": promotable, "results": results,
                "trials_deferred": deferred, "cap_reached": deferred > 0}

    def list_trials(self) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(text("SELECT family, params_json, status, n_evals, first_eval_at, last_eval_at, last_verdict "
                                  "FROM strategy_trials ORDER BY family, params_json")).fetchall()
        return [{"family": r[0], "params": json.loads(r[1]), "status": r[2], "n_evals": r[3],
                 "first_eval_at": str(r[4]), "last_eval_at": str(r[5]), "verdict": json.loads(r[6]) if r[6] else None} for r in rows]
