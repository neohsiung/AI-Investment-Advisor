import json
from .base_agent import BaseAgent

class FundamentalAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        tier = kwargs.pop('tier', 'smart')
        super().__init__(name="Fundamental", prompt_path="prompts/fundamental_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    def run(self, context):
        """
        context: {
            "ticker": "AAPL",
            "financials": {...},
            "news": [...]
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        
        prompt_data = {
            "ticker": ticker,
            "financials": json.dumps(context.get("financials", {}), indent=2, ensure_ascii=False),
            "news": json.dumps(context.get("news", []), indent=2, ensure_ascii=False)
        }
        

        response = self.run_tool_loop(context=prompt_data)

        if "Mock response" in response:
            return f"""
### {ticker} 基本面分析 (Mock)
*   **估值評價**: Fair (合理)
*   **關鍵財務亮點**:
    *   營收年成長 +5%
    *   毛利率維持 40% 水準
*   **護城河分析**: 擁有強大的品牌忠誠度與生態系轉換成本。
*   **風險提示**: 消費性電子需求疲軟。
*   **結論**: Bullish (長期看好)，建議分批佈局。
"""
        return response
