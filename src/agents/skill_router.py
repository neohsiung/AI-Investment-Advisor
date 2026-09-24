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

    # Default fallback intents if manifest discovery yields none (for isolated tests)
    DEFAULT_DIRECT_SKILL_MAP = {
        "price": "get_market_data",
        "holdings": "get_user_holdings",
        "portfolio": "get_user_holdings",
        "macro": "get_macro_summary",
        "vix": "get_macro_summary",
        "momentum": "run_momentum_analysis",
    }

    # Backward compatibility reference
    DIRECT_SKILL_MAP = DEFAULT_DIRECT_SKILL_MAP

    def get_direct_skill_map(self) -> Dict[str, str]:
        """Resolve direct intent map dynamically from SKILL.md manifests."""
        try:
            from src.agents.skills.skill_loader import SkillLoader
            loader = SkillLoader(user_id=self.user_id)
            mapping = loader.get_direct_skill_map()
            if mapping:
                return mapping
        except Exception as e:
            logger.debug(f"SkillRouter: dynamic skill map load failed, using default: {e}")
        return self.DEFAULT_DIRECT_SKILL_MAP

    def __init__(
        self,
        user_id: str,
        tier: str = "fast",
        use_arbiter: Optional[bool] = None,
        arbiter_client: Optional[Any] = None,
        cognitive_routing_service: Optional[Any] = None,
    ):
        self.user_id = user_id
        self._cognitive_routing_service = cognitive_routing_service
        self._llm = None
        self._config = None
        self._arbiter_client = arbiter_client

        # Resolve tier and reflex eligibility via CognitiveRoutingService if not explicitly specified
        if use_arbiter is None:
            svc = self._get_cognitive_routing_service()
            from src.domain.cognitive_issue_type import CognitiveIssueType
            self.use_arbiter = svc.should_use_reflex(CognitiveIssueType.INTENT_ROUTING, user_id=self.user_id)
        else:
            self.use_arbiter = use_arbiter

        # Effective tier for legacy/fallback path
        svc = self._get_cognitive_routing_service()
        self.tier = tier or svc.get_tier_for_issue(CognitiveIssueType.INTENT_ROUTING, user_id=self.user_id)

    def _get_cognitive_routing_service(self):
        if self._cognitive_routing_service is None:
            from src.services.cognitive_routing_service import CognitiveRoutingService
            self._cognitive_routing_service = CognitiveRoutingService()
        return self._cognitive_routing_service

    def _get_arbiter_client(self):
        if self._arbiter_client is None:
            from src.infrastructure.llm.arbiter_client import ArbiterClient
            self._arbiter_client = ArbiterClient(llm_gateway=self._get_llm())
        return self._arbiter_client

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
        
        # 1. Simple heuristic check (Keywords from dynamic manifest intents)
        matched_skill = None
        direct_map = self.get_direct_skill_map()
        for keyword, skill_name in direct_map.items():
            if keyword in msg_lower:
                matched_skill = skill_name
                break
        
        if not matched_skill:
            if self.use_arbiter:
                # 2a. Reflex Tier: Jev 1.13 毫秒級條件裁決 (置信度不足時自動升級)
                try:
                    question_spec = {
                        "type": "choice",
                        "instructions": "Classify user intent into a specific skill or complex swarm",
                        "criteria": {
                            "PRICE_CHECK": "User asks for stock price quote, ticker status or chart",
                            "PORTFOLIO_CHECK": "User asks about user portfolio holdings, cash or position",
                            "MACRO_CHECK": "User asks about macro economics, inflation, VIX, interest rates",
                            "SWARM": "Complex stock analysis, company valuation, debate or general conversation"
                        }
                    }
                    fallback_prompt = (
                        f"Classify user request: '{user_message}'.\n"
                        "Return JSON with {\"intent\": \"PRICE_CHECK\"|\"PORTFOLIO_CHECK\"|\"MACRO_CHECK\"|\"SWARM\"}"
                    )
                    svc = self._get_cognitive_routing_service()
                    from src.domain.cognitive_issue_type import CognitiveIssueType
                    routing_spec = svc.get_routing_spec(CognitiveIssueType.INTENT_ROUTING, user_id=self.user_id)
                    arbiter = self._get_arbiter_client()
                    decision = await arbiter.decide(
                        domain="skill_router",
                        state={"user_message": user_message},
                        question_key="intent",
                        question_spec=question_spec,
                        confidence_threshold=routing_spec.confidence_threshold,
                        system2_fallback_prompt=fallback_prompt,
                        deterministic_default="SWARM",
                        timeout_ms=routing_spec.timeout_ms,
                    )
                    category = str(decision.choice).upper()
                    if "PRICE_CHECK" in category:
                        matched_skill = "get_market_data"
                    elif "PORTFOLIO_CHECK" in category:
                        matched_skill = "get_user_holdings"
                    elif "MACRO_CHECK" in category:
                        matched_skill = "get_macro_summary"
                    else:
                        return None
                except Exception as e:
                    logger.warning(f"SkillRouter: Arbiter classification failed: {e}")
                    return None
            else:
                # 2b. Legacy Fast-tier LLM classification
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

