import json
from .base_agent import BaseAgent

class MomentumAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="Momentum", prompt_path="prompts/momentum_agent.txt", use_cache=use_cache, ttl_hours=4)

    def run(self, context):
        """
        context: {
            "ticker": "AAPL",
            "price_data": {...},
            "indicators": {...}
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        
        # Prepare data for prompt rendering
        prompt_data = {
            "ticker": ticker,
            "price_data": json.dumps(context.get("price_data", {}), indent=2, ensure_ascii=False),
            "indicators": json.dumps(context.get("indicators", {}), indent=2, ensure_ascii=False)
        }
        
        system_prompt_rendered = self.render_system_prompt(prompt_data)
        user_prompt = f"Analyze {ticker} based on the provided technical data."

        response = self._mock_llm_call(user_prompt, system_prompt_rendered)
        
        if "Mock response" in response:
            return f"""
### {ticker} 分析報告 (Mock)
*   **趨勢判斷**: Neutral
*   **關鍵價位**: 支撐 145 | 壓力 155
*   **動能儀表板**:
    *   均線: 5MA, 10MA 糾結
    *   RSI: 52 (中性)
    *   成交量: 縮量整理
*   **結論**: 暫時觀望，等待突破關鍵價位。
"""
        return response
