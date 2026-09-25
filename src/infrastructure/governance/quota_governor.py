"""
External Quota & Rate Governor (外部服務配額與頻率守衛)
======================================================
Ensures external dependencies (Polygon, FRED, Tavily, eToro, LiteLLM)
operate within safe rate limits and NEVER exceed 60% capacity utilization.
Leaves >= 40% headroom for bursts, emergency stops, and user-initiated operations.

硬性限制：所有外部相依工具之使用率維持在 60% 以下，保留 40% 的安全彈性緩衝。
"""
from __future__ import annotations

import time
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

logger = logging.getLogger("QuotaGovernor")


@dataclass
class QuotaRule:
    limit_count: int               # 官方/名義硬上限
    window_seconds: float          # 滑動窗口時間 (秒)
    utilization_cap: float = 0.60  # 最大利用率上限 (預設 60%)
    min_interval_seconds: float = 0.0 # 最小呼叫間隔 (防抖)

    @property
    def max_allowed_count(self) -> int:
        """The 60% capped maximum number of allowed requests per window."""
        return max(1, int(self.limit_count * self.utilization_cap))


DEFAULT_RULES: Dict[str, QuotaRule] = {
    "polygon": QuotaRule(
        limit_count=5,          # 免費層 5 req/min
        window_seconds=60.0,
        utilization_cap=0.60,   # 60% 水位 = 最多 3 req/min
        min_interval_seconds=15.0, # 兩次請求間隔至少 15s
    ),
    "fred": QuotaRule(
        limit_count=120,        # 120 req/min
        window_seconds=60.0,
        utilization_cap=0.60,   # 60% 水位 = 最多 72 req/min
        min_interval_seconds=0.5,
    ),
    "tavily": QuotaRule(
        limit_count=33,         # 1000/月 ≈ 33 req/day
        window_seconds=86400.0, # 日滑動窗口
        utilization_cap=0.60,   # 60% 水位 = 每日預算 20 次
        min_interval_seconds=2.0,
    ),
    "etoro": QuotaRule(
        limit_count=10,         # 10 req/s
        window_seconds=1.0,
        utilization_cap=0.60,   # 60% 水位 = 最多 6 req/s
        min_interval_seconds=0.17, # 每筆間隔至少 170ms
    ),
    "litellm": QuotaRule(
        limit_count=60,         # 基準 60 RPM
        window_seconds=60.0,
        utilization_cap=0.60,   # 60% 水位 = 36 RPM
        min_interval_seconds=0.2,
    ),
}


class ExternalQuotaGovernor:
    """
    Central governor tracking and throttling external calls across providers.
    中央配額控管器：追蹤並節流各外部 API，硬性確保利用率 <= 60%。
    """
    _instance: Optional[ExternalQuotaGovernor] = None

    def __init__(self, custom_rules: Optional[Dict[str, QuotaRule]] = None):
        self.rules: Dict[str, QuotaRule] = {**DEFAULT_RULES, **(custom_rules or {})}
        self._timestamps: Dict[str, deque[float]] = {
            provider: deque() for provider in self.rules
        }
        self._last_call: Dict[str, float] = {provider: 0.0 for provider in self.rules}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> ExternalQuotaGovernor:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = ExternalQuotaGovernor()
        return cls._instance

    def _cleanup_window(self, provider: str, now: float) -> None:
        rule = self.rules.get(provider)
        if not rule or provider not in self._timestamps:
            return
        q = self._timestamps[provider]
        cutoff = now - rule.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

    def get_utilization(self, provider: str) -> float:
        """
        Get current utilization as a fraction of the official limit (0.0 ~ 1.0).
        取得當前利用率比例（相對於官方名義上限）。
        """
        rule = self.rules.get(provider)
        if not rule:
            return 0.0
        now = time.time()
        self._cleanup_window(provider, now)
        current_count = len(self._timestamps[provider])
        return current_count / rule.limit_count if rule.limit_count > 0 else 0.0

    def get_capped_utilization(self, provider: str) -> float:
        """
        Get current utilization relative to the 60% cap (0.0 ~ 1.0).
        取得相對於 60% 限制水位的利用率（1.0 代表剛好達到 60% 上限）。
        """
        rule = self.rules.get(provider)
        if not rule:
            return 0.0
        now = time.time()
        self._cleanup_window(provider, now)
        current_count = len(self._timestamps[provider])
        return current_count / rule.max_allowed_count if rule.max_allowed_count > 0 else 0.0

    def can_acquire(self, provider: str) -> bool:
        """
        Check if an immediate call is allowed under the 60% cap.
        檢查在 60% 限制水位下是否允許立即發起呼叫。
        """
        rule = self.rules.get(provider)
        if not rule:
            return True
        now = time.time()
        self._cleanup_window(provider, now)

        # Check debounce / min interval
        if rule.min_interval_seconds > 0:
            if (now - self._last_call.get(provider, 0.0)) < rule.min_interval_seconds:
                return False

        # Check 60% capacity cap
        current_count = len(self._timestamps[provider])
        return current_count < rule.max_allowed_count

    async def acquire(
        self,
        provider: str,
        wait: bool = False,
        max_wait_seconds: float = 5.0,
    ) -> bool:
        """
        Attempt to acquire capacity for an external provider.
        If wait is True, will sleep asynchronously up to max_wait_seconds to stay under 60%.
        
        嘗試獲取外部服務調用配額。若 wait=True 且超出 60% 水位，將在限額內平滑等待。
        """
        rule = self.rules.get(provider)
        if not rule:
            return True

        start_time = time.time()
        while True:
            async with self._lock:
                now = time.time()
                self._cleanup_window(provider, now)

                # Check spacing
                elapsed_since_last = now - self._last_call.get(provider, 0.0)
                spacing_ok = (rule.min_interval_seconds <= 0) or (elapsed_since_last >= rule.min_interval_seconds)

                current_count = len(self._timestamps[provider])
                cap_ok = current_count < rule.max_allowed_count

                if spacing_ok and cap_ok:
                    self._timestamps[provider].append(now)
                    self._last_call[provider] = now
                    logger.debug(
                        f"Quota acquired for {provider} ({current_count + 1}/{rule.max_allowed_count}, "
                        f"utilization: {self.get_utilization(provider):.1%})"
                    )
                    return True

            # If not allowed and cannot/won't wait
            if not wait:
                logger.warning(
                    f"QuotaGovernor: {provider} reached 60% utilization cap "
                    f"({len(self._timestamps[provider])}/{rule.max_allowed_count} in {rule.window_seconds}s). Request throttled."
                )
                return False

            # Wait calculation
            time_waited = time.time() - start_time
            if time_waited >= max_wait_seconds:
                logger.warning(
                    f"QuotaGovernor: {provider} timed out waiting for capacity "
                    f"after {time_waited:.2f}s (60% cap held)."
                )
                return False

            sleep_duration = max(0.1, rule.min_interval_seconds - elapsed_since_last)
            sleep_duration = min(sleep_duration, max_wait_seconds - time_waited)
            await asyncio.sleep(sleep_duration)

    def record_usage(self, provider: str, count: int = 1) -> None:
        """Directly record usage (e.g. from batch calls)."""
        rule = self.rules.get(provider)
        if not rule:
            return
        now = time.time()
        self._cleanup_window(provider, now)
        for _ in range(count):
            self._timestamps[provider].append(now)
        self._last_call[provider] = now

    def reset(self, provider: Optional[str] = None) -> None:
        """Reset usage history for testing or manual flush."""
        if provider:
            if provider in self._timestamps:
                self._timestamps[provider].clear()
            self._last_call[provider] = 0.0
        else:
            for p in self._timestamps:
                self._timestamps[p].clear()
            for p in self._last_call:
                self._last_call[p] = 0.0

    def get_status(self, provider: str) -> Dict[str, Any]:
        """Return comprehensive status dict for monitoring."""
        rule = self.rules.get(provider)
        if not rule:
            return {"provider": provider, "managed": False}
        now = time.time()
        self._cleanup_window(provider, now)
        current = len(self._timestamps[provider])
        return {
            "provider": provider,
            "managed": True,
            "window_seconds": rule.window_seconds,
            "official_limit": rule.limit_count,
            "effective_cap_60pct": rule.max_allowed_count,
            "current_window_usage": current,
            "official_utilization": round(current / rule.limit_count, 3),
            "capped_utilization": round(current / rule.max_allowed_count, 3),
            "headroom_pct": round((1.0 - (current / rule.limit_count)) * 100, 1),
            "can_acquire_now": self.can_acquire(provider),
        }
