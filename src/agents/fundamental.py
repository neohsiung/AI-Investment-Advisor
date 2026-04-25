import os
import json
from jinja2 import Template
from .base_agent import BaseAgent

class FundamentalAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        tier = kwargs.pop('tier', 'smart')
        super().__init__(name="Fundamental", prompt_path="prompts/fundamental_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    async def run(self, context):
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
            
            from src.services.supply_chain_service import SupplyChainService
            sc_service = SupplyChainService(user_id=self.user_id)
            sc_info = sc_service.get_shortage_premium(ticker)
            shortage_narrative = sc_info.get("narrative", "")
            
            # General Research Mandate (Ticker Research Generalization)
            # 標的研究模式通用化：針對所有標的，強制分析其與 Tier-1 領先者 (如 NVDA) 的成長確定性差距。
            research_mandate = self._render_research_mandate(ticker)
            
            prompt_data = {
                "ticker": ticker,
                "financials": json.dumps(context.get("financials", {}), indent=2, ensure_ascii=False),
                "news": json.dumps(context.get("news", []), indent=2, ensure_ascii=False),
                "shortage_premium": shortage_narrative,
                "research_mandate": research_mandate
            }
            return await self.run_tool_loop(context=prompt_data)
        
        # 2. Batch Mode (Portfolio Scan)
        # 2. 批量模式 (投資組合掃描)
        tickers = context.get("tickers", [])
        if not tickers:
            return "No tickers provided for Fundamental Analysis."
            
        market_data = context.get("market_data", {})
        
        # Phase 12 Parallel Swarm: Process all tickers in parallel
        async def process_ticker(t):
            t_data = market_data.get(t, {})
            fin = t_data.get("financials", {})
            news = t_data.get("news", [])
            
            from src.services.supply_chain_service import SupplyChainService
            sc_service = SupplyChainService(user_id=self.user_id)
            sc_info = sc_service.get_shortage_premium(t)
            shortage_narrative = sc_info.get("narrative", "")
            
            research_mandate = self._render_research_mandate(t)
            
            prompt_data = {
                "ticker": t,
                "financials": json.dumps(fin, indent=2, ensure_ascii=False),
                "news": json.dumps(news, indent=2, ensure_ascii=False),
                "shortage_premium": shortage_narrative,
                "research_mandate": research_mandate
            }
            
            try:
                res = await self.run_tool_loop(context=prompt_data)
                return f"### {t} Analysis\n{res}"
            except Exception as e:
                return f"### {t} Analysis\nError: {e}"

        tasks = [process_ticker(t) for t in tickers]
        import asyncio
        reports = await asyncio.gather(*tasks)
        return "\n\n".join(reports)

    def _render_research_mandate(self, ticker: str) -> str:
        """Loads and renders the research mandate from a workspace template."""
        template_path = os.path.join(self.workspace_path, "IDENTITY_research.md")
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                template_str = f.read()
            template = Template(template_str)
            return template.render(ticker=ticker)
        
        # Fallback
        return f"Analyze {ticker}'s growth certainty compared to Tier-1 leaders."
