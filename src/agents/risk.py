from .base_agent import BaseAgent

class RiskAgent(BaseAgent):
    """
    Risk Agent: Focuses on Portfolio Risk, Volatility (VIX), and Capital Preservation.
    Member of the Agent Council.
    風險探員: 專注於投資組合風險、波動率 (VIX) 與資本保全。
    評議會 (Agent Council) 成員。
    """
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 4
        tier = kwargs.pop('tier', 'fast')
        super().__init__(name="Risk", prompt_path="prompts/risk_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    async def run(self, context):
        """
        context: {
            "ticker": "SPY",
            "market_data": { "vix": 25.5, ... },
            "portfolio": { "beta": 1.2, ... }
        }
        """
        # Prepare data for prompt
        # We assume context is a dict that can be passed to prompt renderer
        # 準備 Prompt 資料
        # 我們假設 context 是一個字典，可直接傳遞給 Prompt 生成器
        response = await self.run_tool_loop(context=context)
        
        return response
