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
        if "ticker" in context and context["ticker"] != "UNKNOWN":
            ticker = context["ticker"]
            prompt_data = {
                "ticker": ticker,
                "financials": json.dumps(context.get("financials", {}), indent=2, ensure_ascii=False),
                "news": json.dumps(context.get("news", []), indent=2, ensure_ascii=False)
            }
            return self.run_tool_loop(context=prompt_data)
        
        # 2. Batch Mode (Portfolio Scan)
        tickers = context.get("tickers", [])
        if not tickers:
            return "No tickers provided for Fundamental Analysis."
            
        market_data = context.get("market_data", {})
        
        reports = []
        # Optimization: Limit to top N or process all? For Deep Dive, process all.
        # But to avoid Context limit, we might need to summarize or process one by one.
        # Given this is "Deep-Dive", let's loop and concatenate.
        
        for t in tickers:
            t_data = market_data.get(t, {})
            
            # Prepare context for this specific ticker
            # Note: We re-use the same prompt logic but just run it multiple times.
            # This is expensive but accurate.
            
            # Check if we have data
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
                res = self.run_tool_loop(context=prompt_data)
                reports.append(f"### {t} Analysis\n{res}")
            except Exception as e:
                reports.append(f"### {t} Analysis\nError: {e}")
                
        return "\n\n".join(reports)
