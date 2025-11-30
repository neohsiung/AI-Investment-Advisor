import json
from .base_agent import BaseAgent

class MomentumAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="MOMENTUM", prompt_path="prompts/momentum_agent.txt", use_cache=use_cache, ttl_hours=1)

    def run(self, context):
        """
        context: {
            "ticker": "AAPL"
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        price = context.get("price", "N/A")
        indicators = context.get("indicators", {})
        
        # 建構 User Prompt
        user_prompt = f"""
        Analyze {ticker}.
        
        [Real-time Data Injection]
        Current Price: {price}
        Technical Indicators: {json.dumps(indicators, indent=2)}
        
        STRICT INSTRUCTION: Use the provided data above. Do NOT hallucinate prices or indicators.
        """
        
        # 呼叫 LLM (Mock)
        response = self._mock_llm_call(user_prompt, self.system_prompt)
        
        # 模擬回傳 JSON
        # 在真實場景中，這裡會解析 LLM 的 JSON 輸出
        if "Mock response" in response:
            mock_result = {
                "signal": "HOLD",
                "confidence": 6,
                "reasoning": f"根據 AI 內部知識庫分析，{ticker} 目前動能中性。"
            }
            return mock_result
            
        return response
