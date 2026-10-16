"""
Mission watchdog — evaluates the kill criteria in config/mission.yaml against real data (0-LLM).
使命看門狗 — 以真實資料評估 config/mission.yaml 的 kill criteria（0-LLM）。

Each criterion returns one of: ok | breach | not_measurable. "not_measurable" is explicit on purpose: a check that
cannot run is reported as such, never as "ok" (fail-silent rule). The watchdog only REPORTS (alert + API); it does
not flip trading off by itself. Auto-halt is an R3 behaviour behind `mission_auto_halt_enabled` (default false).
每條標準回傳 ok | breach | not_measurable；無法量測就明說，絕不假裝 ok。看門狗只回報（警報＋API），
不會自行停止交易；自動停機屬 R3 行為，由 mission_auto_halt_enabled（預設 false）控制。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.config.mission import load_mission

logger = logging.getLogger("MissionWatchdog")

MIN_HISTORY_DAYS_FOR_ALPHA = 252


def _row(kid: str, name: str, status: str, value: Optional[float], threshold: float, unit: str, note: str = "") -> Dict[str, Any]:
    return {"id": kid, "name": name, "status": status, "value": None if value is None else round(value, 4),
            "threshold": threshold, "unit": unit, "note": note}


class MissionWatchdogService:
    def __init__(self, user_id: str, engine: Any = None, nav_usd: Optional[float] = None,
                 llm_cost_30d_usd: Optional[float] = None, monthly_subscription_usd: Optional[float] = None,
                 local_cash_usd: Optional[float] = None, broker_cash_usd: Optional[float] = None):
        self.user_id = user_id
        self._engine = engine
        # Injection points (tests / callers that already hold the numbers). None -> read from the system.
        self._nav = nav_usd
        self._llm30 = llm_cost_30d_usd
        self._sub = monthly_subscription_usd
        self._local_cash = local_cash_usd
        self._broker_cash = broker_cash_usd

    @property
    def engine(self):
        if self._engine is None:
            from src.data.database import get_db_engine
            self._engine = get_db_engine()
        return self._engine

    # ── inputs ────────────────────────────────────────────────────────────────
    def _latest_snapshot(self) -> Optional[Dict[str, float]]:
        with self.engine.connect() as c:
            r = c.execute(text("SELECT total_nlv, cash_balance, date FROM daily_snapshots WHERE user_id = :u "
                               "AND total_nlv IS NOT NULL ORDER BY date DESC LIMIT 1"), {"u": self.user_id}).fetchone()
        return None if r is None else {"nav": float(r[0]), "cash": float(r[1] or 0.0), "date": r[2]}

    def _trades(self, since: date) -> List[Dict[str, Any]]:
        with self.engine.connect() as c:
            rows = c.execute(text("SELECT trade_date, ticker, action, amount FROM transactions WHERE user_id = :u "
                                  "AND entry_category = 'trade' AND trade_date >= :d"), {"u": self.user_id, "d": since}).fetchall()
        return [{"date": r[0], "ticker": r[1], "action": r[2], "amount": float(r[3] or 0.0)} for r in rows]

    # ── evaluation ────────────────────────────────────────────────────────────
    def evaluate(self, today: Optional[date] = None) -> Dict[str, Any]:
        m = load_mission()
        k = {c.id: c for c in m.kill_criteria}
        today = today or date.today()
        results: List[Dict[str, Any]] = []

        nav = self._nav
        snap = None
        if nav is None:
            try:
                snap = self._latest_snapshot()
                nav = snap["nav"] if snap else None
            except Exception as e:
                logger.warning("watchdog: cannot read NAV: %s", e)

        # K1 cost ratio (annualised real LLM cost + subscriptions) / NAV
        c1 = k["K1"]
        try:
            llm30 = self._llm30
            if llm30 is None:
                from src.services.token_logger_service import TokenLoggerService
                sp = TokenLoggerService().get_user_spending(self.user_id, days=30)
                if sp.get("cost_source") != "litellm_billed":
                    raise RuntimeError("real billed LLM cost unavailable (estimate only)")
                llm30 = float(sp["total_cost"])
            sub = self._sub if self._sub is not None else 0.0
            if self._sub is None:
                from src.services.settings_service import SettingsService
                sub = float(SettingsService(user_id=self.user_id).get_setting("monthly_data_subscription_cost_usd", 0.0) or 0.0)
            if not nav or nav <= 0:
                raise RuntimeError("NAV unavailable")
            annual = llm30 * (365.0 / 30.0) + sub * 12.0
            ratio = annual / nav * 100.0
            results.append(_row("K1", c1.name, "breach" if ratio > c1.threshold else "ok", ratio, c1.threshold, c1.unit,
                                f"annualised cost ${annual:.0f} on NAV ${nav:.0f}"))
        except Exception as e:
            results.append(_row("K1", c1.name, "not_measurable", None, c1.threshold, c1.unit, str(e)))

        # K2 ledger vs broker cash
        c2 = k["K2"]
        try:
            local, broker = self._local_cash, self._broker_cash
            if local is None or broker is None:
                from src.repositories.transaction_repository import AlchemyTransactionRepository
                local = AlchemyTransactionRepository().get_cash_balance(self.user_id)
                snap = snap or self._latest_snapshot()
                broker = snap["cash"] if snap else None
            if broker is None:
                raise RuntimeError("no broker-anchored snapshot")
            diff = abs(float(local) - float(broker))
            results.append(_row("K2", c2.name, "breach" if diff > 1.0 else "ok", diff, 1.0, "usd_mismatch_now",
                                f"local ledger cash ${float(local):.2f} vs broker ${float(broker):.2f} (persistence over days not tracked yet)"))
        except Exception as e:
            results.append(_row("K2", c2.name, "not_measurable", None, c2.threshold, c2.unit, str(e)))

        # K3 / K4 from the trade ledger (conservative: every sell counts, safety exits are not separable yet)
        c3, c4 = k["K3"], k["K4"]
        try:
            trades = self._trades(today - timedelta(days=30))
            if not nav or nav <= 0:
                raise RuntimeError("NAV unavailable")
            by_day: Dict[date, Dict[str, Any]] = {}
            for t in trades:
                if t["action"] == "SELL":
                    d = by_day.setdefault(t["date"], {"amt": 0.0, "tickers": set()})
                    d["amt"] += t["amount"]; d["tickers"].add(t["ticker"])
            worst_pct = max((d["amt"] / nav * 100.0 for d in by_day.values()), default=0.0)
            worst_n = max((len(d["tickers"]) for d in by_day.values()), default=0)
            max_n = m.invariants.max_nonsafety_sells_per_day
            b3 = worst_pct > c3.threshold or worst_n > max_n
            results.append(_row("K3", c3.name, "breach" if b3 else "ok", worst_pct, c3.threshold, c3.unit,
                                f"worst day in 30d: {worst_n} tickers (limit {max_n}); safety exits not separated"))
            turnover = (sum(t["amount"] for t in trades) / 2.0) / nav * (365.0 / 30.0)
            results.append(_row("K4", c4.name, "breach" if turnover > c4.threshold else "ok", turnover, c4.threshold, c4.unit,
                                "annualised from the last 30 days"))
        except Exception as e:
            results.append(_row("K3", c3.name, "not_measurable", None, c3.threshold, c3.unit, str(e)))
            results.append(_row("K4", c4.name, "not_measurable", None, c4.threshold, c4.unit, str(e)))

        # K5 / K6 / K7: honest about what cannot be measured yet
        c5, c6, c7 = k["K5"], k["K6"], k["K7"]
        results.append(_row("K5", c5.name, "not_measurable", None, c5.threshold, c5.unit,
                            f"needs >= {MIN_HISTORY_DAYS_FOR_ALPHA} broker-anchored days and an active-sleeve attribution (not built yet)"))
        results.append(_row("K6", c6.name, "not_measurable", None, c6.threshold, c6.unit,
                            "enforced statically by tests/invariants and test_fail_silent_policy, not at runtime"))
        results.append(_row("K7", c7.name, "not_measurable", None, c7.threshold, c7.unit,
                            "no walk-forward evaluator with DSR/trial accounting exists yet (Phase 3C)"))

        breaches = [r for r in results if r["status"] == "breach"]
        return {
            "as_of": today.isoformat(),
            "nav_usd": nav,
            "overall": "BREACH" if breaches else ("OK" if all(r["status"] == "ok" for r in results) else "PARTIAL"),
            "breaches": [r["id"] for r in breaches],
            "criteria": results,
            "mission_version": m.version,
        }
