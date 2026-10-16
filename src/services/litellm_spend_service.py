"""
LiteLLM real-spend collector / reader.
LiteLLM 真實花費收集與查詢服務。

Why: `llm_usage_logs.total_cost_usd` is priced from the benchmark list prices in
config/llm_tiers.yaml, so it overstated real spend ~7x (2026-10 audit: ~$60 vs ~$8.4
billed over 14 days). LiteLLM bills per virtual key; this advisor's key may call
`/key/info` (cumulative spend inside the current budget period) but not the admin-only
`/spend/logs`. The collector therefore polls `/key/info` and books the positive delta into
`llm_real_cost_daily`; the reader sums those days. History before the first poll is
backfilled once from the LiteLLM ledger by an operator (see scripts/backfill_llm_real_cost.py).
原因：llm_usage_logs 以商用定價估算而高估約 7 倍。LiteLLM 依虛擬金鑰計費；本金鑰可呼叫 /key/info
（當期累計花費），不可呼叫僅限管理員的 /spend/logs。故輪詢 /key/info，將正向差額記入每日表。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta, datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger("LiteLLMSpendService")

DEFAULT_BASE_URL = "http://shared_litellm:4000"
# Fraction of days in the window that must have a booked row before real cost is trusted.
# 視窗內至少要有這個比例的日子有實際記帳，才採信真實成本。
MIN_COVERAGE = 0.8


class LiteLLMSpendService:
    def __init__(
        self,
        engine: Any = None,
        base_url: Optional[str] = None,
        http_get: Optional[Callable[..., Any]] = None,
        key_provider: Optional[Callable[[], Optional[str]]] = None,
        key_alias: str = "advisor-prod",
    ):
        if engine is None:
            from src.data.database import get_db_engine
            engine = get_db_engine()
        self.engine = engine
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._http_get = http_get
        self._key_provider = key_provider
        self.key_alias = key_alias

    # ── API access ───────────────────────────────────────────────────────────
    def _api_key(self) -> Optional[str]:
        if self._key_provider:
            return self._key_provider()
        from src.services.llm_credential_cipher import LLMCredentialCipher
        with self.engine.connect() as conn:
            enc = conn.execute(
                text("SELECT encrypted_api_key FROM llm_providers WHERE provider_code = 'openrouter' "
                     "AND enabled = TRUE ORDER BY updated_at DESC LIMIT 1")
            ).scalar()
        return LLMCredentialCipher().decrypt(enc) if enc else None

    def fetch_key_info(self) -> Dict[str, Any]:
        """Current-period spend and budget of this advisor's LiteLLM key. Raises on failure.
        取得本金鑰當期累計花費與預算；失敗時拋出例外（不回傳假值）。"""
        key = self._api_key()
        if not key:
            raise RuntimeError("no LiteLLM key available")
        getter = self._http_get
        if getter is None:
            import requests
            getter = requests.get
        resp = getter(f"{self.base_url}/key/info", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"LiteLLM /key/info HTTP {resp.status_code}")
        info = (resp.json() or {}).get("info") or {}
        if "spend" not in info:
            raise RuntimeError("LiteLLM /key/info response has no spend field")
        return {
            "spend": float(info.get("spend") or 0.0),
            "max_budget": info.get("max_budget"),
            "budget_duration": info.get("budget_duration"),
            "budget_reset_at": info.get("budget_reset_at"),
            "key_alias": info.get("key_alias") or self.key_alias,
        }

    # ── Collector ────────────────────────────────────────────────────────────
    def collect(self, today: Optional[date] = None) -> Dict[str, Any]:
        """Poll once and book the delta since the last poll into today's row.
        輪詢一次，把與上次的差額記入今日列。首次僅建立基準，不歸屬歷史花費。"""
        today = today or datetime.now(timezone.utc).date()
        info = self.fetch_key_info()
        alias = info["key_alias"]
        spend, reset_at = info["spend"], str(info.get("budget_reset_at") or "")
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT last_spend, last_reset_at FROM llm_real_cost_state WHERE key_alias = :a"),
                {"a": alias},
            ).fetchone()
            if row is None:
                delta, note = 0.0, "baseline_created"
            elif str(row[1] or "") == reset_at:
                delta, note = max(0.0, spend - float(row[0])), "delta"
            else:
                # Budget period rolled over: spend restarted from 0, so all of it is new.
                # 預算週期重置：花費自 0 起算，全數視為新增。
                delta, note = spend, "period_reset"
            if delta > 0:
                conn.execute(
                    text("""
                        INSERT INTO llm_real_cost_daily (day, key_alias, spend_usd, source)
                        VALUES (:d, :a, :x, 'litellm_key_info')
                        ON CONFLICT (day, key_alias)
                        DO UPDATE SET spend_usd = llm_real_cost_daily.spend_usd + EXCLUDED.spend_usd,
                                      updated_at = CURRENT_TIMESTAMP
                    """),
                    {"d": today, "a": alias, "x": round(delta, 6)},
                )
            conn.execute(
                text("""
                    INSERT INTO llm_real_cost_state (key_alias, last_spend, last_reset_at)
                    VALUES (:a, :s, :r)
                    ON CONFLICT (key_alias)
                    DO UPDATE SET last_spend = EXCLUDED.last_spend, last_reset_at = EXCLUDED.last_reset_at,
                                  updated_at = CURRENT_TIMESTAMP
                """),
                {"a": alias, "s": spend, "r": reset_at},
            )
        logger.info("LiteLLM spend collected: %s delta=$%.4f (%s)", alias, delta, note)
        return {"key_alias": alias, "delta_usd": delta, "note": note, "period_spend": spend,
                "max_budget": info.get("max_budget"), "budget_reset_at": info.get("budget_reset_at")}

    # ── Reader ───────────────────────────────────────────────────────────────
    def get_spend(self, days: int, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """Real billed spend over the last `days` days (today included), or None when coverage
        is too thin to trust (caller must then label its estimate as an estimate).
        近 days 日（含今日）的真實計費花費；覆蓋不足時回傳 None，呼叫端須標示為估算。"""
        days = max(1, int(days))
        today = today or datetime.now(timezone.utc).date()
        since = today - timedelta(days=days - 1)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("SELECT COALESCE(SUM(spend_usd), 0), COUNT(DISTINCT day) FROM llm_real_cost_daily "
                         "WHERE key_alias = :a AND day >= :since AND day <= :today"),
                    {"a": self.key_alias, "since": since, "today": today},
                ).fetchone()
        except Exception as e:
            logger.warning("LiteLLM real-cost read failed (%s); caller will fall back to estimate", e)
            return None
        total, covered = float(row[0] or 0.0), int(row[1] or 0)
        if covered < MIN_COVERAGE * days:
            return None
        return {"total_cost": total, "days_covered": covered, "window_days": days, "source": "litellm_billed"}
