"""
Benchmark parking: keep idle capital in the mission benchmark instead of cash (config/mission.yaml).
基準停泊：把閒置資金放在使命基準而非現金。

Why: sitting in cash is itself a bet against the benchmark (the account lost ~$1,670 of "excess" doing nothing while
the market moved). Parking makes excess return measure only the value of ACTIVE decisions.
Safety: disabled by default (`benchmark_parking_enabled`); never sells the benchmark; ramps in with a per-run cap;
only buys inside the tradable-capital cap (capital_policy) and keeps the active sleeve's cash reserved; band
around the target prevents churn.
原因：留在現金本身就是押注基準會跌。停泊讓『超額報酬』只衡量主動決策的價值。
安全：預設關閉；絕不賣出基準；每次有金額上限逐步建立；只在可交易資本上限內買入並為主動部位保留現金；目標帶寬避免來回交易。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.config.mission import load_mission
from src.services.core_holdings import is_core, normalize_symbol

logger = logging.getLogger("BenchmarkParking")

MIN_ORDER_USD = 10.0


def plan_parking(
    nlv: float,
    cash: float,
    tradable: float,
    benchmark_value: float,
    other_positions_value: float,
    benchmark_weight_pct: float,
    max_order_usd: float,
    min_gap_usd: float,
) -> Dict[str, Any]:
    """Pure sizing. Returns {action: BUY|HOLD, amount_usd, reason, ...}; never SELL. / 純計算：只可能 BUY 或 HOLD。"""
    out: Dict[str, Any] = {"action": "HOLD", "amount_usd": 0.0}
    if nlv <= 0 or tradable <= 0:
        out["reason"] = "no tradable capital"
        return out
    target = tradable * benchmark_weight_pct / 100.0
    gap = target - benchmark_value
    band = max(min_gap_usd, 0.02 * tradable)
    # Cash that is NOT ours to use: the part of the account outside the tradable cap, plus the cash the active
    # sleeve (the remaining share of tradable capital) still needs.
    untouchable = max(0.0, nlv - tradable)
    active_budget = tradable * (1.0 - benchmark_weight_pct / 100.0)
    active_reserve = max(0.0, active_budget - other_positions_value)
    usable_cash = max(0.0, cash - untouchable - active_reserve)
    out.update({"target_value": round(target, 2), "benchmark_value": round(benchmark_value, 2), "gap": round(gap, 2),
                "band": round(band, 2), "usable_cash": round(usable_cash, 2)})
    if gap <= band:
        out["reason"] = f"within band (gap ${gap:.2f} <= ${band:.2f})"
        return out
    amount = round(min(gap, max_order_usd, usable_cash), 2)
    if amount < MIN_ORDER_USD:
        out["reason"] = f"usable amount ${amount:.2f} below the ${MIN_ORDER_USD:.0f} broker minimum"
        return out
    out.update({"action": "BUY", "amount_usd": amount, "reason": f"park ${amount:.2f} toward target ${target:.2f}"})
    return out


class BenchmarkParkingService:
    def __init__(self, user_id: str, settings_service: Any = None, broker: Any = None, executor: Any = None):
        self.user_id = user_id
        if settings_service is None:
            from src.services.settings_service import SettingsService
            settings_service = SettingsService(user_id=user_id)
        self.settings = settings_service
        self._broker = broker
        self._executor = executor

    def _flag(self, key: str, default: bool) -> bool:
        v = self.settings.get_setting(key, default)
        return v is True or str(v).lower() in ("true", "1")

    def _num(self, key: str, default: float) -> float:
        try:
            return float(self.settings.get_setting(key, default))
        except (TypeError, ValueError):
            logger.warning("Invalid setting %s; using %s", key, default)
            return default

    async def build_plan(self) -> Dict[str, Any]:
        from src.services.capital_policy import tradable_capital

        broker = self._broker
        if broker is None:
            from src.services.broker_factory import BrokerFactory
            broker = BrokerFactory.get_broker(self.user_id)
        if broker is None:
            return {"action": "HOLD", "amount_usd": 0.0, "reason": "no broker", "_error": True}
        account = await broker.get_account()
        positions = await broker.get_positions()
        if not account or float(account.total_equity or 0) <= 0:
            return {"action": "HOLD", "amount_usd": 0.0, "reason": "account unreadable", "_error": True}
        bench = other = 0.0
        for p in positions or []:
            val = float(getattr(p, "market_value", 0.0) or 0.0)
            if is_core(getattr(p, "symbol", "")):
                bench += val
            else:
                other += val
        nlv = float(account.total_equity)
        m = load_mission()
        plan = plan_parking(
            nlv=nlv, cash=float(account.available_cash or 0.0),
            tradable=tradable_capital(self.user_id, nlv),
            benchmark_value=bench, other_positions_value=other,
            benchmark_weight_pct=m.invariants.min_benchmark_weight_pct,
            max_order_usd=self._num("benchmark_parking_max_order_usd", 250.0),
            min_gap_usd=self._num("benchmark_parking_min_gap_usd", 50.0),
        )
        plan["benchmark"] = m.objective.benchmark
        plan["enabled"] = self._flag("benchmark_parking_enabled", False)
        return plan

    async def run(self) -> Dict[str, Any]:
        plan = await self.build_plan()
        if plan.get("_error") or plan["action"] != "BUY":
            plan["executed"] = False
            return plan
        if not plan["enabled"]:
            plan["executed"] = False
            plan["reason"] = "benchmark_parking_enabled is off — dry run only; " + plan["reason"]
            return plan
        executor = self._executor
        if executor is None:
            from src.services.automated_trading_service import AutomatedTradingService
            from src.services.notification_service import NotificationService
            executor = AutomatedTradingService(
                settings_repo=self.settings.settings_repo,
                notification_service=NotificationService.create_with_settings(settings_service=self.settings, user_id=self.user_id),
            )
        res = await executor.execute_benchmark_parking(
            self.user_id, plan["amount_usd"], f"Benchmark parking: {plan['reason']}"
        )
        plan["executed"] = res.get("status") in ("success", "executed", "pending")
        plan["execution"] = {k: res.get(k) for k in ("status", "reason", "order_id")}
        if not plan["executed"]:
            logger.warning("Benchmark parking order not executed: %s", plan["execution"])
        return plan
