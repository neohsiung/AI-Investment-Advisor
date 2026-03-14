import json
from src.agents.base_agent import BaseAgent

class SentinelAgent(BaseAgent):
    """
    Sentinel Agent: Specialized coordinator for classifying and prioritizing incoming triggers.
    哨兵智能體：專門負責對傳入的觸發事件進行分類與優先級評定的協調者。
    """
    def __init__(self, use_cache=True, tier="smart", **kwargs):
        super().__init__(
            name="Sentinel", 
            prompt_path="prompts/sentinel_agent.txt", 
            use_cache=use_cache, 
            ttl_hours=1,  # Sentinel results are time-sensitive
            tier=tier, 
            **kwargs
        )

    def run(self, context):
        """
        Evaluate priority for a trigger.
        context expects:
        - 'trigger_source': Internal/Webhook/etc.
        - 'event_data': The raw data of the event.
        - 'current_vix': Market volatility context.
        """
        trigger_source = context.get('trigger_source', 'unknown')
        event_data = context.get('event_data', {})
        current_vix = context.get('current_vix', 20.0)

        prompt_data = {
            "trigger_source": trigger_source,
            "event_data": json.dumps(event_data, indent=2, ensure_ascii=False),
            "current_vix": current_vix
        }

        # 1. Initial Priority Assessment via Sentinel Prompt
        response_str = self.run_tool_loop(context=prompt_data)
        
        try:
            # Clean up response if it contains markdown or thinking text
            # 精簡：尋找第一個 { 並從那裡開始解析，或使用正則提取
            if "{" in response_str:
                json_part = response_str[response_str.find("{"):response_str.rfind("}")+1]
                result_data = json.loads(json_part)
            else:
                raise ValueError("No JSON object found in response")
            
            # 2. Potential Agent Consultation (If priority is high and target_agent is specified)
            # v2.1: According to user request, we can consult the most relevant agent.
            target_agent = result_data.get("target_agent")
            if target_agent and result_data.get("priority") in ["P1", "P2"]:
                self.logger.info(f"Sentinel consulting {target_agent} for deeper priority validation.")
                
                consult_msg = f"Please confirm if the following event deserves {result_data['priority']} attention: {prompt_data['event_data']}"
                consult_res = self.call_agent(target_agent, consult_msg)
                
                # If sub-agent explicitly downgrades or provides critical insights, we could update rationale.
                # For now, we just log and append info to the rationale.
                result_data["consultation_note"] = f"Consulted {target_agent}: {consult_res[:100]}..."
            
            return result_data

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse or find JSON in SentinelAgent response: {e}\nResponse: {response_str}")
            return {
                "priority": "P2", # Fallback to a safe moderate priority
                "target_agent": "CIO",
                "rationale": f"解析錯誤 ({type(e).__name__})，自動降級為 P2 處理。",
                "error": str(e)
            }
        except Exception as e:
            self.logger.error(f"Error during sentinel prioritization: {e}")
            return {"priority": "P3", "target_agent": "CIO", "error": str(e)}
