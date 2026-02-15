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
            "ticker": "AAPL" (Single Mode)
            OR 
            "tickers": ["AAPL", "GOOG"] (Batch Mode)
            "market_data": { "AAPL": { "financials": ... } }
        }
        """
        # 1. Single Ticker Mode
        # 1. 單一標的模式
        if "ticker" in context and context["ticker"] != "UNKNOWN":
            ticker = context["ticker"]
            prompt_data = {
                "ticker": ticker,
                "financials": json.dumps(context.get("financials", {}), indent=2, ensure_ascii=False),
                "news": json.dumps(context.get("news", []), indent=2, ensure_ascii=False)
            }
            return self.run_tool_loop(context=prompt_data)
        
        # 2. Batch Mode (Portfolio Scan)
        # 2. 批量模式 (投資組合掃描)
        tickers = context.get("tickers", [])
        if not tickers:
            return "No tickers provided for Fundamental Analysis."
            
        market_data = context.get("market_data", {})
        
        reports = []
        # Optimization: Limit to top N or process all? For Deep Dive, process all.
        # But to avoid Context limit, we might need to summarize or process one by one.
        # Given this is "Deep-Dive", let's loop and concatenate.
        # 優化: 限制前 N 名或全部處理？深度分析應處理全部。
        # 為避免 Context 限制，可能需要摘要或逐一處理。
        # 鑑於這是「深度分析」，我們採取迴圈並串接結果。
        
        for t in tickers:
            t_data = market_data.get(t, {})
            
            # Prepare context for this specific ticker
            # Note: We re-use the same prompt logic but just run it multiple times.
            # This is expensive but accurate.
            # 為該標的準備 Context
            # 注意: 我們重用相同的 Prompt 邏輯，但多次執行。
            # 這較昂貴但準確。
            
            # Check if we have data
            # 檢查是否有資料
            fin = t_data.get("financials", {})
            news = t_data.get("news", [])
            
            prompt_data = {
                "ticker": t,
                "financials": json.dumps(fin, indent=2, ensure_ascii=False),
                "news": json.dumps(news, indent=2, ensure_ascii=False)
            }
            
            try:
                # Run Agent for this ticker
                # We prefix with header to distinguish in consolidated output
                # 執行 Agent 針對該標的分析
                # 我們加上標題以在合併輸出中區分
                res = self.run_tool_loop(context=prompt_data)
                reports.append(f"### {t} Analysis\n{res}")
            except Exception as e:
                reports.append(f"### {t} Analysis\nError: {e}")
                
        return "\n\n".join(reports)
