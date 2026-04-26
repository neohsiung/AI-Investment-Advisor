import logging
import json
import os
from datetime import datetime
from dataclasses import replace
from typing import Optional, Dict, Any

from src.domain.interfaces import Message, LLMConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.utils.async_utils import to_thread
from src.prompts.reflection_prompt import ReflectionPrompt
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService
from src.services.evolution_metrics import EvolutionMetrics
from src.services.reflection_manager import ReflectionManager

logger = logging.getLogger(__name__)

class SkillRouter:
    """
    Routes simple user intents directly to skills, bypassing the swarm.
    將簡單的使用者意圖直接路由到技能，跳過 Swarm。
    """

    # Intents that can be handled directly via skills
    DIRECT_SKILL_MAP = {
        "price": "get_market_data",
        "holdings": "get_user_holdings",
        "portfolio": "get_user_holdings",
        "macro": "get_macro_summary",
        "vix": "get_macro_summary",
        "momentum": "run_momentum_analysis",
    }

    def __init__(self, user_id: str, tier: str = "fast"):
        self.user_id = user_id
        self.tier = tier
        self._llm = None
        self._config = None

    def _get_config(self):
        if self._config is None:
            from src.services.settings_service import SettingsService
            from src.services.token_logger_service import TokenLoggerService
            from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter
            
            svc = SettingsService(user_id=self.user_id)
            router = BudgetAwareModelRouter(svc, TokenLoggerService())
            # [STRICT] Must use BudgetAwareModelRouter. No fallbacks allowed.
            self._config = router.get_config(self.tier, self.user_id)
        return self._config

    def _get_llm(self):
        if self._llm is None:
            config = self._get_config()
            self._llm = LLMGatewayFactory.create(config.provider)
        return self._llm

    async def route(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Attempts to route the message to a direct skill execution.
        Returns the skill result string if matched, otherwise None.
        """
        msg_lower = user_message.lower()
        
        # 1. Simple heuristic check (Keywords)
        matched_skill = None
        for keyword, skill_name in self.DIRECT_SKILL_MAP.items():
            if keyword in msg_lower:
                matched_skill = skill_name
                break
        
        if not matched_skill:
            # 2. Fast-tier LLM classification for slightly more complex but still direct intents
            from src.utils.prompt_utils import load_agent_prompt
            
            try:
                llm = self._get_llm()
                config = self._get_config()
                
                system_prompt = load_agent_prompt("skill_router_classifier")
                classification_prompt = load_agent_prompt("skill_router_classifier", {"user_message": user_message})
                
                messages = [
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=classification_prompt),
                ]
                category = await llm.chat(messages=messages, config=config)
                category = category.strip().upper()
                
                if "PRICE_CHECK" in category:
                    matched_skill = "get_market_data"
                elif "PORTFOLIO_CHECK" in category:
                    matched_skill = "get_user_holdings"
                elif "MACRO_CHECK" in category:
                    matched_skill = "get_macro_summary"
                else:
                    return None # Default to complex swarm flow
            except Exception as e:
                logger.warning(f"SkillRouter: Classification failed: {e}")
                return None

        # 3. Execute the matched skill
        try:
            
                                    
            # Simple keyword extraction for ticker if it's price/momentum
            import re
            ticker_match = re.search(r'\b([A-Z]{2,5})\b', user_message.upper())
            ticker = ticker_match.group(1) if ticker_match else None
            
            skill_kwargs = {}
            if ticker:
                skill_kwargs["ticker"] = ticker
            
            logger.info(f"SkillRouter: Directly executing skill {matched_skill} for ticker {ticker}")
            
            return await self._run_skill_via_loader(matched_skill, skill_kwargs, user_message)
            
        except Exception as e:
            logger.error(f"SkillRouter: Execution failed for {matched_skill}: {e}")
            return None

    async def _run_skill_via_loader(self, skill_name: str, kwargs: Dict[str, Any], user_message: str) -> Optional[str]:
        """
        [Phase 6] Self-healing skill execution with reflection.
        具備自我修復（反思）機制的技能執行。
        """
        manager = ReflectionManager(user_id=self.user_id)
        try:
            return await self._agent.run_script(skill_name, **kwargs)
        except Exception as e:
            logger.warning(f"Skill routing failed locally: {e}. Attempting self-correction.")
            # [Task 6.1] Event-driven Self-Correction (Sentinel)
            await manager.reflect_on_error(
                error_context=str(e),
                failed_intent=user_message,
                user_id=self.user_id
            )
            
            # 1. Reflect on the failure
            reflection = await self._reflect_on_error(skill_name, kwargs, str(e))
            
            # 2. Act based on reflection
            if reflection and reflection.get("recommended_action") == "retry":
                corrected_args = reflection.get("corrected_args", {})
                logger.info(f"SkillRouter: Reflection suggested RETRY with args: {corrected_args}")
                try:
                    return await self._agent.run_script(skill_name, **corrected_args)
                except Exception as retry_e:
                    logger.error(f"SkillRouter: Retry failed for '{skill_name}': {retry_e}")
                    return f"System: [Reflection Retry Failed] {retry_e}"
            
            # Cannot self-heal or reflection suggests failing/alternative (not fully implemented yet)
            logger.error(f"SkillRouter: Tool failed and reflection could not recover: {e}")
            return f"System: [Tool Error] {e}"

    

    async def _reflect_on_error(self, tool_name: str, args: Any, error: str) -> Optional[Dict[str, Any]]:
        """
        Invokes a Smart model to analyze and fix the tool call. [Phase 7]
        Delegates to ReflectionManager.
        """
        manager = ReflectionManager(user_id=self.user_id)
        return await manager.reflect_on_error(
            tool_name=tool_name,
            args=args,
            error=str(error),
            agent_name="SkillRouter"
        )

