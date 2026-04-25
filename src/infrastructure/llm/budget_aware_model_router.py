"""
Budget Aware Model Router — Infrastructure Layer.
具備預算意識的模型路由器 — 基礎設施層。

Implements tiered model routing with automatic fallback based on weekly spend.
實作具備週預算自動降級機制的模型分流。

Phase B extension:
  - get_config_chain(user_id, tier, db_session=None) -> list[ModelCandidate]
    Returns the full fallback chain from DB (or legacy defaults).
  - get_resilient_gateway(user_id, tier, db_session=None) -> ResilientLLMPipeline
    Returns a ready-to-use pipeline for the given tier.
  - Existing get_config() / is_budget_critical() / _resolve_tier() unchanged.
"""

import logging
from typing import Any, Dict, List, Optional
from src.domain.interfaces import LLMConfig
from src.infrastructure.llm.tier_config import TierConfig

logger = logging.getLogger(__name__)

class BudgetAwareModelRouter:
    """
    Router that provides LLM configurations based on requested tier and current budget.
    """
    
    # Budget thresholds as per Phase 6 Implementation Plan
    BUDGET_SOFT_LIMIT = 16.0  # 80% (Warn / Partial Downgrade)
    BUDGET_HARD_LIMIT = 20.0  # 100% (Emergency / Full Downgrade)

    def __init__(self, settings_service,
                 token_logger):
        # Lazy imports to avoid circular dependency with TokenLoggerService/SettingsService
        from src.services.settings_service import SettingsService
        from src.services.token_logger_service import TokenLoggerService
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
        [LEGACY PATH] Reads AI_MODEL / AI_MODEL_ADVANCED / … from settings table.
        Prefer get_config_chain() which reads llm_tier_bindings instead.
        """
        # Fetch DB overrides if any
        db_settings = self.settings.get_all_settings(user_id) if user_id else {}
        
        # Resolve model name (DB -> Env -> Default)
        model_name = self.tier_cfg.resolve(tier_name, db_settings)
        if isinstance(model_name, str):
            model_name = model_name.strip().strip('"').strip("'")

        spec = self.tier_cfg.get_spec(tier_name)
        
        # Provider resolution (Check AI_PROVIDER first for standards compliance)
        import os
        env_provider = os.getenv("AI_PROVIDER", "OpenRouter")
        provider = db_settings.get("AI_PROVIDER", db_settings.get("ai_provider", env_provider)) if user_id else env_provider
        
        # API Key Mapping (source_{provider}_api_key or {provider}_api_key or legacy API_KEY)
        api_key_field = f"source_{provider.lower()}_api_key"
        direct_provider_key = f"{provider.lower()}_api_key"
        
        # Support fallback across different naming conventions used in DB
        raw_key = ""
        if user_id:
            raw_key = db_settings.get(api_key_field) or db_settings.get(direct_provider_key) or db_settings.get("API_KEY", "")
            
        api_key = raw_key.strip().strip('"').strip("'") if isinstance(raw_key, str) else raw_key
        
        return LLMConfig(
            provider=provider,
            model=model_name,
            api_key=api_key,
            temperature=0.7,
            max_tokens=spec.max_tokens if spec else None
        )

    # ──────────────────────────────────────────────────────────────────
    # Phase B extensions — DB-driven chain resolution
    # ──────────────────────────────────────────────────────────────────

    def get_config_chain(
        self,
        user_id: str,
        tier: str,
        db_session: Any = None,
        agent_name: Optional[str] = None,
    ) -> List[Any]:
        """
        Return the full ModelCandidate chain for (user_id, tier).

        If agent_name is provided and the user has an enabled override for that
        agent, the AgentOverrideService.resolve() is called first; it may return
        a custom chain (different models or tier) or fall back to the tier chain.

        The returned list is budget-aware: if the user is over the soft limit,
        smart/advanced chains are replaced with the fast chain.

        Args:
            user_id: The user whose binding to load.
            tier: One of "nano", "fast", "smart", "advanced".
            db_session: Optional SQLAlchemy session.
            agent_name: Optional agent identifier (e.g. "cio", "skill_router").
                        If provided, agent overrides are checked first.

        Returns:
            list[ModelCandidate] — ordered primary-first.
        """
        from src.infrastructure.llm.llm_config_chain import build_config_chain

        # Budget-aware tier downgrade (same logic as get_config)
        try:
            spend_summary = self.token_logger.get_user_spending(user_id, days=7)
            total_spent = spend_summary.get("total_cost", 0.0)
            effective_tier = self._resolve_tier(tier, total_spent)
        except Exception:
            effective_tier = tier

        if effective_tier != tier:
            logger.warning(
                "BudgetAwareRouter.get_config_chain: downgrading %s → %s for user %s",
                tier, effective_tier, user_id,
            )

        # ── Agent override resolution (Phase C) ───────────────────────
        if agent_name:
            try:
                from src.services.llm_agent_override_service import LLMAgentOverrideService
                override_svc = LLMAgentOverrideService(user_id=user_id)
                candidates = override_svc.resolve(
                    agent_name=agent_name,
                    default_tier=effective_tier,
                    db_session=db_session,
                )
                if candidates:
                    logger.debug(
                        "BudgetAwareRouter.get_config_chain: agent=%s resolved %d candidate(s)",
                        agent_name, len(candidates),
                    )
                    return candidates
            except Exception as exc:
                logger.warning(
                    "BudgetAwareRouter.get_config_chain: agent override resolution failed "
                    "for agent=%s user=%s: %s — falling back to tier chain",
                    agent_name, user_id, exc,
                )

        return build_config_chain(
            user_id=user_id,
            tier=effective_tier,
            db_session=db_session,
        )

    def get_resilient_gateway(
        self,
        user_id: str,
        tier: str,
        db_session: Any = None,
    ) -> Any:
        """
        Return a ResilientLLMPipeline configured for (user_id, tier).

        Existing callers that use get_config() are unaffected.
        New callers can use this for automatic multi-model fallback.

        Returns:
            ResilientLLMPipeline instance ready to call .execute(messages).
        """
        from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

        chain = self.get_config_chain(user_id=user_id, tier=tier, db_session=db_session)
        return ResilientLLMPipeline(config_chain=chain)
