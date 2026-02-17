from typing import List, Any, Optional, Dict
import json
import logging
from src.services.memory_service import ILLMProvider
from src.agents.factory import AgentFactory

logger = logging.getLogger(__name__)

class AgentLLMProvider(ILLMProvider):
    """
    Adapts existing Agents to provide LLM services for MemoryService.
    Uses 'Engineer' or 'CIO' agents for specific cognitive tasks.
    """
    
    def __init__(self, user_id: str = "system"):
        self.user_id = user_id
        # We can use a generic agent for these tasks, e.g., Engineer or a new 'Utility' agent
        # Using 'Engineer' agent as it's typically for system tasks
        self.agent = AgentFactory.create_agent("Engineer", use_cache=True, user_id=user_id)

    def summarize(self, text: str) -> str:
        """
        Summarize report content using the agent.
        """
        prompt = f"""
        TASK: Summarize the following investment report into a concise context block (max 500 words).
        Focus on: Market View, Top Recommendations, and Risks.
        
        REPORT:
        {text[:15000]} 
        """
        try:
            # The agent might return a dict or string
            response = self.agent.run(prompt)
            if isinstance(response, dict):
                return str(response.get("content") or response.get("output") or response)
            return str(response)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return text[:1000] + "..." # Fallback

    def check_contradictions(self, new_text: str, context_text: str) -> List[str]:
        """
        Check for contradictions.
        """
        prompt = f"""
        TASK: Detect logical contradictions between the Historical View and New Analysis.
        Return ONLY a JSON list of strings, e.g. ["Contradiction: ..."]. Return [] if none.
        
        HISTORICAL VIEW:
        {context_text}
        
        NEW ANALYSIS:
        {new_text}
        """
        try:
            response = self.agent.run(prompt)
            # Normalize to string safely
            if isinstance(response, dict):
                # Try common keys
                response_str = str(response.get("content", "")) or str(response.get("output", "")) or str(response)
            else:
                response_str = str(response)
                
            # Basic parsing logic for JSON list
            import re
            match = re.search(r"\[.*\]", response_str.replace('\n', ' '))
            if match:
                 return json.loads(match.group(0))
            return []
        except Exception as e:
            logger.error(f"Contradiction check failed: {e}")
            return []
