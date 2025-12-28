import json
from .base_agent import BaseAgent

class MacroAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        tier = kwargs.pop('tier', 'smart')
        super().__init__(name="Macro", prompt_path="prompts/macro_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    def run(self, context):
        """
        context: {
            "macro_data": {...}
        }
        """
        prompt_data = {
            "macro_data": json.dumps(context.get("macro_data", {}), indent=2, ensure_ascii=False)
        }
        

        response = self.run_tool_loop(context=prompt_data)

        if "Mock response" in response:
            return """
### 全球總經環境分析 (Mock)
*   **週期階段**: 放緩 (Slowdown)
*   **Fed 動向**: Hawkish
*   **關鍵數據解讀**:
    *   VIX 上升至 20
    *   公債殖利率倒掛持續
*   **配置建議**:
    *   **看好板塊**: 醫療保健 (Healthcare), 公用事業 (Utilities)
    *   **避開板塊**: 非必需消費 (Consumer Discretionary)
*   **結論**: Risk Off (避險模式)
"""
        return response
