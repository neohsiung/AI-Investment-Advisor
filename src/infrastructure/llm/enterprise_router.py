"""
Enterprise Model Router with Automatic Fallback

Implements intelligent model selection and automatic degradation:
- Stage-aware routing (different tiers for different stages)
- Automatic fallback on timeout/error (Smart → Fast → Nano)
- Cost tracking and attribution
- Per-user model tier preferences

Tier Hierarchy:
  Smart (most capable, slowest)     -> google/gemini-2.0-pro-exp-02-05
    ↓
  Fast (balanced)                   -> anthropic/claude-3.5-sonnet
    ↓
  Nano (fastest, least capable)     -> anthropic/claude-3-haiku
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from enum import Enum

from src.infrastructure.llm.tier_config import SettingsAwareModelRouter, TierConfig
from src.repositories.settings_repository import AlchemySettingsRepository
from src.data.database import get_db_engine

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """LLM model tiers with characteristic timeouts."""
    SMART = "smart"      # 120s timeout
    FAST = "fast"        # 90s timeout
    NANO = "nano"        # 60s timeout


# Tier configurations
TIER_CONFIG = {
    ModelTier.SMART: {
        'timeout': 120,
        'max_tokens': 2000,
        'temperature': 0.7,
        'fallback_to': ModelTier.FAST
    },
    ModelTier.FAST: {
        'timeout': 90,
        'max_tokens': 2000,
        'temperature': 0.7,
        'fallback_to': ModelTier.NANO
    },
    ModelTier.NANO: {
        'timeout': 60,
        'max_tokens': 2000,
        'temperature': 0.5,
        'fallback_to': None  # No further fallback
    }
}


class EnterpriseModelRouter(SettingsAwareModelRouter):
    """
    Extended model router with automatic fallback and stage awareness.
    """
    
    def __init__(self, settings_repo: AlchemySettingsRepository = None):
        """
        Initialize router.
        
        Args:
            settings_repo: Settings repository (uses default if None)
        """
        if not settings_repo:
            settings_repo = AlchemySettingsRepository(engine=get_db_engine())
        
        super().__init__(settings_repo)
        self.logger = logger
    
    async def get_model_with_fallback(self, 
                                     user_id: str, 
                                     stage: str = None,
                                     initial_tier: str = None) -> Tuple[str, str]:
        """
        Get model with automatic fallback support.
        
        Args:
            user_id: User identifier
            stage: Stage name (e.g., 'synthesis') for stage-aware routing
            initial_tier: Start with this tier ('smart', 'fast', 'nano'). 
                         If None, read from user settings.
        
        Returns:
            (model_name, tier_used)
            
        Example:
            model, tier = await router.get_model_with_fallback(user_id, stage='synthesis')
        """
        # Determine starting tier
        if initial_tier:
            current_tier = ModelTier(initial_tier)
        else:
            # Read user preference
            tier_name = await self._get_user_tier_preference(user_id)
            current_tier = ModelTier(tier_name)
        
        # Try tiers in fallback chain
        while current_tier:
            try:
                model = self.get_model(user_id, current_tier.value)
                if model:
                    self.logger.info(
                        f"Using {current_tier.value} tier for user {user_id}: {model}"
                    )
                    return model, current_tier.value
            
            except Exception as e:
                self.logger.warning(
                    f"Failed to get {current_tier.value} model: {e}, trying fallback..."
                )
            
            # Move to fallback tier
            next_tier_config = TIER_CONFIG.get(current_tier)
            fallback_tier = next_tier_config.get('fallback_to') if next_tier_config else None
            
            if not fallback_tier:
                raise RuntimeError(f"All model tiers exhausted for user {user_id}")
            
            current_tier = fallback_tier
        
        raise RuntimeError(f"Could not determine any model for user {user_id}")
    
    async def call_llm_with_auto_fallback(self,
                                         user_id: str,
                                         messages: list,
                                         job_id: str = None,
                                         initial_tier: str = None) -> Tuple[str, str, Dict[str, Any]]:
        """
        Call LLM with automatic retry and fallback on timeout/error.
        
        Args:
            user_id: User identifier
            messages: List of Message objects
            job_id: For logging/tracking
            initial_tier: Start with this tier
            
        Returns:
            (response_text, model_used, metadata)
            where metadata includes:
            - tier_used: Which tier was successful
            - attempts: Number of attempts before success
            - fallback_count: How many times fell back to lower tier
            - total_time: Total time spent on this call
        """
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, LLMConfig, Message
        
        gateway = LLMGatewayFactory.create(provider="openrouter")
        
        start_time = datetime.utcnow()
        metadata = {
            'attempts': 0,
            'fallback_count': 0,
            'total_time': 0,
            'attempted_tiers': []
        }
        
        # Determine starting tier
        if initial_tier:
            current_tier = ModelTier(initial_tier)
        else:
            tier_name = await self._get_user_tier_preference(user_id)
            current_tier = ModelTier(tier_name)
        
        last_error = None
        
        # Fallback chain: Smart → Fast → Nano
        while current_tier:
            metadata['attempts'] += 1
            metadata['attempted_tiers'].append(current_tier.value)
            
            if metadata['attempts'] > 1:
                metadata['fallback_count'] += 1
            
            try:
                # Get model for this tier
                model = self.get_model(user_id, current_tier.value)
                if not model:
                    raise ValueError(f"No model available for tier {current_tier.value}")
                
                # Prepare config with tier-specific settings
                config = TIER_CONFIG[current_tier]
                
                llm_config = LLMConfig(
                    provider="openrouter",
                    model=model,
                    temperature=config.get('temperature', 0.7),
                    max_tokens=config.get('max_tokens', 2000)
                )
                
                job_prefix = f"[{job_id}] " if job_id else ""
                logger.info(
                    f"{job_prefix}Attempting {current_tier.value} tier (model: {model}) "
                    f"with {config['timeout']}s timeout"
                )
                
                # Call with timeout
                response = await asyncio.wait_for(
                    gateway.chat(messages, llm_config),
                    timeout=config['timeout']
                )
                
                # Success!
                metadata['total_time'] = (datetime.utcnow() - start_time).total_seconds()
                metadata['model_used'] = model
                metadata['tier_used'] = current_tier.value
                
                logger.info(
                    f"{job_prefix}✅ {current_tier.value} succeeded "
                    f"({metadata['total_time']:.1f}s, {metadata['fallback_count']} fallbacks)"
                )
                
                return response, model, metadata
            
            except asyncio.TimeoutError:
                timeout = config['timeout']
                last_error = f"{current_tier.value} timeout after {timeout}s"
                logger.warning(
                    f"[{job_id}] {current_tier.value} tier timed out after {timeout}s, "
                    f"falling back to next tier..."
                )
            
            except Exception as e:
                last_error = f"{current_tier.value} error: {str(e)}"
                logger.warning(
                    f"[{job_id}] {current_tier.value} tier failed: {e}, "
                    f"falling back to next tier..."
                )
            
            # Move to fallback tier
            tier_config = TIER_CONFIG.get(current_tier)
            fallback_tier = tier_config.get('fallback_to') if tier_config else None
            
            if not fallback_tier:
                # No more tiers to try
                error_msg = f"All model tiers failed. Last error: {last_error}"
                logger.error(f"[{job_id}] {error_msg}")
                raise RuntimeError(error_msg)
            
            current_tier = fallback_tier
    
    async def record_model_usage(self,
                                user_id: str,
                                model: str,
                                tier: str,
                                tokens_input: int,
                                tokens_output: int,
                                cost_usd: float,
                                stage: str = None,
                                job_id: str = None) -> None:
        """
        Record LLM usage for cost attribution and monitoring.
        
        Args:
            user_id: User who consumed the model
            model: Model name
            tier: Tier (smart/fast/nano)
            tokens_input: Input tokens used
            tokens_output: Output tokens used
            cost_usd: Cost in USD
            stage: Pipeline stage (for analysis)
            job_id: Job ID (for tracing)
        """
        # TODO: Write to llm_usage_logs table
        logger.info(
            f"Model usage: user={user_id}, model={model}, tier={tier}, "
            f"tokens_in={tokens_input}, tokens_out={tokens_output}, "
            f"cost=${cost_usd:.4f}, stage={stage}, job_id={job_id}"
        )
    
    async def _get_user_tier_preference(self, user_id: str) -> str:
        """
        Get user's preferred model tier from settings.
        
        Defaults to 'smart' if not specified.
        
        Args:
            user_id: User identifier
            
        Returns:
            Tier name ('smart', 'fast', or 'nano')
        """
        try:
            settings = await self.settings_repo.get_settings(user_id)
            if settings and hasattr(settings, 'llm_tier'):
                tier = settings.llm_tier or 'smart'
            else:
                tier = 'smart'
            return tier
        except Exception as e:
            logger.warning(f"Failed to get tier preference for {user_id}: {e}, defaulting to 'smart'")
            return 'smart'


class ModelFallbackStrategy:
    """
    Encapsulates model fallback decision logic.
    
    Handles:
    - Timeout escalation (immediately fall back)
    - Rate limit errors (exponential backoff before fallback)
    - Transient errors (retry N times before fallback)
    - Model quota exceeded (skip model, try next tier)
    """
    
    def __init__(self):
        self.logger = logger
    
    async def should_fallback(self, 
                             error_type: str,
                             tier: ModelTier,
                             attempt_count: int) -> bool:
        """
        Decide whether to fallback to lower tier based on error type.
        
        Args:
            error_type: Type of error ('timeout', 'rate_limit', 'error', 'quota')
            tier: Current tier being tried
            attempt_count: Number of attempts on this tier
            
        Returns:
            True if should fallback, False if should retry
        """
        if error_type == 'timeout':
            # Immediately fallback on timeout
            return True
        
        elif error_type == 'rate_limit':
            # Retry up to 2 times before falling back
            return attempt_count >= 2
        
        elif error_type == 'quota':
            # Skip this tier immediately
            return True
        
        elif error_type == 'error':
            # Retry up to 3 times before falling back
            return attempt_count >= 3
        
        return False
    
    async def get_retry_delay(self,
                             error_type: str,
                             attempt_count: int) -> float:
        """
        Get delay before retrying (exponential backoff for rate limits).
        
        Args:
            error_type: Type of error
            attempt_count: Attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        if error_type == 'rate_limit':
            # Exponential backoff: 1s, 2s, 4s, 8s, ...
            return min(2 ** attempt_count, 32)
        
        return 0  # No delay for other errors


# Export
__all__ = [
    'EnterpriseModelRouter',
    'ModelTier',
    'ModelFallbackStrategy',
    'TIER_CONFIG'
]
