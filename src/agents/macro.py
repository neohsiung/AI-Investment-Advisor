from .base_agent import BaseAgent

class MacroAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="MACRO", prompt_path="prompts/macro_agent.txt", use_cache=use_cache, ttl_hours=24)

    def run(self, context):
        """
        context: {}  # No specific input required, relies on Prompt
        """
        from src.utils.time_utils import get_current_date_str
        current_date = get_current_date_str()
        macro_data = context.get("macro_data", {})
        
        user_prompt = f"""
        Current Date: {current_date}
        
        [Real-time Data Injection]
        Market Indicators: {macro_data}
        (^VIX: Volatility, ^TNX: 10Y Treasury Yield, SPY: S&P 500 ETF)
        
        Please provide a comprehensive macro analysis based on these indicators.
        """
        
        response = self._mock_llm_call(user_prompt, self.system_prompt)
        
        if "Mock response" in response:
            return f"""
## 總體經濟展望 (Mock)
- **日期**: {current_date}
- **觀點**: Risk-Neutral
- **分析**: 等待更多經濟數據發布。
            """
        
        return response
