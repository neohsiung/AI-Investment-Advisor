"""
CalendarBlackoutService — 宏觀事件與財報日避開守衛
==================================================
職責：
1. 個股財報日前後避開視窗 (Earnings Blackout Window)：
   - 下單/建倉前檢測候選標的是否即將於 24~48 小時內發布財報（或發布後 24 小時內），
     暫緩開倉以規避二元財報波動與引申波動率 (IV) 崩跌風險。
   - 整合 Finnhub 官方財報日曆 API，並以 Redis 分散式快取 (TTL 12h) 降低外部開銷。
2. 重大宏觀事件避開視窗 (High-Impact Macro Calendar Blackout Window)：
   - 檢測聯準會利率決議 (FOMC)、消費者物價指數 (CPI)、非農就業報告 (NFP) 前後保護視窗
     （預設發布前 60 分鐘至發布後 30 分鐘），暫緩全市場市價建倉，防範流動性真空與劇烈滑點。
3. 嚴格符合 Fail-Safe / Fail-Silent 準則：外部日曆異常時平滑降級，不阻塞例行交易流程。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional, Tuple
import pytz
import httpx

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("CalendarBlackoutService")

# Redis 快取鍵前綴
_REDIS_EARNINGS_KEY_PREFIX = "macro_calendar:earnings"
_REDIS_MACRO_KEY_PREFIX = "macro_calendar:macro_events"
_CACHE_TTL_SECONDS = 43200  # 12 小時


@dataclass
class BlackoutDecision:
    """
    避開守衛評估決策
    """
    is_blackout: bool
    reason: str
    event_type: str = "NONE"  # "NONE", "EARNINGS", "MACRO"
    event_name: Optional[str] = None
    event_time: Optional[str] = None
    timing: Optional[str] = None  # "bmo" (盤前), "amc" (盤後), "dmh" (盤中)
    hours_to_event: Optional[float] = None
    recommended_action: str = "PROCEED"  # "PROCEED", "DEFER"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_blackout": self.is_blackout,
            "reason": self.reason,
            "event_type": self.event_type,
            "event_name": self.event_name,
            "event_time": self.event_time,
            "timing": self.timing,
            "hours_to_event": round(self.hours_to_event, 2) if self.hours_to_event is not None else None,
            "recommended_action": self.recommended_action,
            "metadata": self.metadata,
        }


class CalendarBlackoutService:
    """
    宏觀事件與財報日避開守衛服務
    """

    # 2026/2027 聯準會 FOMC 利率決議發布時間表 (美東時間 14:00 EST / 14:30 記者會)
    # 來源：Federal Reserve Official Schedule
    _BUILTIN_FOMC_SCHEDULE_EST = [
        {"name": "FOMC 利率決議與貨幣政策聲明", "time": "2026-01-28 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與經濟預測摘要 (SEP)", "time": "2026-03-18 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與貨幣政策聲明", "time": "2026-04-29 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與經濟預測摘要 (SEP)", "time": "2026-06-17 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與貨幣政策聲明", "time": "2026-07-29 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與經濟預測摘要 (SEP)", "time": "2026-09-16 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與貨幣政策聲明", "time": "2026-10-28 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與經濟預測摘要 (SEP)", "time": "2026-12-09 14:00", "type": "FOMC"},
        {"name": "FOMC 利率決議與貨幣政策聲明", "time": "2027-01-27 14:00", "type": "FOMC"},
    ]

    # 2026 美國勞工統計局 (BLS) CPI 與非農就業報告發布時間 (美東時間 08:30 EST)
    _BUILTIN_BLS_SCHEDULE_EST = [
        # CPI
        {"name": "美國 12 月 CPI 通膨報告", "time": "2026-01-14 08:30", "type": "CPI"},
        {"name": "美國 1 月 CPI 通膨報告",   "time": "2026-02-11 08:30", "type": "CPI"},
        {"name": "美國 2 月 CPI 通膨報告",   "time": "2026-03-11 08:30", "type": "CPI"},
        {"name": "美國 3 月 CPI 通膨報告",   "time": "2026-04-14 08:30", "type": "CPI"},
        {"name": "美國 4 月 CPI 通膨報告",   "time": "2026-05-12 08:30", "type": "CPI"},
        {"name": "美國 5 月 CPI 通膨報告",   "time": "2026-06-10 08:30", "type": "CPI"},
        {"name": "美國 6 月 CPI 通膨報告",   "time": "2026-07-14 08:30", "type": "CPI"},
        {"name": "美國 7 月 CPI 通膨報告",   "time": "2026-08-12 08:30", "type": "CPI"},
        {"name": "美國 8 月 CPI 通膨報告",   "time": "2026-09-15 08:30", "type": "CPI"},
        {"name": "美國 9 月 CPI 通膨報告",   "time": "2026-10-14 08:30", "type": "CPI"},
        {"name": "美國 10 月 CPI 通膨報告",  "time": "2026-11-12 08:30", "type": "CPI"},
        {"name": "美國 11 月 CPI 通膨報告",  "time": "2026-12-10 08:30", "type": "CPI"},
        # NFP
        {"name": "美國 12 月非農就業報告 (NFP)", "time": "2026-01-09 08:30", "type": "NFP"},
        {"name": "美國 1 月非農就業報告 (NFP)",   "time": "2026-02-06 08:30", "type": "NFP"},
        {"name": "美國 2 月非農就業報告 (NFP)",   "time": "2026-03-06 08:30", "type": "NFP"},
        {"name": "美國 3 月非農就業報告 (NFP)",   "time": "2026-04-03 08:30", "type": "NFP"},
        {"name": "美國 4 月非農就業報告 (NFP)",   "time": "2026-05-08 08:30", "type": "NFP"},
        {"name": "美國 5 月非農就業報告 (NFP)",   "time": "2026-06-05 08:30", "type": "NFP"},
        {"name": "美國 6 月非農就業報告 (NFP)",   "time": "2026-07-02 08:30", "type": "NFP"},
        {"name": "美國 7 月非農就業報告 (NFP)",   "time": "2026-08-07 08:30", "type": "NFP"},
        {"name": "美國 8 月非農就業報告 (NFP)",   "time": "2026-09-04 08:30", "type": "NFP"},
        {"name": "美國 9 月非農就業報告 (NFP)",   "time": "2026-10-02 08:30", "type": "NFP"},
        {"name": "美國 10 月非農就業報告 (NFP)",  "time": "2026-11-06 08:30", "type": "NFP"},
        {"name": "美國 11 月非農就業報告 (NFP)",  "time": "2026-12-04 08:30", "type": "NFP"},
    ]

    def __init__(self, user_id: Optional[str] = None, settings_service: Any = None) -> None:
        self.user_id = resolve_user_id(user_id)
        if settings_service is None:
            try:
                from src.services.settings_service import SettingsService
                self.settings_service = SettingsService()
            except Exception:
                self.settings_service = None
        else:
            self.settings_service = settings_service
        self._nyse_tz = pytz.timezone("US/Eastern")

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        if self.settings_service:
            try:
                val = self.settings_service.get(self.user_id, key) if hasattr(self.settings_service, "get") else self.settings_service.get_setting(key)
                if val is not None:
                    return str(val).lower() in ("true", "1")
            except Exception:
                pass
        return default

    def _get_setting_float(self, key: str, default: float) -> float:
        if self.settings_service:
            try:
                val = self.settings_service.get(self.user_id, key) if hasattr(self.settings_service, "get") else self.settings_service.get_setting(key)
                if val is not None:
                    return float(val)
            except Exception:
                pass
        return default

    def _get_setting_int(self, key: str, default: int) -> int:
        if self.settings_service:
            try:
                val = self.settings_service.get(self.user_id, key) if hasattr(self.settings_service, "get") else self.settings_service.get_setting(key)
                if val is not None:
                    return int(val)
            except Exception:
                pass
        return default

    def _get_finnhub_key(self) -> Optional[str]:
        import os
        env_key = os.environ.get("FINNHUB_API_KEY")
        if env_key:
            return env_key
        if self.settings_service:
            try:
                if hasattr(self.settings_service, "get_all_settings"):
                    all_s = self.settings_service.get_all_settings()
                    return all_s.get("source_finnhub_api_key") or all_s.get("FINNHUB_API_KEY")
                elif hasattr(self.settings_service, "get"):
                    return self.settings_service.get(self.user_id, "source_finnhub_api_key") or self.settings_service.get(self.user_id, "FINNHUB_API_KEY")
                elif hasattr(self.settings_service, "get_setting"):
                    return self.settings_service.get_setting("source_finnhub_api_key") or self.settings_service.get_setting("FINNHUB_API_KEY")
            except Exception:
                pass
        return None

    async def fetch_earnings_calendar(
        self, ticker: str, force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        獲取標的最新財報日曆資料（優先從 Redis 快取讀取）。
        若快取未命中，則調用 Finnhub /calendar/earnings API 並快取 12 小時。
        """
        clean_ticker = (ticker or "").strip().upper()
        if not clean_ticker:
            return None

        cache_key = f"{_REDIS_EARNINGS_KEY_PREFIX}:{clean_ticker}"

        # 1. 優先嘗試從 Redis 讀取快取
        if not force_refresh:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                cached = await r.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.debug(f"Redis cache read error for {clean_ticker} earnings: {e}")

        # 2. 調用 Finnhub Earnings Calendar API
        token = self._get_finnhub_key()
        if not token:
            logger.debug(f"No Finnhub API key found; skipping earnings API for {clean_ticker}")
            return None

        try:
            # 查詢涵蓋前後 45 天區間
            now_ny = datetime.now(self._nyse_tz)
            start_str = (now_ny - timedelta(days=20)).strftime("%Y-%m-%d")
            end_str = (now_ny + timedelta(days=60)).strftime("%Y-%m-%d")

            url = "https://finnhub.io/api/v1/calendar/earnings"
            params = {
                "symbol": clean_ticker,
                "from": start_str,
                "to": end_str,
                "token": token,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    calendar_items = data.get("earningsCalendar", [])
                    if calendar_items:
                        # 挑選距離現在最近（大於等於 5 天前，以便涵蓋剛發布後的 post-hours）的項目
                        candidate = None
                        min_delta = timedelta(days=999)
                        today_date = now_ny.date()

                        for it in calendar_items:
                            d_str = it.get("date")
                            if not d_str:
                                continue
                            try:
                                d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                                delta = abs(d_obj - today_date)
                                if delta < min_delta:
                                    min_delta = delta
                                    candidate = it
                            except Exception:
                                pass

                        if candidate:
                            # 寫入 Redis 快取
                            try:
                                from src.infrastructure.cache.redis_client import get_redis
                                r = await get_redis(decode_responses=True)
                                await r.set(cache_key, json.dumps(candidate), ex=_CACHE_TTL_SECONDS)
                            except Exception as re:
                                logger.debug(f"Failed to cache earnings in redis: {re}")
                            return candidate
        except Exception as api_err:
            logger.warning(f"Failed to fetch Finnhub earnings calendar for {clean_ticker}: {api_err}")

        return None

    async def evaluate_earnings_blackout(
        self, ticker: str, now_dt: Optional[datetime] = None
    ) -> BlackoutDecision:
        """
        評估個股是否落入財報避開視窗 (Earnings Blackout Window)。
        - 預設前置保護：財報前 48 小時 (earnings_blackout_pre_hours)
        - 預設後置沉澱：財報後 24 小時 (earnings_blackout_post_hours)
        """
        clean_ticker = (ticker or "").strip().upper()
        if not self._get_setting_bool("enable_earnings_blackout_guard", True):
            return BlackoutDecision(
                is_blackout=False,
                reason="財報日前後避開守衛已由設定關閉",
                event_type="NONE",
            )

        pre_hours = self._get_setting_float("earnings_blackout_pre_hours", 48.0)
        post_hours = self._get_setting_float("earnings_blackout_post_hours", 24.0)

        now_ny = now_dt.astimezone(self._nyse_tz) if now_dt else datetime.now(self._nyse_tz)

        earnings_data = await self.fetch_earnings_calendar(clean_ticker)
        if not earnings_data:
            return BlackoutDecision(
                is_blackout=False,
                reason=f"無 {clean_ticker} 即將發布財報記錄或外部行事曆無即時排程，安全放行",
                event_type="NONE",
            )

        date_str = earnings_data.get("date")
        hour_code = (earnings_data.get("hour") or "").strip().lower()
        if not date_str:
            return BlackoutDecision(is_blackout=False, reason="財報日期未定，安全放行")

        try:
            earnings_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            # 根據時段估計精確時間
            if hour_code == "bmo":
                # 盤前 08:00 EST
                release_dt = self._nyse_tz.localize(datetime(earnings_date.year, earnings_date.month, earnings_date.day, 8, 0, 0))
                timing_desc = "盤前 (BMO 08:00)"
            elif hour_code == "amc":
                # 盤後 16:30 EST
                release_dt = self._nyse_tz.localize(datetime(earnings_date.year, earnings_date.month, earnings_date.day, 16, 30, 0))
                timing_desc = "盤後 (AMC 16:30)"
            else:
                # 未註明，預設為開盤 09:30 EST
                release_dt = self._nyse_tz.localize(datetime(earnings_date.year, earnings_date.month, earnings_date.day, 9, 30, 0))
                timing_desc = "當日 (09:30)"

            delta_sec = (release_dt - now_ny).total_seconds()
            hours_to_event = delta_sec / 3600.0

            # 檢驗是否落入避開視窗：[-post_hours <= hours_to_event <= pre_hours]
            is_in_blackout = (-post_hours <= hours_to_event <= pre_hours)

            if is_in_blackout:
                if hours_to_event >= 0:
                    status_desc = f"預計於 {hours_to_event:.1f} 小時後 ({date_str} {timing_desc}) 發布財報"
                else:
                    status_desc = f"已於 {abs(hours_to_event):.1f} 小時前 ({date_str} {timing_desc}) 發布財報（處於波動沉澱窗口）"

                reason = (
                    f"⚠️ 標的 {clean_ticker} {status_desc}，處於財報保護避開視窗 "
                    f"(前 {pre_hours:.0f}h / 後 {post_hours:.0f}h)，暫緩配置以規避二元財報波動風險。"
                )
                logger.info(f"Earnings Blackout Guard triggered for {clean_ticker}: {reason}")
                return BlackoutDecision(
                    is_blackout=True,
                    reason=reason,
                    event_type="EARNINGS",
                    event_name=f"{clean_ticker} Q{earnings_data.get('quarter', '')} 財報",
                    event_time=release_dt.isoformat(),
                    timing=hour_code or "unknown",
                    hours_to_event=hours_to_event,
                    recommended_action="DEFER",
                    metadata=earnings_data,
                )
            else:
                if hours_to_event >= 0:
                    days_away = hours_to_event / 24.0
                    safe_reason = f"距離下次財報 ({date_str} {timing_desc}) 尚有 {days_away:.1f} 天，處於安全交易區間"
                else:
                    days_ago = abs(hours_to_event) / 24.0
                    safe_reason = f"財報已於 {days_ago:.1f} 天前 ({date_str} {timing_desc}) 發布完畢，已過波動沉澱期，處於安全交易區間"

                return BlackoutDecision(
                    is_blackout=False,
                    reason=safe_reason,
                    event_type="EARNINGS",
                    event_name=f"{clean_ticker} 財報",
                    event_time=release_dt.isoformat(),
                    timing=hour_code,
                    hours_to_event=hours_to_event,
                    recommended_action="PROCEED",
                    metadata=earnings_data,
                )

        except Exception as parse_err:
            logger.warning(f"Error parsing earnings date '{date_str}' for {clean_ticker}: {parse_err}")
            return BlackoutDecision(is_blackout=False, reason="財報日期解析異常，安全降級放行")

    def evaluate_macro_blackout(
        self, now_dt: Optional[datetime] = None
    ) -> BlackoutDecision:
        """
        評估目前時間是否落入高衝擊宏觀數據發布避開視窗 (FOMC / CPI / NFP)。
        - 預設前置保護：發布前 60 分鐘 (macro_blackout_pre_minutes)
        - 預設後置沉澱：發布後 30 分鐘 (macro_blackout_post_minutes)
        """
        if not self._get_setting_bool("enable_macro_calendar_blackout_guard", True):
            return BlackoutDecision(
                is_blackout=False,
                reason="宏觀行事曆避開守衛已由設定關閉",
                event_type="NONE",
            )

        pre_minutes = self._get_setting_int("macro_blackout_pre_minutes", 60)
        post_minutes = self._get_setting_int("macro_blackout_post_minutes", 30)

        now_ny = now_dt.astimezone(self._nyse_tz) if now_dt else datetime.now(self._nyse_tz)

        all_macro_events = self._BUILTIN_FOMC_SCHEDULE_EST + self._BUILTIN_BLS_SCHEDULE_EST

        for ev in all_macro_events:
            t_str = ev["time"]
            name = ev["name"]
            try:
                ev_dt = self._nyse_tz.localize(datetime.strptime(t_str, "%Y-%m-%d %H:%M"))
                diff_sec = (ev_dt - now_ny).total_seconds()
                diff_min = diff_sec / 60.0

                # 檢驗是否在保護視窗內：[-post_minutes <= diff_min <= pre_minutes]
                if -post_minutes <= diff_min <= pre_minutes:
                    if diff_min >= 0:
                        status_str = f"即將於 {diff_min:.0f} 分鐘後 ({t_str} EST) 發布"
                    else:
                        status_str = f"已於 {abs(diff_min):.0f} 分鐘前 ({t_str} EST) 發布（處於市場吸收沉澱期）"

                    reason = (
                        f"🛡️ 重大宏觀事件 [{name}] {status_str}，處於流動性保護避開窗口 "
                        f"(前 {pre_minutes}分 / 後 {post_minutes}分)，暫緩全市場開倉以防極端滑點。"
                    )
                    logger.warning(f"Macro Blackout Guard triggered: {reason}")
                    return BlackoutDecision(
                        is_blackout=True,
                        reason=reason,
                        event_type="MACRO",
                        event_name=name,
                        event_time=ev_dt.isoformat(),
                        hours_to_event=diff_min / 60.0,
                        recommended_action="DEFER",
                        metadata=ev,
                    )
            except Exception as e:
                logger.debug(f"Error parsing macro event date '{t_str}': {e}")

        return BlackoutDecision(
            is_blackout=False,
            reason="目前無即將發布之重大宏觀事件 (FOMC/CPI/NFP)，宏觀行事曆安全",
            event_type="NONE",
            recommended_action="PROCEED",
        )

    async def evaluate_candidate(
        self, ticker: str, now_dt: Optional[datetime] = None
    ) -> BlackoutDecision:
        """
        全面評估候選標的之開倉安全度（依序檢驗宏觀事件黑名單與個股財報黑名單）。
        """
        # 1. 檢驗全市場宏觀事件黑名單 (FOMC / CPI / NFP)
        macro_decision = self.evaluate_macro_blackout(now_dt=now_dt)
        if macro_decision.is_blackout:
            return macro_decision

        # 2. 檢驗個股財報日黑名單
        earnings_decision = await self.evaluate_earnings_blackout(ticker=ticker, now_dt=now_dt)
        return earnings_decision

    async def get_upcoming_calendar_summary(
        self, tickers: List[str], now_dt: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        產出候選清單標的之即時財報日曆與宏觀大事記摘要，供對話路由器 /guard 與 /calendar 展現。
        """
        now_ny = now_dt.astimezone(self._nyse_tz) if now_dt else datetime.now(self._nyse_tz)
        today_date = now_ny.date()

        # 1. 檢測下一個最近的重大宏觀事件
        all_macro = self._BUILTIN_FOMC_SCHEDULE_EST + self._BUILTIN_BLS_SCHEDULE_EST
        next_macro = None
        min_future_sec = 999999999

        for ev in all_macro:
            try:
                ev_dt = self._nyse_tz.localize(datetime.strptime(ev["time"], "%Y-%m-%d %H:%M"))
                diff = (ev_dt - now_ny).total_seconds()
                if 0 <= diff < min_future_sec:
                    min_future_sec = diff
                    next_macro = {
                        "name": ev["name"],
                        "time": ev["time"],
                        "type": ev["type"],
                        "hours_away": round(diff / 3600.0, 1),
                        "days_away": round(diff / 86400.0, 1),
                    }
            except Exception:
                pass

        # 2. 檢測標的庫財報日程
        tickers_summary = {}
        for ticker in tickers:
            clean = ticker.strip().upper()
            decision = await self.evaluate_earnings_blackout(clean, now_dt=now_ny)
            raw_meta = decision.metadata or {}
            d_str = raw_meta.get("date", "未定")
            timing = raw_meta.get("hour", "")
            timing_str = f" ({timing.upper()})" if timing else ""

            tickers_summary[clean] = {
                "ticker": clean,
                "is_blackout": decision.is_blackout,
                "date": d_str,
                "timing": timing,
                "display": f"{d_str}{timing_str}" if d_str != "未定" else "無即時日程",
                "reason": decision.reason,
                "hours_to_event": decision.hours_to_event,
            }

        macro_decision = self.evaluate_macro_blackout(now_dt=now_ny)

        return {
            "macro_status": {
                "is_blackout": macro_decision.is_blackout,
                "reason": macro_decision.reason,
                "next_event": next_macro,
            },
            "tickers": tickers_summary,
            "evaluated_at": now_ny.isoformat(),
        }
