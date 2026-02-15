import json
from .base_agent import BaseAgent
try:
    import dspy
    from .dspy_modules import MomentumSignature
except ImportError:
    dspy = None
    MomentumSignature = None

class MomentumAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 4
        # Allow tier override
        # 允許覆蓋分級 (tier)
        tier = kwargs.pop('tier', 'fast')
        super().__init__(name="Momentum", prompt_path="prompts/momentum_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)
        self.dspy_module = None
        if dspy and hasattr(dspy, 'ChainOfThought') and MomentumSignature:
            # Initialize DSPy Module if real DSPy is present
            # 若真實 DSPy 存在，則初始化 DSPy 模組
            self.dspy_module = dspy.ChainOfThought(MomentumSignature)

    def run(self, context):
        """
        context: {
            "ticker": "AAPL",
            "price_data": {...},
            "indicators": {...}
        }
        """
        ticker = context.get("ticker", "UNKNOWN")
        
        # --- DSPy Path (Optimization / v3.0) ---
        # --- DSPy 路徑 (優化版 / v3.0) ---
        # Only use if dspy is real (has ChainOfThought) and configured
        # 僅在 DSPy 真實存在 (具備 ChainOfThought) 且已配置時使用
        if self.dspy_module and hasattr(dspy, 'settings') and dspy.settings.lm:
            try:
                # Prepare context string for DSPy signature
                # 為 DSPy 簽名準備 Context 字串
                context_json = json.dumps({
                    "ticker": ticker,
                    "price_data": context.get("price_data", {}),
                    "indicators": context.get("indicators", {})
                }, indent=2, ensure_ascii=False)
                
                prediction = self.dspy_module(context=context_json)
                
                # Format output to match legacy expectations or improve it
                # 格式化輸出以符合舊有預期或進行改進
                return f"""
### {ticker} 分析報告 (DSPy Optimized)
*   **信號**: {prediction.signal} (Confidence: {prediction.confidence})
*   **分析**:
{prediction.analysis}
"""
            except Exception as e:
                print(f"DSPy run failed, falling back to legacy: {e}")

        # --- Legacy Path (Jinja2 Templates) ---
        # --- 舊有路徑 (Jinja2 模板) ---
        
        # Prepare data for prompt rendering
        # 準備 Prompt 渲染所需資料
        prompt_data = {
            "ticker": ticker,
            "price_data": json.dumps(context.get("price_data", {}), indent=2, ensure_ascii=False),
            "indicators": json.dumps(context.get("indicators", {}), indent=2, ensure_ascii=False)
        }
        

        response = self.run_tool_loop(context=prompt_data)
        
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
