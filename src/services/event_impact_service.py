"""
EventImpactService — Quantifies, decays, and applies market event biases.
事件量化抽取與時間衰減偏置服務。

Core Capabilities:
1. Microeconomic Bias (個經軌道): Ticker-specific alpha adjustments with 36h default half-life.
2. Macroeconomic Bias (總經軌道): Systemic stress indexing modifying portfolio cash buffers & hurdles.
3. Multi-tenant isolation by user_id and high-speed caching via Redis.
4. Compliant with Fail-Silent Policy (Constraint #0).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.domain.event_impact import EventImpact, EventScope, EventSentiment
from src.repositories.event_impact_repository import (
    AlchemyEventImpactRepository,
    IEventImpactRepository,
)
from src.utils.logger import setup_logger

logger = setup_logger("EventImpactService")


class EventImpactService:
    """Service orchestrating event quantification and real-time bias application."""

    def __init__(
        self,
        user_id: Optional[str] = None,
        repository: Optional[IEventImpactRepository] = None,
        settings_service: Any = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.repository = repository or AlchemyEventImpactRepository()
        self._settings_service = settings_service

    def _get_setting(self, key: str, default: Any) -> Any:
        """Safely fetch setting from SettingsService or fallback."""
        if self._settings_service is not None:
            try:
                if hasattr(self._settings_service, "get_setting"):
                    val = self._settings_service.get_setting(key, default=default, user_id=self.user_id)
                elif hasattr(self._settings_service, "get"):
                    val = self._settings_service.get(key)
                else:
                    val = None
                if val is not None:
                    return val
            except Exception as e:
                logger.warning(f"EventImpactService: failed to read setting {key}: {e}")
        return default

    def _get_redis(self):
        """Get sync Redis client for caching."""
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            return get_redis_sync()
        except Exception:
            return None

    def record_event_impact(
        self,
        scope: EventScope,
        headline: str,
        summary: str = "",
        ticker: Optional[str] = None,
        category: str = "general",
        sentiment: Optional[EventSentiment] = None,
        initial_impact: Optional[float] = None,
        half_life_hours: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EventImpact:
        """
        Quantify and persist a new market event into the bias loop.
        量化並存儲新市場事件至偏置閉環中。
        """
        # Determine defaults by scope
        if scope == EventScope.MICRO:
            if half_life_hours is None:
                half_life_hours = float(self._get_setting("event_bias_micro_half_life_hours", 36.0))
            if initial_impact is None:
                # Default heuristics for micro
                if sentiment == EventSentiment.BEARISH:
                    initial_impact = -1.2
                elif sentiment == EventSentiment.BULLISH:
                    initial_impact = +1.0
                else:
                    initial_impact = 0.0
            ticker_clean = ticker.upper() if ticker else None
        else:
            scope = EventScope.MACRO
            ticker_clean = None
            if half_life_hours is None:
                half_life_hours = float(self._get_setting("event_bias_macro_half_life_hours", 96.0))
            if initial_impact is None:
                # Default heuristics for macro stress
                if sentiment == EventSentiment.BEARISH:
                    initial_impact = -0.6
                elif sentiment == EventSentiment.BULLISH:
                    initial_impact = +0.5
                else:
                    initial_impact = 0.0

        sent_final = sentiment or (
            EventSentiment.BEARISH if (initial_impact or 0.0) < 0
            else (EventSentiment.BULLISH if (initial_impact or 0.0) > 0 else EventSentiment.NEUTRAL)
        )

        impact = EventImpact(
            user_id=self.user_id,
            scope=scope,
            ticker=ticker_clean,
            category=category,
            headline=headline,
            summary=summary,
            sentiment=sent_final,
            initial_impact=float(initial_impact),
            half_life_hours=float(half_life_hours),
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

        self.repository.insert_impact(impact)

        # Invalidate cache
        r = self._get_redis()
        if r:
            try:
                if ticker_clean:
                    r.delete(f"event_bias:{self.user_id}:micro:{ticker_clean}")
                r.delete(f"event_bias:{self.user_id}:macro")
            except Exception as e:
                logger.warning(f"EventImpactService: Redis cache invalidation error: {e}")

        return impact

    def get_ticker_micro_bias(
        self,
        ticker: str,
        at_time: Optional[datetime] = None,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Calculate net score delta for a ticker based on active micro events.
        計算標的之個經微調分數 (-1.5 ~ +1.5 pt)。
        Returns (net_delta, active_events_details).
        """
        is_enabled = bool(self._get_setting("event_bias_enabled", True))
        if not is_enabled or not ticker:
            return 0.0, []

        ticker_upper = ticker.upper()
        max_impact = float(self._get_setting("event_bias_max_micro_impact", 1.5))

        try:
            impacts = self.repository.get_active_impacts(
                user_id=self.user_id,
                scope=EventScope.MICRO,
                ticker=ticker_upper,
            )

            active_details = []
            net_delta = 0.0

            for imp in impacts:
                if imp.is_active(at_time):
                    decayed = imp.compute_decayed_impact(at_time)
                    net_delta += decayed
                    active_details.append({
                        "id": imp.id,
                        "headline": imp.headline,
                        "category": imp.category,
                        "initial_impact": imp.initial_impact,
                        "current_impact": decayed,
                        "half_life_hours": imp.half_life_hours,
                        "remaining_hours": imp.remaining_hours(at_time),
                        "created_at": imp.created_at.isoformat(),
                    })

            # Clamp net delta to [-max_impact, +max_impact]
            clamped_delta = max(-max_impact, min(max_impact, net_delta))
            return round(clamped_delta, 2), active_details

        except Exception as e:
            logger.warning(f"EventImpactService: failed to compute micro bias for {ticker_upper}: {e}")
            return 0.0, [{"_fallback_reason": str(e)}]

    def get_macro_stress_bias(
        self,
        at_time: Optional[datetime] = None,
    ) -> Tuple[float, float, List[Dict[str, Any]]]:
        """
        Calculate systemic macro stress and recommended extra cash reserve.
        計算總體經濟壓力指數 (-1.0 ~ +1.0) 與額外現金防禦保留率 (0.0 ~ +15%)。
        Returns (macro_stress_index, extra_cash_reserve_ratio, active_events_details).
        """
        is_enabled = bool(self._get_setting("event_bias_enabled", True))
        if not is_enabled:
            return 0.0, 0.0, []

        max_cash_buffer = float(self._get_setting("event_bias_max_macro_cash_buffer", 0.15))

        try:
            impacts = self.repository.get_active_impacts(
                user_id=self.user_id,
                scope=EventScope.MACRO,
            )

            active_details = []
            net_stress = 0.0

            for imp in impacts:
                if imp.is_active(at_time):
                    decayed = imp.compute_decayed_impact(at_time)
                    net_stress += decayed
                    active_details.append({
                        "id": imp.id,
                        "headline": imp.headline,
                        "category": imp.category,
                        "initial_impact": imp.initial_impact,
                        "current_impact": decayed,
                        "half_life_hours": imp.half_life_hours,
                        "remaining_hours": imp.remaining_hours(at_time),
                        "created_at": imp.created_at.isoformat(),
                    })

            # Clamp stress to [-1.0, +1.0]
            clamped_stress = max(-1.0, min(1.0, net_stress))

            # If macro stress is negative (headwind), dynamically scale defense cash reserve
            extra_cash = 0.0
            if clamped_stress < 0:
                # E.g. stress -1.0 -> +15% cash; stress -0.5 -> +7.5% cash
                extra_cash = min(max_cash_buffer, abs(clamped_stress) * max_cash_buffer)

            return round(clamped_stress, 2), round(extra_cash, 3), active_details

        except Exception as e:
            logger.warning(f"EventImpactService: failed to compute macro stress: {e}")
            return 0.0, 0.0, [{"_fallback_reason": str(e)}]

    def dismiss_bias(self, impact_id: str) -> bool:
        """Dismiss an active bias manually."""
        try:
            success = self.repository.dismiss_impact(self.user_id, impact_id)
            r = self._get_redis()
            if r:
                # Flush cached entries
                for key in r.scan_iter(f"event_bias:{self.user_id}:*"):
                    r.delete(key)
            return success
        except Exception as e:
            logger.warning(f"EventImpactService: failed to dismiss bias {impact_id}: {e}")
            return False

    def get_all_active_biases(self) -> Dict[str, Any]:
        """Aggregate all currently active micro and macro biases for Dashboard display."""
        macro_stress, extra_cash, macro_events = self.get_macro_stress_bias()

        all_active_impacts = self.repository.get_active_impacts(user_id=self.user_id)
        micro_by_ticker: Dict[str, List[Dict[str, Any]]] = {}

        for imp in all_active_impacts:
            if imp.scope == EventScope.MICRO and imp.is_active():
                t = imp.ticker or "GENERAL"
                decayed = imp.compute_decayed_impact()
                if t not in micro_by_ticker:
                    micro_by_ticker[t] = []
                micro_by_ticker[t].append({
                    "id": imp.id,
                    "headline": imp.headline,
                    "category": imp.category,
                    "sentiment": imp.sentiment.value,
                    "initial_impact": imp.initial_impact,
                    "current_impact": decayed,
                    "half_life_hours": imp.half_life_hours,
                    "remaining_hours": imp.remaining_hours(),
                    "created_at": imp.created_at.isoformat(),
                })

        return {
            "macro": {
                "stress_index": macro_stress,
                "extra_cash_reserve_ratio": extra_cash,
                "events": macro_events,
            },
            "micro": micro_by_ticker,
            "total_active_events": len(macro_events) + sum(len(v) for v in micro_by_ticker.values()),
        }
