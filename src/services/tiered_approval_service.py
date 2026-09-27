"""
Tiered Auto-Approval Service
分級自動核准服務

Provides policy evaluation for multi-tier trade approvals.
Enables high-confidence small-sized orders to bypass human-in-the-loop blocking
under strict safety, position sizing, and macro risk boundaries, helping achieve
autonomous execution without compromising capital safety.
在嚴格風控與資本安全邊界下，針對高勝率小額試單提供分級自動放行決策。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.config.owner import resolve_user_id
from src.infrastructure.cache.redis_client import get_redis_sync
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class TieredApprovalResult:
    """Evaluation result from tiered auto-approval."""
    approved: bool
    tier: str  # TIER_1_DIRECT, TIER_2_AUTO_APPROVED, TIER_3_MANUAL_REQUIRED, TIER_4_SKIPPED
    reason: str
    confidence_score: float
    order_amount: float
    daily_count: int
    max_daily_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "tier": self.tier,
            "reason": self.reason,
            "confidence_score": self.confidence_score,
            "order_amount": self.order_amount,
            "daily_count": self.daily_count,
            "max_daily_count": self.max_daily_count,
        }


class TieredApprovalService:
    """
    Evaluates whether a trade order qualifies for automated approval.
    分級自動核准引擎：評估交易委託是否符合自動放行標準。
    """

    def __init__(self, user_id: str, settings_repo=None, redis_client=None):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo
        self._settings_service = None
        self._redis = redis_client
        self._in_memory_daily_counts: Dict[str, int] = {}

    @property
    def settings(self) -> SettingsService:
        if self._settings_service is None:
            self._settings_service = SettingsService(user_id=self.user_id)
        return self._settings_service

    def _get_redis(self):
        if self._redis is None:
            try:
                self._redis = get_redis_sync(decode_responses=True)
            except Exception as e:
                logger.warning("TieredApprovalService: Redis unavailable (%s), using local fallback", e)
                self._redis = False
        return self._redis if self._redis is not False else None

    def _get_daily_key(self) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"tiered_approval:daily_count:{self.user_id}:{today_str}"

    def get_daily_approved_count(self) -> int:
        """Get number of orders auto-approved today for this user."""
        r = self._get_redis()
        if r:
            try:
                val = r.get(self._get_daily_key())
                return int(val) if val is not None else 0
            except Exception as ex:
                logger.warning("Failed to fetch daily auto-approved count from Redis: %s", ex)

        # Fallback in-memory
        key = self._get_daily_key()
        return self._in_memory_daily_counts.get(key, 0)

    def record_auto_approval(self) -> int:
        """Record an auto-approval event, incrementing daily counter."""
        r = self._get_redis()
        key = self._get_daily_key()
        if r:
            try:
                pipe = r.pipeline()
                pipe.incr(key)
                pipe.expire(key, 86400 * 2)  # 48h TTL
                res = pipe.execute()
                new_count = int(res[0])
                logger.info(
                    "User %s tiered auto-approval count incremented to %d",
                    self.user_id, new_count
                )
                return new_count
            except Exception as ex:
                logger.warning("Failed to increment daily auto-approved count in Redis: %s", ex)

        # Fallback in-memory
        count = self._in_memory_daily_counts.get(key, 0) + 1
        self._in_memory_daily_counts[key] = count
        return count

    def evaluate_approval(
        self,
        order: Any,
        confidence_score: float,
        rationale: str = "",
        sentinel_status: str = "NORMAL",
        threshold: float = 7.5,
    ) -> TieredApprovalResult:
        """
        Evaluate order against tiered approval policies.
        判定訂單是否符合分級自動核准資格。
        """
        # 1. Fetch user-configured boundaries
        enabled_setting = self._get_setting("tiered_approval_enabled", True)
        is_enabled = str(enabled_setting).lower() in ("true", "1")

        raw_auto_score_min = self._get_setting("tiered_approval_auto_score_min", 6.8)
        auto_score_min = float(raw_auto_score_min)
        if auto_score_min > 10.0:
            auto_score_min /= 10.0

        raw_max_amount = self._get_setting("tiered_approval_max_amount_usd", 30.0)
        max_amount_usd = float(raw_max_amount)

        raw_max_daily = self._get_setting("tiered_approval_max_daily_count", 3)
        max_daily_count = int(raw_max_daily)

        # Normalize score
        normalized_score = float(confidence_score)
        if normalized_score > 10.0:
            normalized_score /= 10.0

        # Calculate effective order amount
        order_amount = 0.0
        if hasattr(order, "amount_usd") and order.amount_usd is not None:
            order_amount = float(order.amount_usd)
        elif hasattr(order, "quantity") and order.quantity is not None:
            order_amount = float(order.quantity)

        daily_count = self.get_daily_approved_count()

        # Gate 0: Is feature globally enabled for this user?
        if not is_enabled:
            return TieredApprovalResult(
                approved=False,
                tier="TIER_3_MANUAL_REQUIRED",
                reason="Tiered auto-approval is disabled in user settings",
                confidence_score=normalized_score,
                order_amount=order_amount,
                daily_count=daily_count,
                max_daily_count=max_daily_count,
            )

        # Gate 1: Macro / Sentinel Risk Guard
        # If sentinel is in PANIC or severe drawdown, auto-approval is suspended
        if sentinel_status.upper() in ("PANIC", "CRITICAL", "HIGH_RISK"):
            logger.warning(
                "TieredApproval blocked: Sentinel status is %s for user %s",
                sentinel_status, self.user_id
            )
            return TieredApprovalResult(
                approved=False,
                tier="TIER_3_MANUAL_REQUIRED",
                reason=f"Auto-approval suspended: Sentinel status is {sentinel_status}",
                confidence_score=normalized_score,
                order_amount=order_amount,
                daily_count=daily_count,
                max_daily_count=max_daily_count,
            )

        # Gate 2: Score requirement
        if normalized_score < auto_score_min:
            return TieredApprovalResult(
                approved=False,
                tier="TIER_3_MANUAL_REQUIRED",
                reason=f"Score {normalized_score:.1f} below tiered auto-approval min ({auto_score_min:.1f})",
                confidence_score=normalized_score,
                order_amount=order_amount,
                daily_count=daily_count,
                max_daily_count=max_daily_count,
            )

        # Gate 3: Order Amount Cap (小額實測安全上限)
        if order_amount > max_amount_usd:
            logger.info(
                "TieredApproval: Order amount $%.2f exceeds auto cap $%.2f. Requesting manual approval.",
                order_amount, max_amount_usd
            )
            return TieredApprovalResult(
                approved=False,
                tier="TIER_3_MANUAL_REQUIRED",
                reason=f"Order amount ${order_amount:.2f} exceeds tiered auto-approval cap (${max_amount_usd:.2f})",
                confidence_score=normalized_score,
                order_amount=order_amount,
                daily_count=daily_count,
                max_daily_count=max_daily_count,
            )

        # Gate 4: Daily Quota Cap (防黑天鵝過度連續觸發)
        if daily_count >= max_daily_count:
            logger.info(
                "TieredApproval: Daily limit reached (%d/%d). Requesting manual approval.",
                daily_count, max_daily_count
            )
            return TieredApprovalResult(
                approved=False,
                tier="TIER_3_MANUAL_REQUIRED",
                reason=f"Daily auto-approval quota reached ({daily_count}/{max_daily_count})",
                confidence_score=normalized_score,
                order_amount=order_amount,
                daily_count=daily_count,
                max_daily_count=max_daily_count,
            )

        # All boundaries satisfied -> Tier 2 Auto-Approved!
        approval_reason = (
            f"Tier 2 Auto-Approved: Score {normalized_score:.1f} >= {auto_score_min:.1f}, "
            f"amount ${order_amount:.2f} <= ${max_amount_usd:.2f}, "
            f"quota ({daily_count + 1}/{max_daily_count})"
        )
        logger.info(approval_reason)

        return TieredApprovalResult(
            approved=True,
            tier="TIER_2_AUTO_APPROVED",
            reason=approval_reason,
            confidence_score=normalized_score,
            order_amount=order_amount,
            daily_count=daily_count,
            max_daily_count=max_daily_count,
        )

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_repo and hasattr(self.settings_repo, "get"):
            val = self.settings_repo.get(self.user_id, key)
            if val is not None:
                return val
        try:
            return self.settings.get_setting(key, default)
        except Exception:
            return default
