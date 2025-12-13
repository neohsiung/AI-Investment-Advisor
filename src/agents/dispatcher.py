import json
from .base_agent import BaseAgent

class DispatcherAgent(BaseAgent):
    def __init__(self, use_cache=True):
        # Dispatcher use FAST tier model
        super().__init__(name="Dispatcher", prompt_path="prompts/dispatcher_agent.txt", use_cache=use_cache, ttl_hours=24, tier="fast")

    def run(self, context):
        """
        context: {
            "user_input": "..."
        }
        """
        user_input = context.get("user_input", "")
        
        # Simple injection
        prompt_content = f"User Input: {user_input}"
        
        # Dispatcher prompt is simple, likely doesn't need Jinja2 template if we just append input.
        # But BaseAgent usually expects system_prompt to be the instruction.
        # We append user input to the call.
        
        # Check cache manually or let base handle it? Base handles it.
        # But user input varies a lot.
        
        try:
            response_str = self._call_real_llm(prompt_content, self.system_prompt)
            
            # Parse JSON
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception as e:
            self.logger.error(f"Dispatcher failed: {e}")
            # Fallback
            return {
                "agents": ["CIO"],
                "tickers": [],
                "intent": "general_chat",
                "error": str(e)
            }
