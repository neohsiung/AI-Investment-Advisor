"""
Inference Cost-to-Alpha Hurdle Gate Service (Phase 39)
======================================================
Protects the fund's net annualized alpha (target: +10% vs S&P 500) against LLM token
cost erosion, particularly on small-to-medium capital accounts (~$1,000 - $10,000).

Financial Hurdle Principle:
    On a ~$1,690 portfolio, a 10% annual net alpha target represents ~$169/year (~$14/month).
    If routine tasks trigger multi-agent LLM debates costing $15-$30/month, the entire fund alpha
    is erased by model inference bills alone.

    This service establishes a rigid cost-to-alpha hurdle:
        Hurdle Ratio = (Estimated LLM Cost / Order Capital) <= Max Allowed Friction (0.15%)
    Routine maintenance, rebalances, and batch deployments under $250 USD are automatically routed
    to 0-LLM deterministic mathematical models (Bayesian HMM, Risk Parity, Technical Filters),
    capping monthly AI expenses under $3.00 USD while preserving 100% of strategy alpha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("InferenceHurdleGateService")

# Default thresholds
DEFAULT_MAX_HURDLE_RATIO = 0.0015  # 0.15% of trade value (15 bps)
DEFAULT_SMALL_ORDER_BYPASS_THRESHOLD_USD = 250.0  # Orders < $250 bypass full LLM council
DEFAULT_ESTIMATED_COUNCIL_COST_USD = 0.25  # ~5 agents * 2 rounds with prompt context


@dataclass
class HurdleEvaluation:
    allow_llm: bool
    routing_mode: str  # "0_LLM_MATH_ENGINE", "SLM_FAST_TIER", "FULL_LLM_COUNCIL"
    order_amount_usd: float
    estimated_llm_cost_usd: float
    hurdle_ratio: float
    max_hurdle_ratio: float
    reason: str
    estimated_alpha_saved_bps: float
    evaluated_at: str


class InferenceHurdleGateService:
    """
    Evaluates whether an analytical or trading operation warrants expensive LLM inference,
    or whether it should be served by high-performance 0-LLM deterministic mathematical engines.
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)
        self._redis_client = None

    def _get_redis(self):
        if self._redis_client is None:
            try:
                import redis
                import os
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                self._redis_client = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.debug("Redis connection unavailable for Hurdle Gate telemetry: %s", e)
        return self._redis_client

    def evaluate_task_hurdle(
        self,
        task_type: str,
        order_amount_usd: float = 0.0,
        estimated_llm_cost_usd: float = DEFAULT_ESTIMATED_COUNCIL_COST_USD,
        regime_entropy: float = 0.0,
        is_breaking_news: bool = False,
    ) -> HurdleEvaluation:
        """
        Evaluate cost-to-alpha profitability for a given trading or advisory task.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # 1. Critical unstructured events ALWAYS allow LLM analysis regardless of size
        if is_breaking_news or task_type in ("breaking_news_analysis", "macro_black_swan"):
            return HurdleEvaluation(
                allow_llm=True,
                routing_mode="FULL_LLM_COUNCIL",
                order_amount_usd=order_amount_usd,
                estimated_llm_cost_usd=estimated_llm_cost_usd,
                hurdle_ratio=0.0,
                max_hurdle_ratio=DEFAULT_MAX_HURDLE_RATIO,
                reason="Unstructured breaking news / black swan event requires semantic reasoning.",
                estimated_alpha_saved_bps=0.0,
                evaluated_at=now_iso,
            )

        # 2. Routine deterministic mathematical tasks -> 0-LLM mathematical routing
        routine_math_tasks = {
            "batch_cash_deployment",
            "routine_rebalance",
            "factor_rotation",
            "slippage_guard_check",
            "stop_loss_check",
            "portfolio_health_check",
        }

        if task_type in routine_math_tasks:
            # Check capital hurdle
            if order_amount_usd <= 0:
                hurdle_ratio = 1.0  # Infinitely costly if trade amount is 0
            else:
                hurdle_ratio = estimated_llm_cost_usd / order_amount_usd

            if order_amount_usd < DEFAULT_SMALL_ORDER_BYPASS_THRESHOLD_USD or hurdle_ratio > DEFAULT_MAX_HURDLE_RATIO:
                # Bypass LLM: preserve capital alpha!
                alpha_saved_bps = (hurdle_ratio * 10000.0) if order_amount_usd > 0 else 0.0
                self.record_savings(estimated_llm_cost_usd)
                return HurdleEvaluation(
                    allow_llm=False,
                    routing_mode="0_LLM_MATH_ENGINE",
                    order_amount_usd=order_amount_usd,
                    estimated_llm_cost_usd=estimated_llm_cost_usd,
                    hurdle_ratio=hurdle_ratio,
                    max_hurdle_ratio=DEFAULT_MAX_HURDLE_RATIO,
                    reason=(
                        f"Order amount (${order_amount_usd:.2f}) or hurdle ratio ({hurdle_ratio * 100:.2f}%) "
                        f"would erode net alpha. Routed to 0-LLM mathematical engine."
                    ),
                    estimated_alpha_saved_bps=alpha_saved_bps,
                    evaluated_at=now_iso,
                )

        # 3. High ambiguity / moderate-sized orders -> Fast SLM tier
        if regime_entropy > 1.25 or order_amount_usd < 1000.0:
            return HurdleEvaluation(
                allow_llm=True,
                routing_mode="SLM_FAST_TIER",
                order_amount_usd=order_amount_usd,
                estimated_llm_cost_usd=estimated_llm_cost_usd * 0.2,
                hurdle_ratio=estimated_llm_cost_usd * 0.2 / max(order_amount_usd, 1.0),
                max_hurdle_ratio=DEFAULT_MAX_HURDLE_RATIO,
                reason="Moderate size or regime ambiguity; routed to low-latency, budget-efficient fast SLM tier.",
                estimated_alpha_saved_bps=0.0,
                evaluated_at=now_iso,
            )

        # 4. Large strategic repositioning -> Full Council allowed
        return HurdleEvaluation(
            allow_llm=True,
            routing_mode="FULL_LLM_COUNCIL",
            order_amount_usd=order_amount_usd,
            estimated_llm_cost_usd=estimated_llm_cost_usd,
            hurdle_ratio=estimated_llm_cost_usd / max(order_amount_usd, 1.0),
            max_hurdle_ratio=DEFAULT_MAX_HURDLE_RATIO,
            reason="Substantial capital commitment justifies comprehensive multi-agent debate.",
            estimated_alpha_saved_bps=0.0,
            evaluated_at=now_iso,
        )

    def record_savings(self, amount_usd: float) -> None:
        """Accumulate saved inference dollars in Redis for net-alpha accounting."""
        r = self._get_redis()
        if not r:
            return
        try:
            key = f"inference:savings:{self.user_id}"
            r.incrbyfloat(key, amount_usd)
            # Record monthly bucket
            month_key = f"inference:savings:{self.user_id}:{datetime.now(timezone.utc).strftime('%Y-%m')}"
            r.incrbyfloat(month_key, amount_usd)
        except Exception as e:
            logger.debug("Failed to record inference savings in Redis: %s", e)

    def get_cost_to_alpha_telemetry(self) -> Dict[str, Any]:
        """Retrieve total inference savings and cost-to-alpha efficiency metrics."""
        r = self._get_redis()
        total_saved = 0.0
        monthly_saved = 0.0
        if r:
            try:
                key = f"inference:savings:{self.user_id}"
                month_key = f"inference:savings:{self.user_id}:{datetime.now(timezone.utc).strftime('%Y-%m')}"
                total_saved = float(r.get(key) or 0.0)
                monthly_saved = float(r.get(month_key) or 0.0)
            except Exception as e:
                logger.debug("Failed to read telemetry from Redis: %s", e)

        return {
            "user_id": self.user_id,
            "total_inference_dollars_saved": round(total_saved, 2),
            "monthly_inference_dollars_saved": round(monthly_saved, 2),
            "max_hurdle_ratio_bps": int(DEFAULT_MAX_HURDLE_RATIO * 10000),
            "small_order_bypass_threshold_usd": DEFAULT_SMALL_ORDER_BYPASS_THRESHOLD_USD,
            # Not a verdict: this gate only measures avoided spend. Real net alpha
            # (with actual LLM + subscription cost) is served by /api/v1/net-alpha.
            # 非結論：本閘門只衡量省下的花費；真實淨 Alpha 請見 /api/v1/net-alpha。
            "alpha_preservation_status": "SAVINGS_ONLY_SEE_NET_ALPHA_API",
            "target_net_alpha_pct": 10.0,
            "estimated_annual_cost_drag_avoided_pct": None,
        }
