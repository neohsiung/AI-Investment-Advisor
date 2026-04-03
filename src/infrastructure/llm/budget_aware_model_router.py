"""
Budget Aware Model Router — Infrastructure Layer.
具備預算意識的模型路由器 — 基礎設施層。

Implements tiered model routing with automatic fallback based on weekly spend.
實作具備週預算自動降級機制的模型分流。
"""

import logging
from typing import Dict, Any, Optional
from src.domain.interfaces import LLMConfig
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService
from src.infrastructure.llm.tier_config import TierConfig

logger = logging.getLogger(__name__)

class BudgetAwareModelRouter:
    """
    Router that provides LLM configurations based on requested tier and current budget.
    """
    
    # Budget thresholds as per Phase 6 Implementation Plan
    BUDGET_SOFT_LIMIT = 16.0  # 80% (Warn / Partial Downgrade)
    BUDGET_HARD_LIMIT = 20.0  # 100% (Emergency / Full Downgrade)

    def __init__(self, settings_service: SettingsService, 
                 token_logger: TokenLoggerService):
        self.settings = settings_service
        self.token_logger = token_logger
        self.tier_cfg = TierConfig()

    def get_config(self, requested_tier: str, user_id: str = None) -> LLMConfig:
        """
        Get the appropriate LLMConfig for the requested tier, potentially downgraded
        due to budget constraints.
        
        Args:
            requested_tier: "nano", "fast", "smart", "advanced"
            user_id: The internal user ID to check budget for.
            
        Returns:
            LLMConfig for the (potentially downgraded) tier.
        """
        user_id = user_id or self.settings.user_id
        if not user_id:
            # Fallback for system-level or uninitialized calls
            return self._build_config(requested_tier, "")

        # 1. Fetch current spend (cached/aggregated in DB)
        spend_summary = self.token_logger.get_user_spending(user_id, days=7)
        total_spent = spend_summary.get("total_cost", 0.0)
        
        # 2. Determine effective tier based on budget
        effective_tier = self._resolve_tier(requested_tier, total_spent)
        
        if effective_tier != requested_tier:
            logger.warning(
                f"BudgetAwareRouter: Downgrading {requested_tier} -> {effective_tier} "
                f"due to spend ${total_spent:.2f}"
            )
            
        # 3. Build the final Config
        return self._build_config(effective_tier, user_id)

    def is_budget_critical(self, user_id: str = None) -> bool:
        """
        Check if the weekly budget has reached the soft limit ($16.0). [Phase 7]
        """
        user_id = user_id or self.settings.user_id
        if not user_id:
            return False
            
        spend_summary = self.token_logger.get_user_spending(user_id, days=7)
        total_spent = spend_summary.get("total_cost", 0.0)
        
        return total_spent >= self.BUDGET_SOFT_LIMIT

    def _resolve_tier(self, requested: str, spend: float) -> str:
        """
        Logic for tier downgrading.
        """
        # Hard Limit reached: Force everything to 'fast'
        if spend >= self.BUDGET_HARD_LIMIT:
            return "fast"
        
        # Soft Limit reached: Downgrade 'smart' or 'advanced' to 'fast'
        if spend >= self.BUDGET_SOFT_LIMIT:
            if requested in ["smart", "advanced"]:
                return "fast"
            
        return requested

    def _build_config(self, tier_name: str, user_id: str) -> LLMConfig:
        """
        Internal mapping from tier name to actual LLMConfig using TierConfig.
        """
        # Fetch DB overrides if any
        db_settings = self.settings.get_all_settings() if user_id else {}
        
        # Resolve model name (DB -> Env -> Default)
        model_name = self.tier_cfg.resolve(tier_name, db_settings)
        spec = self.tier_cfg.get_spec(tier_name)
        
        # Provider resolution (Check AI_PROVIDER first for standards compliance)
        provider = db_settings.get("AI_PROVIDER", db_settings.get("ai_provider", "OpenRouter")) if user_id else "OpenRouter"
        
        # API Key Mapping (source_{provider}_api_key or legacy API_KEY)
        api_key_field = f"source_{provider.lower()}_api_key"
        # Support fallback to legacy "API_KEY"
        api_key = db_settings.get(api_key_field, db_settings.get("API_KEY", "")) if user_id else ""
        
        return LLMConfig(
            provider=provider,
            model=model_name,
            api_key=api_key,
            temperature=0.7,
            max_tokens=spec.max_tokens if spec else None
        )
