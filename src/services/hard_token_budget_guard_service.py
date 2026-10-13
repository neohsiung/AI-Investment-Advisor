"""
Hard Token Budget Guard Service (Phase 47 - Plan A)
===================================================
Enforces a rigid financial ceiling on LLM token costs to protect the fund's net
annualized alpha target (+10% vs SPY after deducting LLM & SaaS fees).

Key Capabilities:
  1. Hard Daily & Monthly Budget Ceiling ($0.10/day, $2.50/month default on ~$1,700 portfolio).
  2. Zero-LLM Sentinel Patrol: Enforces 100% mathematical calculations for routine ATR/VPIN/Jump checks.
  3. Deterministic Council Fallback: Automatically routes routine portfolio rebalances to deterministic models.
  4. Real-time budget telemetry & /budget 0-LLM operational reporting.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("HardTokenBudgetGuardService")

DEFAULT_DAILY_LLM_BUDGET_USD = 0.10
DEFAULT_MONTHLY_LLM_BUDGET_USD = 2.50


@dataclass
class TokenBudgetStatus:
    is_hard_locked: bool
    lockout_reason: str
    daily_spent_usd: float
    daily_cap_usd: float
    monthly_spent_usd: float
    monthly_cap_usd: float
    pct_used_monthly: float
    remaining_monthly_usd: float
    zero_llm_mode_active: bool
    evaluated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_hard_locked": self.is_hard_locked,
            "lockout_reason": self.lockout_reason,
            "daily_spent_usd": round(self.daily_spent_usd, 4),
            "daily_cap_usd": round(self.daily_cap_usd, 4),
            "monthly_spent_usd": round(self.monthly_spent_usd, 4),
            "monthly_cap_usd": round(self.monthly_cap_usd, 4),
            "pct_used_monthly": round(self.pct_used_monthly, 2),
            "remaining_monthly_usd": round(self.remaining_monthly_usd, 4),
            "zero_llm_mode_active": self.zero_llm_mode_active,
            "evaluated_at": self.evaluated_at,
        }


class HardTokenBudgetGuardService:
    """
    Guards account assets by strictly constraining LLM expenditures to prevent token erosion.
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)
        self._settings_service = None
        self._token_logger = None
        self._redis_client = None

    def _get_settings(self) -> Any:
        if self._settings_service is None:
            from src.services.settings_service import SettingsService
            self._settings_service = SettingsService()
        return self._settings_service

    def _get_token_logger(self) -> Any:
        if self._token_logger is None:
            from src.services.token_logger_service import TokenLoggerService
            self._token_logger = TokenLoggerService()
        return self._token_logger

    def _get_redis(self) -> Any:
        if self._redis_client is None:
            try:
                import os
                import redis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                self._redis_client = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.debug("Redis connection unavailable for HardTokenBudgetGuardService: %s", e)
        return self._redis_client

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            settings = self._get_settings()
            return settings.get_setting(key, default)
        except Exception:
            return default

    def get_budget_status(self) -> TokenBudgetStatus:
        """
        Evaluate real-time LLM spending against configured daily and monthly caps.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        enabled = bool(self._get_setting("enable_hard_token_budget_guard", True))
        daily_cap = float(self._get_setting("daily_llm_budget_usd", DEFAULT_DAILY_LLM_BUDGET_USD))
        monthly_cap = float(self._get_setting("monthly_llm_budget_usd", DEFAULT_MONTHLY_LLM_BUDGET_USD))

        token_logger = self._get_token_logger()
        daily_spent = 0.0
        monthly_spent = 0.0

        try:
            daily_stats = token_logger.get_user_spending(self.user_id, days=1)
            daily_spent = float(daily_stats.get("total_cost", 0.0) or 0.0)
        except Exception as de:
            logger.debug("Failed querying daily spending: %s", de)

        try:
            monthly_stats = token_logger.get_user_spending(self.user_id, days=30)
            monthly_spent = float(monthly_stats.get("total_cost", 0.0) or 0.0)
        except Exception as me:
            logger.debug("Failed querying monthly spending: %s", me)

        # Check if user performed a manual reset that offset the spend
        redis_client = self._get_redis()
        if redis_client:
            try:
                reset_key = f"hard_token_budget:reset_offset:{self.user_id}"
                offset = redis_client.get(reset_key)
                if offset:
                    offset_val = float(offset)
                    daily_spent = max(0.0, daily_spent - offset_val)
                    monthly_spent = max(0.0, monthly_spent - offset_val)
            except Exception as re:
                logger.debug("Redis offset query error: %s", re)

        is_hard_locked = False
        lockout_reason = "NORMAL"

        if enabled:
            if monthly_spent >= monthly_cap:
                is_hard_locked = True
                lockout_reason = f"MONTHLY_LIMIT_BREACHED: ${monthly_spent:.4f} >= ${monthly_cap:.2f}"
            elif daily_spent >= daily_cap:
                is_hard_locked = True
                lockout_reason = f"DAILY_LIMIT_BREACHED: ${daily_spent:.4f} >= ${daily_cap:.2f}"

        pct_used = (monthly_spent / max(0.01, monthly_cap)) * 100.0
        remaining_monthly = max(0.0, monthly_cap - monthly_spent)

        zero_llm_active = is_hard_locked or bool(self._get_setting("enable_sentinel_zero_llm_mode", True))

        return TokenBudgetStatus(
            is_hard_locked=is_hard_locked,
            lockout_reason=lockout_reason,
            daily_spent_usd=daily_spent,
            daily_cap_usd=daily_cap,
            monthly_spent_usd=monthly_spent,
            monthly_cap_usd=monthly_cap,
            pct_used_monthly=pct_used,
            remaining_monthly_usd=remaining_monthly,
            zero_llm_mode_active=zero_llm_active,
            evaluated_at=now_iso,
        )

    def should_allow_llm(
        self,
        task_type: str,
        is_user_direct_chat: bool = False,
    ) -> Tuple[bool, str]:
        """
        Gating check for any LLM call attempt across the platform.
        Returns:
            (allow_llm, reason)
        """
        enabled = bool(self._get_setting("enable_hard_token_budget_guard", True))
        if not enabled:
            return True, "GUARD_DISABLED"

        # 1. Zero-LLM Sentinel enforcement
        sentinel_zero_llm = bool(self._get_setting("enable_sentinel_zero_llm_mode", True))
        if sentinel_zero_llm and task_type in ("sentinel_monitor", "sentinel_tick", "sentinel_eval", "Thematic"):
            return False, "SENTINEL_ZERO_LLM_ENFORCED"

        # 2. Zero-LLM routine rebalance / deployment enforcement
        deterministic_council = bool(self._get_setting("enable_deterministic_council_fallback", True))
        if deterministic_council and task_type in (
            "routine_rebalance",
            "batch_cash_deployment",
            "staggered_dip_deployment",
            "dip_buying",
        ):
            return False, "DETERMINISTIC_COUNCIL_ENFORCED"

        # 3. Check hard budget ceiling
        status = self.get_budget_status()
        if status.is_hard_locked:
            if is_user_direct_chat:
                return True, "USER_DIRECT_CHAT_EXCEPTION"
            return False, f"HARD_BUDGET_LOCKOUT:{status.lockout_reason}"

        return True, "BUDGET_PERMITTED"

    def reset_budget_lockout(self) -> Dict[str, Any]:
        """
        Manually reset budget lockout watermark, resetting apparent daily/monthly spend.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        token_logger = self._get_token_logger()
        current_daily = 0.0
        try:
            stats = token_logger.get_user_spending(self.user_id, days=1)
            current_daily = float(stats.get("total_cost", 0.0) or 0.0)
        except Exception:
            pass

        redis_client = self._get_redis()
        if redis_client:
            try:
                reset_key = f"hard_token_budget:reset_offset:{self.user_id}"
                # Expire after 24 hours so new days track fresh
                redis_client.setex(reset_key, 86400, str(current_daily))
            except Exception as e:
                logger.warning("Failed storing budget reset offset in Redis: %s", e)

        return {
            "status": "RESET_SUCCESSFUL",
            "reset_at": now_iso,
            "user_id": self.user_id,
            "daily_offset_applied_usd": current_daily,
        }

    def format_budget_report(self, status: Optional[TokenBudgetStatus] = None) -> str:
        """
        Format an actionable, informative status report for Telegram/Email.
        """
        if status is None:
            status = self.get_budget_status()

        status_emoji = "🔴 <b>【硬性代幣熔斷生效中】</b>" if status.is_hard_locked else "🟢 <b>【AI 代幣成本受控中】</b>"
        
        lines = [
            f"💰 {status_emoji}",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>當日 LLM 支出</b>：<code>${status.daily_spent_usd:.4f} USD</code> / <code>${status.daily_cap_usd:.2f}</code>",
            f"• <b>當月 LLM 支出</b>：<code>${status.monthly_spent_usd:.4f} USD</code> / <code>${status.monthly_cap_usd:.2f}</code>",
            f"• <b>月度預算消耗率</b>：<code>{status.pct_used_monthly:.1f}%</code>",
            f"• <b>月度可用餘額</b>：<code>${status.remaining_monthly_usd:.4f} USD</code>",
            "━━━━━━━━━━━━━━━━━━",
            "🛡️ <b>【0-LLM 數理引擎守衛狀態】</b>",
            f"• <b>Sentinel 0-LLM 守衛</b>：<b>{'啟用 (0 Token 消耗)' if status.zero_llm_mode_active else '未啟用'}</b>",
            f"• <b>確定性數理議會替代</b>：<b>{'主動啟用' if not status.is_hard_locked else '強制接管中'}</b>",
            f"• <b>當前風控狀態</b>：<code>{status.lockout_reason}</code>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        if status.is_hard_locked:
            lines.append("⚠️ <i>背景定時任務已全面轉入 0-LLM 純數理計算，杜絕資金磨損。</i>")
            lines.append("💡 <i>輸入 <code>/budget reset</code> 可手動解除今日熔斷。</i>")
        else:
            lines.append("✨ <i>例行監控與再平衡 100% 走數理引擎，月度費用受控於 $2.50 以內。</i>")
            lines.append("💡 <i>輸入 <code>/alpha</code> 檢視扣除模型後之真實淨 Alpha。</i>")

        return "\n".join(lines)
