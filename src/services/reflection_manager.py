"""
Reflection Manager Service — Component Layer.
反射管理員服務 — 組件層。

Encapsulates Phase 7 autonomous self-healing logic:
- Budget-aware prompt selection
- Smart tier routing
- Observability tagging & metrics
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import replace

from src.domain.interfaces import Message
from src.prompts.reflection_prompt import ReflectionPrompt
from src.infrastructure.llm import BudgetAwareModelRouter
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService
from src.services.evolution_metrics import EvolutionMetrics
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, LoggingLLMGateway

logger = logging.getLogger(__name__)


class ReflectionManager:
    """
    Centralized service for autonomous error reflection and self-healing.
    集中化服務，用於自主錯誤反射與自癒。
    """

    def __init__(self, user_id: str = "system"):
        self.user_id = user_id
        self.settings = SettingsService(user_id=user_id)
        self.token_logger = TokenLoggerService()
        self.router = BudgetAwareModelRouter(self.settings, self.token_logger)
        self.metrics = EvolutionMetrics()

    async def reflect_on_error(
        self, 
        tool_name: str, 
        args: Any, 
        error: str, 
        agent_name: str = "Agent",
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous reflection call with budget awareness and observability.
        
        Args:
            tool_name: Name of the failed tool
            args: Original arguments sent to the tool
            error: Error message or exception string
            agent_name: Name of the calling agent for logging/tagging
            is_async: Whether the caller is in an async context (for to_thread usage)
            
        Returns:
            Reflection dict or None if failed
        """
        start_time = datetime.utcnow()
        success = False
        action = "none"
        
        try:
            # 1. Budget-Aware Prompt Selection
            is_critical = self.router.is_budget_critical(self.user_id)
            if is_critical:
                logger.info(f"ReflectionManager: Budget critical mode for {agent_name}. Using compressed prompt.")
                prompt = ReflectionPrompt.build_compressed(tool_name, args, error)
            else:
                prompt = ReflectionPrompt.build(tool_name, args, error)
            
            # 2. Tier Selection (Routing)
            config = self.router.get_config("smart", self.user_id)
            config = replace(config, temperature=0.0)
            
            # 3. Provider & Gateway Setup
            provider = self.settings.get_setting("ai_provider", "OpenRouter")
            raw_llm = LLMGatewayFactory.create(provider)
            
            # Wrap with Logging gateway to add metadata tags for Phase 7 observability
            llm = LoggingLLMGateway(
                inner=raw_llm,
                agent_name=agent_name,
                tier="smart",
                user_id=self.user_id,
                metadata={"tag": "reflection", "tool": tool_name}
            )
            
            messages = [Message(role="user", content=prompt)]
            
            # 4. LLM Call (Asynchronous) [Phase 1.2 Fix]
            response = await llm.chat(messages, config)
            
            # 5. Parse JSON response
            cleaned = response.replace("```json", "").replace("```", "").strip()
            if not cleaned.startswith("{"):
                start = cleaned.find("{")
                cleaned = cleaned[start:] if start != -1 else cleaned
                
            reflection = json.loads(cleaned)
            action = reflection.get("recommended_action", "unknown")
            success = True
            return reflection
            
        except Exception as e:
            logger.error(f"ReflectionManager: Reflection failed for {agent_name}: {e}")
            return None
        finally:
            # 6. Record Evolution Metrics
            duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self.metrics.record_reflection_event(
                tool_name=tool_name,
                error_type=type(error).__name__ if not isinstance(error, str) else "GenericError",
                action=action,
                success=success,
                duration_ms=duration
            )
