import json
from src.agents.base_agent import BaseAgent
from src.services.settings_service import SettingsService

class ThematicAgent(BaseAgent):
    """
    Agent responsible for dynamically updating thematic stock lists and 
    supply chain graphs based on market events using the SettingsService.
    """
    def __init__(self, user_id, use_cache=True, tier="smart", **kwargs):
        super().__init__(
            name="Thematic Optimization", 
            prompt_path="prompts/thematic_agent.txt", 
            use_cache=use_cache, 
            ttl_hours=24, 
            tier=tier, 
            user_id=user_id, 
            **kwargs
        )
        self.settings_service = SettingsService(user_id=self.user_id)

    async def run(self, context):
        """
        Evaluate an event and update thematic settings.
        context expects:
        - 'event_text': The news or event description.
        - 'theme_key': The setting key to update (e.g., 'physical_ai_tickers', 'ai_energy_tickers', 'supply_chain_knowledge_graph')
        - 'current_state': The current value of that setting.
        """
        event_text = context.get('event_text', '')
        theme_key = context.get('theme_key', '')
        current_state = context.get('current_state', {})

        if not event_text or not theme_key:
            self.logger.error("Missing event_text or theme_key in context.")
            return {"status": "error", "message": "Missing context parameters."}

        prompt_data = {
            "event_text": event_text,
            "theme_key": theme_key,
            "current_state": json.dumps(current_state, indent=2, ensure_ascii=False)
        }

        user_prompt = f"Event:\n{event_text}\n\nCurrent State for '{theme_key}':\n{prompt_data['current_state']}\n\nPlease evaluate this event and provide the updated JSON."

        messages = [
            {"role": "system", "content": self.render_system_prompt(prompt_data)},
            {"role": "user", "content": user_prompt}
        ]

        response_str = await self.call_llm(messages, temperature=0.2, response_format={"type": "json_object"})
        
        try:
            # Clean up response if it contains markdown
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            result_data = json.loads(cleaned)
            
            # Apply the update
            if theme_key == "supply_chain_knowledge_graph" and "updated_graph" in result_data:
                success, msg = self.settings_service.save_setting(theme_key, result_data["updated_graph"])
            elif "updated_tickers" in result_data:
                success, msg = self.settings_service.save_setting(theme_key, result_data["updated_tickers"])
            else:
                success, msg = False, "Invalid JSON structure returned by LLM."
                
            if success:
                self.logger.info(f"Successfully updated theme '{theme_key}' based on event.")
            else:
                self.logger.error(f"Failed to update theme '{theme_key}': {msg}")

            return {
                "status": "success" if success else "failed",
                "theme_key": theme_key,
                "rationale": result_data.get("rationale", ""),
                "message": msg
            }

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse ThematicAgent response: {e}\nResponse: {response_str}")
            return {"status": "error", "message": "JSON Parse Error"}
        except Exception as e:
            self.logger.error(f"Error during thematic update: {e}")
            return {"status": "error", "message": str(e)}
