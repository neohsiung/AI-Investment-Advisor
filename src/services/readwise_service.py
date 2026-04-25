import typing
import os
import json
import re
import asyncio
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable

from src.data.providers.readwise_provider import ReadwiseProvider
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

logger = setup_logger("ReadwiseService")

class ReadwiseService:
    """
    Readwise Service to process highlights and determine if they are investment-related or require actions.
    Readwise 服務，用來處理畫線筆記並判斷是否與投資相關或需要觸發行動。
    
    PAD Phase 2: Migrated to SettingsAwareModelRouter + OpenRouterGateway
    """
    
    def __init__(self, user_id: str = "system", readwise_provider: ReadwiseProvider = None, settings_service: Optional[SettingsService] = None):
        self.user_id = user_id
        self.provider = readwise_provider or ReadwiseProvider(user_id=user_id)
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        
        # PAD Phase 2: Initialize router and gateway for LLM calls
        from src.data.database import get_db_engine
        self.settings_repo = AlchemySettingsRepository(engine=get_db_engine())
        self.model_router = SettingsAwareModelRouter(self.settings_repo)
        self.gateway = OpenRouterGateway()
        
    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "fast", 
                              temperature: float = 0.7, max_tokens: int = 1500) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role.
        """
        try:
            model = self.model_router.get_model(self.user_id, tier)
            if not model:
                logger.warning(f"Failed to route model for tier={tier}, using fallback")
                return json.dumps({"status": "failed", "error": "No model routed"})
            
            # Determine system prompt based on agent name
            agent_prompts = {
                "Analyst": "You are an investment highlight analyzer. Analyze highlights for investment relevance and required actions. Return valid JSON.",
            }
            
            system_prompt = agent_prompts.get(agent_name, f"You are a {agent_name}.")
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]
            
            config = LLMConfig(
                provider=os.getenv("AI_PROVIDER", "OpenRouter"),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            logger.debug(f"ReadwiseService: Calling {agent_name} agent via {model}")
            response = await self.gateway.chat(messages, config)
            
            if not isinstance(response, str):
                logger.error(f"ReadwiseService: Unexpected response type from gateway: {type(response)}")
                return json.dumps({"status": "failed", "error": f"Invalid response type: {type(response)}"})
            
            return response
        except Exception as e:
            logger.error(f"ReadwiseService: {agent_name} agent failed: {e}")
            return json.dumps({"status": "failed", "error": str(e)})
        
    def fetch_and_analyze_highlights(self, updated_after: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch highlights and analyze them for investment relevance.
        獲取畫線筆記並分析其投資相關性。
        """
        try:
            highlights = self.provider.fetch_highlights(updated_after=updated_after)
            analyzed_highlights = []
            
            for highlight in highlights:
                text = highlight.get("text", "")
                if not text:
                    continue
                    
                # /highlights endpoint does not return book title, use book_id if needed
                # For basic analysis, the text itself and the user's note is usually sufficient
                book_id = highlight.get("book_id", "Unknown Book ID")
                
                # PAD Phase 2: Use async analysis
                analysis = asyncio.run(self.analyze_highlight_async(
                    text, book_id=str(book_id), note=highlight.get("note", "")
                ))
                
                # Ensure analysis is a dict before calling .get()
                if isinstance(analysis, dict) and analysis.get("is_investment_related"):
                    analyzed_highlights.append({
                        "id": highlight.get("id"),
                        "text": text,
                        "note": highlight.get("note", ""),
                        "book_id": book_id,
                        "source_url": highlight.get("url", ""),
                        "highlighted_at": highlight.get("highlighted_at"),
                        "analysis": analysis
                    })
                        
            return analyzed_highlights
        except Exception as e:
            logger.error(f"Failed to fetch and analyze highlights: {e}")
            return []

    async def analyze_highlight_async(self, highlight_text: str, book_id: str = "", note: str = "") -> Dict[str, Any]:
        """
        Asynchronously analyze a specific highlight text using LLM.
        使用 LLM 非同步分析特定的畫線內容。
        PAD Phase 2: Async implementation via gateway
        """
        context = {
            "highlight_text": highlight_text,
            "book_id": book_id,
            "user_note": note,
            "task": "Analyze if this highlight is investment-related and requires action"
        }
        
        try:
            response = await self._call_agent_llm("Analyst", context, tier="fast", temperature=0.5, max_tokens=500)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Highlight analysis failed: {e}")
            return {
                "is_investment_related": False,
                "requires_action": False,
                "reasoning": f"Analysis failed: {str(e)}",
                "suggested_action": None
            }

    def analyze_highlight(self, highlight_text: str, book_id: str = "", note: str = "") -> Dict[str, Any]:
        """
        Synchronous wrapper for analyze_highlight_async (for backward compatibility).
        使用 LLM 分析特定的畫線內容。
        """
        return asyncio.run(self.analyze_highlight_async(highlight_text, book_id, note))
            
    def _parse_json_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse JSON response from LLM, with multiple fallback strategies.
        """
        if isinstance(response, dict) and "is_investment_related" in response:
            return response
            
        response_str = ""
        if isinstance(response, dict):
             response_str = (
                 str(response.get("content", "")) 
                 or str(response.get("output", "")) 
                 or str(response)
             )
        else:
             response_str = str(response)
             
        # Extract json object using regex
        match = re.search(r"\{.*\}", response_str, re.DOTALL | re.IGNORECASE)
        if match:
             try:
                 obj = json.loads(match.group(0))
                 return obj
             except json.JSONDecodeError as e:
                 logger.warning(f"Error decoding JSON response: {e}, raw string: {match.group(0)}")
                 # Fallback to simple matching if json is malformed
                 pass
                 
        # Additional fallback logic
        is_investment = "true" in response_str.lower() or "investment_related\": true" in response_str.lower()
        requires_action = "requires_action\": true" in response_str.lower()
        
        return {
            "is_investment_related": is_investment,
            "requires_action": requires_action,
            "reasoning": response_str[:100],
            "suggested_action": None
        }
