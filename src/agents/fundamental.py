from .base_agent import BaseAgent

class FundamentalAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="FUNDAMENTAL", prompt_path="prompts/fundamental_agent.txt", use_cache=use_cache, ttl_hours=168)

    def run(self, context):
        """
        context: {
            "ticker": "AAPL"
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        financials = context.get("financials", {})
        news = context.get("news", [])
        
        user_prompt = f"""
        Analyze {ticker}.
        
        [Real-time Data Injection]
        Key Financials: {financials}
        Recent News: {news}
        
        STRICT INSTRUCTION: Base your analysis on the provided financials and news. Do NOT invent numbers.
        """
        
        response = self._mock_llm_call(user_prompt, self.system_prompt)
        
        # 若使用 Mock，回傳更豐富的 Mock Response
        if "Mock response" in response:
            return f"""
### {ticker} 基本面分析 (Mock)
- **健康度評分**: 8/10
- **結論**: 看多 (Bullish)
- **理由**: 根據 AI 內部知識庫分析，該公司近期表現強勁。
            """
        
        return response
